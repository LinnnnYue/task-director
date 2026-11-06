"""Cross-vendor, cross-family model routing — executable form of the SKILL.md rule.

`SKILL.md` §「供应商与模型族约束（异族互审）」states a hard constraint:

* the executor (worker) and the reviewer / scorer must come from **different
  providers AND different model families**; a same-provider or same-family pair
  is refused, never scored;
* the candidate pool is **health-aware**: probe each model with a tiny request
  before dispatch, skip / blacklist / degrade on failure or timeout, and never
  blindly take the first candidate in catalog order (the known `find()` bug);
* **`pro` tier models are disabled** for every task, whatever its difficulty;
* roles **rotate** across difficulty- and type-appropriate candidates instead of
  being pinned to one model;
* cost follows difficulty: cheap/free flash models for simple work, GLM/Qwen
  class for complex code. Cost is a *preference*; the cross-family rule is a
  *hard constraint*, so a pricier-but-cross-family pair is always preferred over
  a cheap same-family self-review.

This module is the reference implementation, standard library only, so a
docs-only skill repository can still verify the policy:

    python -m unittest discover -s tests -v

It never calls a real endpoint. Callers inject a probe callable
(`probe(route) -> bool`); when no probe is supplied every candidate is assumed
healthy, keeping the module usable offline and testable with stubs.

Data model: a `provider` is the routing group id a live model catalog exposes
(the access channel), and a `family` is the normalized model name (provider
prefix stripped, lowercased, dashes to dots, trailing 4-digit date suffix
dropped). Both must differ between executor and reviewer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import threading
import time
from typing import Callable, Iterable, Mapping, Sequence

#: Cost ladder, cheapest first. `pro` is the disabled tier.
TIERS: tuple[str, ...] = ("free", "cheap", "mid", "strong", "pro")

#: Tiers that must never be selected, at any difficulty, for budget safety.
FORBIDDEN_TIERS: tuple[str, ...] = ("pro",)

#: Difficulty -> cost bands to try, in order. Later bands exist only as
#: degradation: the cross-family constraint outranks the cost preference, so a
#: band with no cross-family pair may widen (cheaper first, then one step
#: stronger) before dispatch gives up. `pro` appears in no band.
TIER_PLANS: dict[str, tuple[tuple[str, ...], ...]] = {
    "simple": (
        ("free", "cheap"),
        ("free", "cheap", "mid"),
    ),
    "standard": (
        ("cheap", "mid"),
        ("free", "cheap", "mid"),
        ("free", "cheap", "mid", "strong"),
    ),
    "complex": (
        ("mid", "strong"),
        ("cheap", "mid", "strong"),
    ),
}

#: Model families a complex *code* task should prefer (GLM / Qwen class).
CODE_FAMILIES: tuple[str, ...] = ("glm", "qwen")

_DATE_SUFFIX = re.compile(r"[._]?\d{4}$")
_DOT_RUN = re.compile(r"[.]{2,}")


class CrossFamilyError(ValueError):
    """No reviewer satisfies the cross-provider-and-family constraint."""


class NoCandidateError(ValueError):
    """No healthy candidate remains; dispatch must not fall back to a pro model."""


# --------------------------------------------------------------------------- #
# Route / family basics
# --------------------------------------------------------------------------- #


def norm_model(model: str | None) -> str:
    """Normalize a model id into its family key.

    Provider prefix is stripped, text lowercased, dashes become dots, runs of
    dots collapse, and a trailing 4-digit date suffix is dropped, so
    `deepseek-v4.1-flash-1017`, `DeepSeek-V4.1-Flash` and
    `trae/DeepSeek-V4.1-Flash` all land in the same family.
    """
    text = str(model or "").strip().split("/")[-1].lower()
    text = text.replace("-", ".")
    text = _DOT_RUN.sub(".", text)
    return _DATE_SUFFIX.sub("", text).strip(".")


def norm_provider(provider: str | None) -> str:
    return str(provider or "").strip().lower()


@dataclass(frozen=True)
class Route:
    """One candidate: provider (catalog group id), model id, cost tier."""

    provider: str
    model: str
    tier: str = "mid"

    def __post_init__(self) -> None:
        if not norm_provider(self.provider) or not norm_model(self.model):
            raise ValueError(f"路由候选缺少 provider/model：{self!r}")
        if self.tier not in TIERS:
            raise ValueError(f"未知成本档 {self.tier!r}，应为 {TIERS}")

    @property
    def family(self) -> str:
        return norm_model(self.model)

    @property
    def key(self) -> tuple[str, str]:
        return (norm_provider(self.provider), self.family)

    def __str__(self) -> str:  # compact, for evidence lines
        return f"{self.provider}/{self.model}"

    def as_dict(self) -> dict[str, str]:
        return {"provider": self.provider, "model": self.model, "tier": self.tier, "family": self.family}


def cross_ok(worker: Route, reviewer: Route) -> bool:
    """True only when provider *and* family both differ."""
    return norm_provider(worker.provider) != norm_provider(reviewer.provider) and worker.family != reviewer.family


def require_cross(worker: Route, reviewer: Route) -> None:
    """Raise when the pair would be same-provider or same-family (包庇风险)."""
    if not cross_ok(worker, reviewer):
        raise CrossFamilyError(
            "异族互审约束不成立：执行者 "
            f"{worker}（族 {worker.family}）与评审者 {reviewer}（族 {reviewer.family}）"
            "必须 provider 与模型族都不同；同供应商或同族一律拒绝，须改选其他候选。"
        )


# --------------------------------------------------------------------------- #
# Candidate pool
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Pool:
    """A candidate pool, in the operator's declared order (rotation applies on top)."""

    routes: tuple[Route, ...]

    def __post_init__(self) -> None:
        if not self.routes:
            raise ValueError("候选池为空：至少需要一个候选")

    def usable(self, tiers: Sequence[str], health: "HealthRegistry | None" = None) -> list[Route]:
        """Tier-legal, non-forbidden, currently-healthy candidates."""
        allowed = {tier for tier in tiers if tier not in FORBIDDEN_TIERS}
        out: list[Route] = []
        for route in self.routes:
            if route.tier not in allowed:
                continue
            if health is not None and health.is_dead(route):
                continue
            out.append(route)
        return out


def pool_from_list(entries: Iterable[Mapping[str, object] | Route]) -> Pool:
    """Build a pool; every entry is validated by `Route.__post_init__`."""
    built: list[Route] = []
    for position, entry in enumerate(entries):
        if isinstance(entry, Route):
            built.append(entry)
            continue
        if not isinstance(entry, Mapping):
            raise ValueError(f"候选池第 {position + 1} 条不是对象：{entry!r}")
        try:
            built.append(
                Route(
                    provider=str(entry.get("provider", "")),
                    model=str(entry.get("model", "")),
                    tier=str(entry.get("tier", "mid")),
                )
            )
        except ValueError as error:
            raise ValueError(f"候选池第 {position + 1} 条无效：{error}") from error
    return Pool(tuple(built))


def load_pool(source: str | Mapping[str, object] | Sequence[Mapping[str, object]]) -> Pool:
    """Load a pool from a JSON path, a decoded mapping, or a plain list of entries."""
    if isinstance(source, str):
        with open(source, encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = source
    entries = data.get("candidates") if isinstance(data, Mapping) else data
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ValueError('候选池文件应形如 {"candidates": [...]} 或候选数组')
    return pool_from_list(entries)


def interleave_by_family(routes: Sequence[Route]) -> list[Route]:
    """Stable round-robin over families, so consecutive rotations change family.

    This is the canonical ordering rotation walks; it replaces "take the first
    entry of the catalog" with a deterministic family-rotating order.
    """
    buckets: dict[str, list[Route]] = {}
    for route in routes:
        buckets.setdefault(route.family, []).append(route)
    order = list(buckets)
    out: list[Route] = []
    while order:
        progressed = False
        for family in list(order):
            bucket = buckets[family]
            if bucket:
                out.append(bucket.pop(0))
                progressed = True
            if not bucket:
                order.remove(family)
        if not progressed:  # pragma: no cover - defensive
            break
    return out


# --------------------------------------------------------------------------- #
# Cost tiers
# --------------------------------------------------------------------------- #


def tier_plans(task_class: str) -> tuple[tuple[str, ...], ...]:
    """Cost bands to try for a difficulty, preferred band first."""
    plan = TIER_PLANS.get(task_class)
    if plan is None:
        raise ValueError(f"未知任务复杂度 {task_class!r}，应为 {tuple(TIER_PLANS)}")
    return plan


def preferred_tiers(task_class: str) -> tuple[str, ...]:
    """The band a difficulty should normally use: cheap flash for simple work,
    GLM/Qwen-class mid for complex work. `pro` never appears."""
    return tier_plans(task_class)[0]


def allowed_tiers(task_class: str) -> tuple[str, ...]:
    """Union of every band a difficulty may fall back to, cheapest first,
    `pro` excluded."""
    present = {tier for band in tier_plans(task_class) for tier in band}
    return tuple(tier for tier in TIERS if tier in present and tier not in FORBIDDEN_TIERS)


def filter_for_type(routes: Sequence[Route], task_class: str, task_type: str | None) -> tuple[list[Route], str | None]:
    """Complex code work prefers GLM/Qwen-class families; falls back when unavailable."""
    if task_type != "code" or task_class != "complex":
        return list(routes), None
    preferred = [route for route in routes if route.family.startswith(CODE_FAMILIES)]
    if not preferred:
        return list(routes), None
    return preferred, f"复杂代码任务优先 {CODE_FAMILIES} 族候选（{len(preferred)} 个）"


# --------------------------------------------------------------------------- #
# Health awareness
# --------------------------------------------------------------------------- #

ProbeFn = Callable[[Route], bool]


@dataclass
class _Dead:
    until: float
    reason: str
    count: int


class HealthRegistry:
    """Blacklist of failing models, with a TTL so a transient outage heals."""

    def __init__(self, ttl_seconds: float | None = 900, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl = ttl_seconds
        self.clock = clock
        self._dead: dict[tuple[str, str], _Dead] = {}

    def is_dead(self, route: Route) -> bool:
        entry = self._dead.get(route.key)
        if entry is None:
            return False
        if self.ttl is not None and entry.until <= self.clock():
            del self._dead[route.key]
            return False
        return True

    def reason(self, route: Route) -> str | None:
        entry = self._dead.get(route.key)
        return entry.reason if entry is not None and self.is_dead(route) else None

    def trip(self, route: Route, reason: str) -> None:
        now = self.clock()
        previous = self._dead.get(route.key)
        count = (previous.count if previous else 0) + 1
        until = float("inf") if self.ttl is None else now + self.ttl
        self._dead[route.key] = _Dead(until=until, reason=reason, count=count)

    def heal(self, route: Route) -> None:
        self._dead.pop(route.key, None)

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            f"{provider}/{family}": {"reason": entry.reason, "count": entry.count}
            for (provider, family), entry in self._dead.items()
            if self._still_dead(provider, family)
        }

    def _still_dead(self, provider: str, family: str) -> bool:
        entry = self._dead.get((provider, family))
        if entry is None:
            return False
        return self.ttl is None or entry.until > self.clock()


def probe_route(probe: ProbeFn | None, route: Route, timeout: float) -> bool:
    """Probe one candidate; timeout and any error count as unhealthy.

    The probe runs on a **daemon** thread so a hung endpoint cannot keep the
    process alive: a `ThreadPoolExecutor` worker is non-daemon, so a probe that
    ignores its timeout would block interpreter exit after the selection run
    finished. Daemon threads are abandoned at exit, which is the right cost for
    a health check whose only failure mode is "this model is unusable".
    """
    if probe is None:
        return True
    if timeout <= 0:
        raise ValueError("探针超时必须为正数")

    outcome: dict[str, object] = {}

    def run() -> None:
        try:
            outcome["healthy"] = bool(probe(route))
        except Exception as error:  # any probe error means the model is unusable
            outcome["healthy"] = False
            outcome["error"] = str(error)

    thread = threading.Thread(target=run, name=f"model-probe:{route}", daemon=True)
    thread.start()
    thread.join(timeout)
    return bool(outcome.get("healthy", False))


# --------------------------------------------------------------------------- #
# Rotation state
# --------------------------------------------------------------------------- #


@dataclass
class RotationState:
    """Persisted cursors: consecutive dispatches keep rotating instead of pinning."""

    worker_cursor: int = 0
    reviewer_cursor: int = 0

    @classmethod
    def load(cls, path: str) -> "RotationState":
        """Read the persisted cursors; a missing or corrupt file restarts at zero.

        A bad rotation file must not block dispatch — losing the cursor only costs
        one round of less-varied selection.
        """
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return cls()
        if not isinstance(data, Mapping):
            return cls()
        return cls(
            worker_cursor=int(data.get("worker_cursor", 0) or 0),
            reviewer_cursor=int(data.get("reviewer_cursor", 0) or 0),
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"worker_cursor": self.worker_cursor, "reviewer_cursor": self.reviewer_cursor}, handle)


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


@dataclass
class Selection:
    worker: Route
    reviewer: Route
    task_class: str
    task_type: str | None
    degraded: bool
    evidence: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "worker": self.worker.as_dict(),
            "reviewer": self.reviewer.as_dict(),
            "task_class": self.task_class,
            "task_type": self.task_type,
            "degraded": self.degraded,
            "evidence": list(self.evidence),
        }


def _note(evidence: list[str], line: str) -> None:
    """Append a line kept in the final evidence, removing duplicates."""
    if line not in evidence:
        evidence.append(line)


def _pick(routes: Sequence[Route], cursor: int, *, health: HealthRegistry, probe: ProbeFn | None,
          timeout: float, evidence: list[str]) -> tuple[Route | None, int]:
    """Walk the rotated order, skipping dead and failing candidates.

    Returns the chosen route and the cursor into `routes` *just after* it, so the
    next dispatch starts from the following candidate instead of the same one.
    """
    if not routes:
        return None, cursor
    size = len(routes)
    start = cursor % size
    for offset in range(size):
        route = routes[(start + offset) % size]
        if health.is_dead(route):
            evidence.append(f"跳过 {route}：在黑名单中（{health.reason(route) or '此前探针失败'}）")
            continue
        if not probe_route(probe, route, timeout):
            health.trip(route, "探针失败或超时")
            evidence.append(f"跳过 {route}：探针失败/超时（已加入黑名单）")
            continue
        return route, (start + offset + 1) % size
    return None, start


def select_roles(
    pool: Pool,
    *,
    task_class: str = "standard",
    task_type: str | None = None,
    rotation: RotationState | None = None,
    health: HealthRegistry | None = None,
    probe: ProbeFn | None = None,
    probe_timeout: float = 3.0,
    allow_degrade: bool = True,
) -> Selection:
    """Pick a worker and a cross-provider, cross-family reviewer.

    Order of decisions:
    1. cost band by difficulty (`tier_plans` / `allowed_tiers`), `pro` excluded;
    2. complex code tasks prefer GLM/Qwen families, retried without that
       preference if the preferred families cannot be paired cross-family;
    3. canonical order interleaves families, then rotation walks it from the
       persisted cursor — never "first entry in catalog";
    4. every candidate is probed; failures are blacklisted and skipped;
    5. reviewer must differ from the worker in provider *and* family;
    6. if the preferred band has no healthy cross-family pair, widen to the next
       band (cheaper first, then one step stronger, never `pro`) before refusing.
    """
    rotation = rotation if rotation is not None else RotationState()
    health = health if health is not None else HealthRegistry()
    evidence: list[str] = []
    first_error: ValueError | None = None

    plans: list[tuple[tuple[str, ...], bool, bool]] = []
    for step, band in enumerate(tier_plans(task_class)):
        plans.append((band, step > 0, True))
        plans.append((band, step > 0, False))
    if not allow_degrade:
        plans = [entry for entry in plans if not entry[1]]

    for band, degraded, prefer in plans:
        try:
            return _select_once(
                pool,
                task_class=task_class,
                task_type=task_type,
                band=band,
                degraded=degraded,
                prefer=prefer,
                rotation=rotation,
                health=health,
                probe=probe,
                probe_timeout=probe_timeout,
                evidence=evidence,
            )
        except (NoCandidateError, CrossFamilyError) as error:
            first_error = first_error or error
            continue
    assert first_error is not None
    raise first_error


def _select_once(
    pool: Pool,
    *,
    task_class: str,
    task_type: str | None,
    band: tuple[str, ...],
    degraded: bool,
    prefer: bool,
    rotation: RotationState,
    health: HealthRegistry,
    probe: ProbeFn | None,
    probe_timeout: float,
    evidence: list[str],
) -> Selection:
    if degraded:
        evidence.append(f"优先成本档无健康异族配对，已降档：{band}")
    excluded = [route for route in pool.routes if route.tier in FORBIDDEN_TIERS]
    if excluded:
        evidence.append(f"已排除 pro 档候选 {len(excluded)} 个（任何任务禁用 Pro）")

    legal = pool.usable(band, health)
    if not legal:
        raise NoCandidateError(
            f"任务 {task_class}（成本档 {band}）在候选池中没有健康候选；"
            "不得回退到同族自评，也不得启用 pro 档，需补池或待健康模型恢复"
        )

    if prefer:
        filtered, note = filter_for_type(legal, task_class, task_type)
        if note:
            evidence.append(note)
    else:
        filtered = list(legal)
    ordered = interleave_by_family(filtered)

    worker, index = _pick(ordered, rotation.worker_cursor, health=health, probe=probe,
                          timeout=probe_timeout, evidence=evidence)
    if worker is None:
        raise NoCandidateError(
            f"任务 {task_class}：所有 Worker 候选都探针失败；不得退回同族自评或 pro 档"
        )
    rotation.worker_cursor = index

    reviewer_pool = [route for route in ordered if cross_ok(worker, route)]
    if not reviewer_pool:
        raise CrossFamilyError(
            f"没有与执行者 {worker}（provider {worker.provider}，族 {worker.family}）"
            "provider 与族都不同的评审候选；同族/同供应商不得评分，须改选或补池"
        )
    reviewer, index = _pick(reviewer_pool, rotation.reviewer_cursor, health=health, probe=probe,
                            timeout=probe_timeout, evidence=evidence)
    if reviewer is None:
        raise CrossFamilyError(
            f"与执行者 {worker} 异族的评审候选全部探针失败；不得退回同族自评或 pro 档"
        )
    rotation.reviewer_cursor = index
    require_cross(worker, reviewer)
    _note(evidence, f"执行者 {worker}（{worker.provider} 族 {worker.family}，成本档 {worker.tier}）")
    _note(evidence, f"评审者 {reviewer}（{reviewer.provider} 族 {reviewer.family}，成本档 {reviewer.tier}）")

    return Selection(worker=worker, reviewer=reviewer, task_class=task_class,
                     task_type=task_type, degraded=degraded, evidence=evidence)


# --------------------------------------------------------------------------- #
# CLI (manual verification / demo)
# --------------------------------------------------------------------------- #


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="按异族互审规则选出一组 worker/reviewer 模型")
    parser.add_argument("--pool", required=True, help="候选池 JSON 路径")
    parser.add_argument("--task", default="standard", choices=sorted(TIER_PLANS), help="任务复杂度")
    parser.add_argument("--type", default=None, help="任务类型（如 code）")
    parser.add_argument("--rounds", type=int, default=1, help="连续轮换轮数")
    args = parser.parse_args(argv)

    pool = load_pool(args.pool)
    rotation = RotationState()
    health = HealthRegistry()
    for _ in range(args.rounds):
        selection = select_roles(pool, task_class=args.task, task_type=args.type, rotation=rotation, health=health)
        print(json.dumps(selection.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

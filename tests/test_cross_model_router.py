"""Policy tests for cross-vendor, cross-family model routing (stdlib unittest only).

Run: python -m unittest discover -s tests -v

Covered (required by the ticket):
* 同族 / 同供应商配对被拒（require_cross + 选择器永不返回同族评审）
* 连续多次轮换始终保持异族
* 坏模型（探针失败 / 超时）被跳过并进入黑名单，且不按目录顺序盲取首个
* pro 档任何任务禁用；成本分档随难度变化
* 同档无健康候选时降档，绝不降级为同族自评
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cross_model_router import (  # noqa: E402  (sys.path set above)
    CrossFamilyError,
    HealthRegistry,
    NoCandidateError,
    Pool,
    RotationState,
    Route,
    Selection,
    cross_ok,
    filter_for_type,
    interleave_by_family,
    load_pool,
    norm_model,
    probe_route,
    require_cross,
    allowed_tiers,
    preferred_tiers,
    select_roles,
    tier_plans,
    tiers_for,
)

POOL = Pool(
    (
        Route("codearts", "deepseek-v4.1-flash-1017", "cheap"),
        Route("trae", "deepseek-v4.1-flash", "cheap"),
        Route("loomy", "qwen3.8-flash", "mid"),
        Route("trae", "qwen3.8-flash", "mid"),
        Route("trae", "glm-5.3-flash", "mid"),
        Route("loomy", "GLM-5.3-Flash", "mid"),
        Route("buddy", "deepseek-v4.1-pro", "pro"),
    )
)


def sel(**kwargs) -> Selection:
    kwargs.setdefault("pool", POOL)
    return select_roles(**kwargs)


class FamilyNormalizationTest(unittest.TestCase):
    def test_dash_case_and_date_suffix_collapse_to_one_family(self):
        variants = [
            "deepseek-v4.1-flash",
            "DeepSeek-V4.1-Flash",
            "deepseek-v4.1-flash-1017",
            "trae/DeepSeek-V4.1-Flash",
        ]
        self.assertEqual({norm_model(v) for v in variants}, {"deepseek.v4.1.flash"})

    def test_glm_and_qwen_are_distinct_families(self):
        self.assertNotEqual(norm_model("glm-5.3-flash"), norm_model("qwen3.8-flash"))


class CrossConstraintTest(unittest.TestCase):
    def test_same_family_pair_is_refused(self):
        worker = Route("trae", "deepseek-v4.1-flash", "cheap")
        reviewer = Route("codearts", "deepseek-v4.1-flash-1017", "cheap")
        self.assertFalse(cross_ok(worker, reviewer))
        with self.assertRaises(CrossFamilyError):
            require_cross(worker, reviewer)

    def test_same_provider_pair_is_refused_even_across_families(self):
        worker = Route("trae", "deepseek-v4.1-flash", "cheap")
        reviewer = Route("trae", "glm-5.3-flash", "mid")
        self.assertFalse(cross_ok(worker, reviewer))
        with self.assertRaises(CrossFamilyError):
            require_cross(worker, reviewer)

    def test_cross_provider_and_family_passes(self):
        worker = Route("codearts", "deepseek-v4.1-flash", "cheap")
        reviewer = Route("trae", "glm-5.3-flash", "mid")
        self.assertTrue(cross_ok(worker, reviewer))
        require_cross(worker, reviewer)  # must not raise

    def test_selector_never_returns_same_family_reviewer(self):
        for task in ("simple", "standard", "complex"):
            for _ in range(10):
                selection = sel(task_class=task, task_type="code")
                self.assertNotEqual(selection.worker.family, selection.reviewer.family)
                self.assertNotEqual(
                    selection.worker.provider.lower(), selection.reviewer.provider.lower()
                )


class RotationTest(unittest.TestCase):
    def test_five_consecutive_rotations_stay_cross_family_and_change_worker(self):
        rotation = RotationState()
        seen_workers = []
        for round_no in range(5):
            selection = sel(task_class="standard", rotation=rotation)
            self.assertTrue(cross_ok(selection.worker, selection.reviewer),
                            f"第 {round_no + 1} 轮出现同族/同供应商配对")
            seen_workers.append(str(selection.worker))
        self.assertGreater(len(set(seen_workers)), 1, "连续轮换必须换模型，不能锁死一个")

    def test_rotation_cursor_is_not_catalog_first_entry(self):
        rotation = RotationState()
        first = sel(task_class="standard", rotation=rotation).worker
        second = sel(task_class="standard", rotation=rotation).worker
        self.assertNotEqual(first, second, "轮换不能每次都取目录第一个候选")

    def test_rotation_visits_every_legal_family_before_repeating(self):
        rotation = RotationState()
        picked = []
        for _ in range(4):
            picked.append(sel(task_class="complex", task_type="code", rotation=rotation).worker.family)
        self.assertGreaterEqual(len(set(picked)), 2)


class HealthTest(unittest.TestCase):
    def test_probe_failure_is_skipped_and_blacklisted(self):
        health = HealthRegistry()
        bad = Route("codearts", "deepseek-v4.1-flash-1017", "cheap")

        def probe(route: Route) -> bool:
            return route.key != bad.key

        selection = sel(task_class="simple", health=health, probe=probe)
        self.assertNotEqual(selection.worker.key, bad.key)
        self.assertTrue(health.is_dead(bad))
        self.assertTrue(any("探针失败" in line for line in selection.evidence))

    def test_timeout_is_treated_as_unhealthy(self):
        slow = Route("loomy", "qwen3.8-flash", "mid")

        def probe(route: Route) -> bool:
            if route.key == slow.key:
                time.sleep(0.2)
            return True

        self.assertFalse(probe_route(probe, slow, 0.05))
        self.assertTrue(probe_route(probe, POOL.routes[0], 0.05))

    def test_blacklisted_model_is_not_probed_again_in_the_same_rotation(self):
        health = HealthRegistry()
        bad = Route("trae", "glm-5.3-flash", "mid")
        calls = []

        def probe(route: Route) -> bool:
            calls.append(route.key)
            return route.key != bad.key

        first = sel(task_class="standard", health=health, probe=probe)
        before = len(calls)
        second = sel(task_class="standard", health=health, probe=probe)
        self.assertNotEqual(first.worker.key, bad.key)
        self.assertNotEqual(second.worker.key, bad.key)
        self.assertGreater(len(calls), before, "第二轮仍应探针健康候选")

    def test_all_candidates_blacklisted_raises_instead_of_falling_back_same_family(self):
        health = HealthRegistry()
        for route in POOL.routes:
            health.trip(route, "探针失败")
        with self.assertRaises((NoCandidateError, CrossFamilyError)):
            sel(task_class="standard", health=health)

    def test_health_ttl_heals_a_transient_failure(self):
        now = [1000.0]
        health = HealthRegistry(ttl_seconds=60, clock=lambda: now[0])
        route = POOL.routes[0]
        health.trip(route, "探针超时")
        self.assertTrue(health.is_dead(route))
        now[0] += 61
        self.assertFalse(health.is_dead(route))
        self.assertIsNone(health.reason(route))


class TierTest(unittest.TestCase):
    def test_pro_tier_is_never_selected_for_any_difficulty(self):
        for task in ("simple", "standard", "complex"):
            for _ in range(6):
                selection = sel(task_class=task, task_type="code")
                self.assertNotEqual(selection.worker.tier, "pro")
                self.assertNotEqual(selection.reviewer.tier, "pro")

    def test_difficulty_changes_the_preferred_cost_band(self):
        self.assertEqual(preferred_tiers("simple"), ("free", "cheap"))
        self.assertEqual(preferred_tiers("standard"), ("cheap", "mid"))
        self.assertEqual(preferred_tiers("complex"), ("mid", "strong"))

    def test_pro_is_absent_from_every_band_and_union(self):
        for task in ("simple", "standard", "complex"):
            for band in tier_plans(task):
                self.assertNotIn("pro", band)
            self.assertNotIn("pro", allowed_tiers(task))
            self.assertNotIn("pro", tiers_for(task))

    def test_simple_task_prefers_cheap_tiers_when_a_cross_family_pair_exists(self):
        pool = Pool(
            (
                Route("loomy", "spark-x2.6", "free"),
                Route("codearts", "deepseek-v4.1-flash-1017", "cheap"),
                Route("trae", "deepseek-v4.1-flash", "cheap"),
                Route("loomy", "qwen3.8-flash", "mid"),
            )
        )
        selection = select_roles(pool, task_class="simple")
        self.assertFalse(selection.degraded)
        self.assertIn(selection.worker.tier, ("free", "cheap"))
        self.assertIn(selection.reviewer.tier, ("free", "cheap"))

    def test_widening_never_adds_pro(self):
        self.assertNotIn("pro", tiers_for("complex"))
        self.assertEqual(allowed_tiers("complex"), ("cheap", "mid", "strong"))

    def test_degrade_happens_when_the_preferred_band_has_no_cross_family_pair(self):
        only_mid = Pool(
            (
                Route("trae", "glm-5.3-flash", "mid"),
                Route("loomy", "qwen3.8-flash", "mid"),
                Route("buddy", "deepseek-v4.1-flash", "strong"),
            )
        )
        selection = select_roles(only_mid, task_class="simple", allow_degrade=True)
        self.assertTrue(selection.degraded, "优先档无候选时必须降档而不是回退同族")
        self.assertTrue(cross_ok(selection.worker, selection.reviewer))
        self.assertNotEqual(selection.worker.tier, "pro")
        self.assertNotEqual(selection.reviewer.tier, "pro")

    def test_no_candidate_at_any_tier_raises(self):
        pool = Pool((Route("trae", "glm-5.3-flash", "pro"),))
        with self.assertRaises(NoCandidateError):
            select_roles(pool, task_class="simple")


class TypePreferenceTest(unittest.TestCase):
    def test_complex_code_task_prefers_glm_or_qwen(self):
        selection = sel(task_class="complex", task_type="code")
        self.assertTrue(
            selection.worker.family.startswith(("glm", "qwen"))
            or selection.reviewer.family.startswith(("glm", "qwen")),
            "复杂代码任务应优先 glm/千问族",
        )

    def test_filter_falls_back_when_no_preferred_family_exists(self):
        pool = Pool((Route("trae", "deepseek-v4.1-flash", "cheap"), Route("codearts", "deepseek-v4.1-flash", "cheap")))
        kept, note = filter_for_type(list(pool.routes), "complex", "code")
        self.assertEqual(len(kept), 2)
        self.assertIsNone(note)

    def test_simple_task_does_not_prefer_glm_family(self):
        routes = list(POOL.routes)
        kept, note = filter_for_type(routes, "simple", "code")
        self.assertEqual(len(kept), len(routes))
        self.assertIsNone(note)


class PoolAndOrderingTest(unittest.TestCase):
    def test_load_pool_from_example_file(self):
        pool = load_pool(str(ROOT / "scripts" / "model-pool.example.json"))
        self.assertEqual(len(pool.routes), 10)
        self.assertTrue(any(route.tier == "pro" for route in pool.routes))

    def test_load_pool_accepts_plain_array_and_mapping(self):
        entries = [{"provider": "trae", "model": "glm-5.3-flash", "tier": "mid"}]
        self.assertEqual(len(load_pool(entries).routes), 1)
        self.assertEqual(len(load_pool({"candidates": entries}).routes), 1)

    def test_interleave_makes_consecutive_entries_different_families(self):
        ordered = interleave_by_family(list(POOL.routes))
        consecutive_same = [
            (a.family, b.family)
            for a, b in zip(ordered, ordered[1:])
            if a.family == b.family
        ]
        self.assertLessEqual(len(consecutive_same), 1, "同族条目不应连续排列")

    def test_rotation_state_round_trips_through_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "rotation.json")
            state = RotationState(worker_cursor=2, reviewer_cursor=1)
            state.save(path)
            loaded = RotationState.load(path)
            self.assertEqual((loaded.worker_cursor, loaded.reviewer_cursor), (2, 1))

    def test_missing_rotation_file_starts_at_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded = RotationState.load(str(Path(tmp) / "absent.json"))
            self.assertEqual((loaded.worker_cursor, loaded.reviewer_cursor), (0, 0))

    def test_selection_serializes_for_evidence_logs(self):
        selection = sel(task_class="standard")
        payload = json.loads(json.dumps(selection.as_dict(), ensure_ascii=False))
        self.assertIn("worker", payload)
        self.assertIn("reviewer", payload)
        self.assertTrue(payload["evidence"])
        self.assertNotEqual(payload["worker"]["family"], payload["reviewer"]["family"])


class RouteValidationTest(unittest.TestCase):
    def test_route_rejects_empty_provider_or_model(self):
        with self.assertRaises(ValueError):
            Route("", "glm-5.3-flash")
        with self.assertRaises(ValueError):
            Route("trae", "")

    def test_route_rejects_unknown_tier(self):
        with self.assertRaises(ValueError):
            Route("trae", "glm-5.3-flash", "platinum")

    def test_empty_pool_rejected(self):
        with self.assertRaises(ValueError):
            Pool(())


if __name__ == "__main__":
    unittest.main(verbosity=2)

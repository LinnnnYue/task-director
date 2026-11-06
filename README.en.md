# task-director

> 🎯 A general-purpose "task director" meta-skill: you give the brief, it breaks the task into an Agent team, sets the bar, quality-gates, and distills reusable templates.

<p align="left">
  <a href="README.md">🇨🇳 中文</a> &nbsp;·&nbsp; Issues and PRs welcome
</p>

---

## 💡 Why you'll want it

Does any of this sound familiar?

- You hand an AI a complex task and it either one-lines you or rambles without acting?
- Multi-step work loses context halfway, drifts off course, and you end up cleaning up?
- You want AI to collaborate in parallel but don't know how to split or accept the result?

**task-director handles exactly that.** It is never the doer — it is the **director**: decompose, team up, set acceptance lines, cover edges, log bias, prune. You keep the final call; it carries the dirty work of orchestration and quality-gating.

## ✨ Features

- **🤝 HITL first, auto escape hatch** — shows the team plan for your nod by default; says "just do it / auto" and it runs silent, no interruption to your flow.
- **🧩 Three-layer dispatch** — Director / specialist modules (UI, code quality baselines) / Workers. Taste and rules live in the modules, never hardcoded in the flow.
- **📊 10-point scale, 5 dynamic dimensions** — proposal / execution / deliverable / innovation / compliance; specialists override weights (e.g. UI deliverable → 0.35).
- **🛡️ Score calibration log** — AI grading AI drifts. Every 5 "human-low / machine-high" gaps tighten that dimension's default by 0.3; recovers after 3 consistent runs. Honest over time.
- **🗂️ Template retirement** — retires only on dual condition (>90d unused AND a higher-score peer appears). Low-frequency users never purged by a timer; high-frequency users never dragged by entropy.
- **⚖️ User veto right** — any score can be overturned; "rollback to Phase 1" final call is always yours. Flow serves trust, not the number.
- **🔀 Cross-family review, no collusion** — the executor and the reviewer must come from **different providers AND different model families** (e.g. `qwen3.8-flash` writes, `GLM-5.3-Flash` reviews). Same-family pairs are refused; nobody scores their own kin. Each model is probed with a tiny request before dispatch, and failing or timing-out models are skipped and blacklisted instead of blindly taking the first catalog entry.
- **💰 Cost tiers** — free/cheap flash models for simple work, GLM / Qwen class for complex code; the `pro` tier is disabled for every task so it never burns credits.

## 🚀 Quick start

**Install** — copy the whole dir into your Agent skills path (keep the name `task-director`):

```text
WorkBuddy:   ~/.workbuddy/skills/task-director/
Claude Code: ~/.claude/skills/task-director/   # or .agents/skills, .anybox/skills
Codex:       ~/.codex/skills/task-director/    # or $CODEX_HOME/skills/task-director/
Cross-client project install: .agents/skills/task-director/
```

The dir must contain: `SKILL.md`, `role-models.md`, `specialist-registry.md`, `role-templates.md`, `score-calibration-log.md`, `role-templates-archive.md`. `scripts/` and `tests/` hold the optional reference implementation and its checks — the skill works without them, it just loses automatic selection.

**Use**

- Triggers: `派任务` / `orchestrate` / `导演` / `任务拆分` / `分身协作`
- Trust mode: command contains `直接派` / `just do it` / `auto` → Phase 1 runs silent.
- Red lines (hard stop for you): privacy, public release, irreversible ops, budget.

**Configure the model pool (required for cross-vendor rotation)** — open `role-models.md` and replace the sample pool with the providers and models your own accounts can actually call. Each entry needs three things: the call channel `provider`, the model id `model`, and a cost `tier` (`free` / `cheap` / `mid` / `strong`; mark `pro` models as `pro` — they are excluded automatically).

Three rules you cannot skip:

1. **Mount every model family on at least two providers**, otherwise one 403 or a rate limit leaves you unable to form a cross-family pair.
2. **Keep `pro` entries but never use them**: they stay in the pool so the file honestly reflects your account, and dispatch filters them out.
3. **Prefer a reviewer family that criticises reliably** (GLM-class): a different family is only the precondition; willingness to find faults is what makes it a review.

**Verify the routing rules** — standard library only, no dependencies:

```bash
python -m unittest discover -s tests -v
```

To see a selection run first:

```bash
python scripts/cross_model_router.py \
  --pool scripts/model-pool.example.json \
  --task complex --type code --rounds 4
```

## 🔄 How it works

```mermaid
flowchart LR
    P0[Phase 0<br/>trigger & load] --> P1[Phase 1<br/>decompose + team]
    P1 -- you confirm / HITL --> P2[Phase 2<br/>spawn prompts]
    P2 --> P3[Phase 3<br/>dispatch]
    P3 --> P4[Phase 4<br/>score]
    P4 -- pass --> P5[Phase 5<br/>consolidate]
    P4 -- fail --> P1
    P1 -. you say rollback .-> P1
```

1. **Phase 0 trigger & load** — optionally load your user-profile / specialist modules; fall back to generic defaults if absent.
2. **Phase 1 decompose + team design** — task type, complexity, deps, risks, Agent team table. **This is your confirmation point.**
3. **Phase 2 spawn sub-agent prompts** — self-contained, explicit output specs for later scoring.
4. **Phase 3 dispatch** — parallel / pipeline / iterate (≤3 rounds per agent); ≤4 workers +1 integrator.
5. **Phase 4–5 score & consolidate** — 10-pt 5-dim scoring; ≥8 enters the role-template library.

## 🔧 Customize

**Specialist interface** — mount your domain baselines (UI taste, code style, writing) in `specialist-registry.md` by schema; the bundled `ui-design-baseline` is a format demo only — swap in your own.

**Model pool interface** — register candidates in `role-models.md` (human-readable) and `scripts/model-pool.example.json` (machine-readable schema example; copy it to your own `model-pool.json` and point the script at it). Keep both in sync: the human file records each model's pitfalls, the machine file drives dispatch.

**Weights and routing are two separate things** — specialist modules set *how much* a dimension weighs; the model pool sets *who* judges it. No weight setting exempts a same-family pair: tighten the weights all you like, a same-family reviewer still lets it slide.

**User-profile interface** — if you distilled a user-profile / persona module (e.g. `user-profile/self.md`, `persona.md`), optionally read it in Phase 0 to calibrate tone and privacy boundaries. **Fully optional**; runs fine without it.

## 🪞 Meta · it reviewed its own release

This repo's release prep (de-personalize, generalize deps, author credits, write docs) was itself produced and reviewed by **task-director** in HITL mode — the director decomposed the publish task, spawned sub-agent prompts, scored, consolidated, all under your veto. A skill auditing its own release is the closed-loop proof of its creed: orchestrate, not author; quality-gate, never decide for you.

## 📁 Structure

```text
task-director/
├── SKILL.md                  # skill body: 5-Phase flow + 10-pt scorecard + cross-family rule
├── role-models.md            # candidate pool / cost tiers / probe blacklist / rotation (human)
├── specialist-registry.md    # specialist mounts & weight overrides (demo included)
├── role-templates.md         # verified role-template library (2 demos)
├── score-calibration-log.md  # human-vs-machine bias log (empty template)
├── role-templates-archive.md # retired template archive (empty template)
├── scripts/
│   ├── cross_model_router.py     # reference implementation of the routing rule (zero deps)
│   └── model-pool.example.json   # machine-readable pool schema example
├── tests/
│   └── test_cross_model_router.py # routing-policy tests (stdlib unittest)
├── LICENSE                   # MIT
├── README.md                 # this page (中文)
└── README.en.md              # English version
```

## 📄 License

[MIT](LICENSE) © 2026 小凛酱丷

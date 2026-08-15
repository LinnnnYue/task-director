# task-director · 任务总监

通用的 **Orchestrator 元技能**——把任意任务拆解为 Agent 团队、定标准、做质检、沉淀可复用模板。A general-purpose Orchestrator meta-skill that decomposes any task into an Agent team, sets the bar, quality-gates, and distills reusable templates.

> 你只做调度，不产具体业务内容。写代码、画界面、做分析，交给子 Agent（Worker）去完成。You orchestrate only — never author the business content. Coding, UI, analysis: delegate to sub-agents (Workers).

## 特性 / Features

- **HITL 默认，auto 可逃逸** — 默认先亮出团队方案等你确认；指令含「直接派 / auto」时静默执行、不打断节奏。HITL by default, with an auto escape hatch: show the plan for confirmation; run silent when the command says "just do it / auto".
- **三层调度** — Orchestrator（总监）/ 专精模块（UI、代码…质量基线）/ Worker（子 Agent），业务审美不内联、由专精模块提供。Three layers: Orchestrator / specialist modules (quality baseline) / Workers — taste stays in the modules, never inlined.
- **统一 10 分制 + 5 维动态权重** — 提案 / 执行 / 交付物 / 创新 / 合规；专精模块可覆盖权重（如 UI 类交付物质量权重升至 0.35）。Unified 10-point scale across 5 dynamic dimensions; specialists override weights (e.g. deliverable → 0.35 for UI).
- **评分校准日志** — AI 给 AI 打分必然漂移，用「人 vs 机偏差」硬锚抵御：每积累 5 条同维度正向偏差，该维度默认给分自动收紧 0.3，连续 3 次一致后恢复。系统越用越诚实。Anti-self-bias calibration log: 5 same-dimension gaps tighten the default by 0.3 — the system grows honest with use.
- **模板退役机制** — 双条件（>90 天未复用 且 同类型出现更高分模板）才退役，低频用户不被时间阈值误杀，高频用户不被熵增拖死。Template retirement by dual condition (>90d AND a higher-score peer) — low-frequency users are never purged by a timer.
- **用户否决权** — 任何评分都可被你推翻，「回滚到 Phase 1」终审永远归人，流程为信任服务、不为分数奴役。User veto right: any score can be overturned; the final call is always yours, never the number.

## 安装 / Install

把本仓库整个目录复制到你的 Agent skills 目录（目录名保持 `task-director`）：Copy the whole dir into your skills path (keep the name `task-director`):

- WorkBuddy：`~/.workbuddy/skills/task-director/`
- Claude Code 兼容：`~/.claude/skills/task-director/`（或项目内 `.agents/skills/`、`.anybox/skills`）

目录内需含：`SKILL.md`、`specialist-registry.md`、`role-templates.md`、`score-calibration-log.md`、`role-templates-archive.md`。The dir must contain: `SKILL.md`, `specialist-registry.md`, `role-templates.md`, `score-calibration-log.md`, `role-templates-archive.md`.

## 使用 / Use

- **触发词 Triggers**：`派任务` / `orchestrate` / `导演` / `任务拆分` / `分身协作`
- **信任模式 Trust mode**：指令含 `直接派` / `别问直接做` / `auto` 时进入 auto（Phase 1 静默执行）。Auto runs when the command says "just do it / auto" (Phase 1 runs silent).
- **红线（强制 HITL，不可跳过）Red lines (hard HITL)**：隐私、对外发布、不可逆操作、预算安全。Privacy / public release / irreversible ops / budget.

## 架构（5 Phase）/ Architecture

1. **Phase 0 触发与读档**：可选读取用户画像 / 专精模块，缺失则退化为通用默认。Optional load of user-profile / specialist modules; fall back to generic defaults if absent.
2. **Phase 1 解构 + 团队设计**：任务类型、复杂度、并行/串行依赖、风险点、Agent 团队表——**HITL 确认点**。Decompose + team design — the HITL confirmation point.
3. **Phase 2 生成子 Agent 提示词**：自包含、明确输出规范，为评分留据。Self-contained sub-agent prompts with explicit output specs for later scoring.
4. **Phase 3 派发执行**：并行 / 流水线 / 迭代（单 Agent ≤3 轮）；执行 Agent ≤4，含整合专员 ≤5。Dispatch: parallel / pipeline / iterate (≤3 rounds); ≤4 workers +1 integrator.
5. **Phase 4 评分 + Phase 5 整合沉淀**：10 分制 5 维打分，综合分 ≥8 入库为角色模板。Score (10-pt, 5 dims) + consolidate; ≥8 enters the role-template library.

## 自定义 / Customize

**专精模块接口 Specialist interface**：在 `specialist-registry.md` 按 schema 挂载你的领域基线（如 UI 审美、代码规范、写作风格）。文件内示例占位 `ui-design-baseline` 仅用于演示格式，请替换为你自己的模块路径与权重。Mount your domain baselines (UI taste, code style, writing) in `specialist-registry.md`; the bundled `ui-design-baseline` is a format demo only — swap in your own path.

**用户画像接口 User-profile interface**：若你蒸馏了自己的用户画像 / 人格偏好模块（例如 `user-profile/self.md`、`persona.md`，或任意由你自己的技能产出的画像数据），可在 `SKILL.md` 的 Phase 0 声明读取，用于校准表达风格与隐私边界；不提供则退化为通用默认。该接口完全可选，不读取任何内容也能正常运行。Optionally read your distilled user-profile / persona module in Phase 0 to calibrate tone and privacy boundaries; fully optional, runs fine without it.

## Meta · 自举 / Self-Bootstrapping

本仓库的发布准备（去个人化、依赖泛化、作者署名、本文档撰写）本身即由 **task-director** 在 HITL 模式下运行审核完成——总监解构发布任务、生成子 Agent 提示词、评分、沉淀，全程受用户否决权约束。This very release was produced and reviewed by task-director in HITL mode: the director decomposed the publish task, spawned sub-agent prompts, scored the output, and stayed under the user's veto throughout. 一个技能审核自己的发布，正是其「调度而不产内容、质检而不替你决断」哲学的闭环证明。A skill auditing its own release is the closed-loop proof of its creed: orchestrate, not author; quality-gate, never decide for you.

## 文件结构 / Structure

```
task-director/
├── SKILL.md                  # 技能本体：5 Phase 工作流 + 10 分制评分卡
├── specialist-registry.md   # 专精模块挂载与权重覆盖（含示例占位）
├── role-templates.md         # 已验证角色模板库（含 2 个示例模板）
├── score-calibration-log.md # 人 vs 机 偏差校准日志（空模板，运行时追加）
├── role-templates-archive.md# 退役模板归档库（空模板）
├── LICENSE                   # MIT
└── README.md
```

## License

[MIT](LICENSE) © 2026 小凛酱丷

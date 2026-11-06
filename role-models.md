---
role_models_version: "1.0.0"
probe_timeout_seconds: 3
blacklist_ttl_minutes: 15
rotation_state_file: ".task-director-rotation.json"
---

# 角色模型池 · 跨供应商轮换

这是本技能的**路由配置**，不是角色模板。改它等于改整个技能的派发行为，须在 HITL 下确认。选型规则见 `SKILL.md` §「供应商与模型族约束（异族互审）」；机器可读的候选池同步存一份在 `./scripts/model-pool.example.json`，参考实现 `./scripts/cross_model_router.py` 直接读取它。

## 成本档定义

| 档位 | 用途 | 典型模型 | 约束 |
|------|------|----------|------|
| `free` | 极简任务、探针、草稿 | `loomy/spark-x2.6` | 免积分，但能力有限 |
| `cheap` | 简单任务、格式化、小改 | `codearts/deepseek-v4.1-flash-1017`、`trae/deepseek-v4.1-flash` | 免费额度多，跑量首选 |
| `mid` | 标准任务、普通代码、写作 | `qwen3.8-flash`、`glm-5.3-flash` 两个 provider | 主力档 |
| `strong` | 复杂推理、硬骨头代码 | `buddy/deepseek-v4.1-flash`、`magicrew/deepseek-v4.1-flash` | 少用，按需 |
| `pro` | **任何任务禁用** | 各 provider 的 `*-pro` | 烧积分；选型时整体排除 |

## 候选池

同一模型族尽量挂在不同供应商上，异族配对才有余量。**族名 = 归一化后的模型 id**（去 provider 前缀、小写、`-`→`.`、去尾 4 位日期）。

| provider | model | tier | 族 | 备注 |
|----------|-------|------|----|------|
| `loomy` | `spark-x2.6` | free | `spark.x2.6` | 免积分兜底；输出短，适合探针与小改 |
| `codearts` | `deepseek-v4.1-flash-1017` | cheap | `deepseek.v4.1.flash` | 免费额度多；曾出现 403，需探针把关 |
| `trae` | `deepseek-v4.1-flash` | cheap | `deepseek.v4.1.flash` | 稳定主力 |
| `loomy` | `qwen3.8-flash` | mid | `qwen3.8.flash` | 中文写作与普通代码较好 |
| `trae` | `qwen3.8-flash` | mid | `qwen3.8.flash` | 同上，另一渠道 |
| `trae` | `glm-5.3-flash` | mid | `glm.5.3.flash` | 评审偏好：挑刺稳，少顺着对方思路走 |
| `loomy` | `GLM-5.3-Flash` | mid | `glm.5.3.flash` | 同上，另一渠道；大小写不影响族判定 |
| `buddy` | `deepseek-v4.1-flash` | strong | `deepseek.v4.1.flash` | 快，复杂任务留用 |
| `magicrew` | `deepseek-v4.1-flash` | strong | `deepseek.v4.1.flash` | 备用渠道 |
| `buddy` | `deepseek-v4.1-pro` | pro | `deepseek.v4.1.pro` | **禁用**；留在池里只为如实反映账号能力 |

> 加候选时注意：只在**同一 provider**里堆某个族的模型，不会增加异族余量。异族余量由「不同 provider × 不同族」的笛卡尔积决定。

## 复杂度映射与降级顺序

| 任务复杂度 | 首选档 | 降级顺序（仅放宽成本，永不放宽族，永不启用 pro） |
|------------|--------|------------------------------------------------|
| 简单 | `free` + `cheap` | 加 `mid` |
| 标准 | `cheap` + `mid` | 加 `free` → 再加 `strong` |
| 复杂 | `mid` + `strong` | 加 `cheap` |

**任务类型偏好**：复杂代码任务优先 `glm` / `qwen` 族；不满足时先放宽族偏好，仍不满足再降档。

## 探针与黑名单

1. **探针**：每个候选在派发前发一次极小请求（≤1 行输出、低 `max_tokens`、超时 `probe_timeout_seconds`）。超时、4xx、5xx、空响应一律判坏。
2. **跳过**：坏候选当次跳过，不再当次重试。
3. **拉黑**：跳过的候选写入黑名单，带 `blacklist_ttl_minutes` 的 TTL（一次抖动不该永久封杀），并累计 `count`。
4. **恢复**：TTL 到期自动放回候选池；连续可用若干次后清空 `count`。
5. **升级信号**：同一候选 `count` ≥ 3 且跨任务复现，应在执行报告里点名，提示用户换渠道或换号。

## 轮换

- 执行者与评审者各有一个持久化游标（`rotation_state_file`），每次派发前进一位，**跨任务持久化**——否则每次重启都从目录第一个开始，等于没轮换。
- 排序不是目录顺序：先按族做轮转交织（`interleave_by_family`），保证相邻候选尽量不同族，再按游标行走。
- 同一任务内多个执行者不得全部落在同一族；否则评审侧异族余量会被吃光。

## 黑名单

运行时追加，格式：

```yaml
---
provider: "codearts"
model: "deepseek-v4.1-flash-1017"
reason: "探针 403"
count: 2
until: "2026-11-07T03:45:00+08:00"
---
```

> 当前无记录。首次探针失败时由总监创建并追加。

## 反包庇说明（写给未来的自己）

同族互评最危险的地方不是它明显放水，而是它**看起来很像认真评审**：顺着对方的框架补全、认可对方的选择、把"没做"说成"没强调"。异族互审的价值就在于——对方的框架对它来说是陌生的，它只能拿质量标准对着产出本身判。

所以规则里所有「降级」都不许碰族与供应商：成本可以谈，包庇不能谈。

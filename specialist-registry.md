---
specialist_registry_version: "1.1.0"
---

# 专精模块注册表

本文件登记可挂载的专精模块（质量基线 + 权重覆盖）。**不捆绑任何具体模块**——下方 `ui-design-baseline` 仅为演示接口格式的示例占位，请替换为你自己的模块路径。

**本文件不决定用哪个模型。** 模型分派走 `role-models.md`（候选池 + 成本档 + 异族互审），与权重覆盖是两件独立的事：权重回答「这一维多重」，路由回答「谁来判这一维」。

## 通用默认权重（未命中任何模块时）
```yaml
dimension_weights:
  proposal: 0.20        # 提案质量
  execution: 0.20       # 执行质量
  deliverable: 0.20     # 交付物质量
  innovation: 0.20      # 创新性
  compliance: 0.20      # 合规性
```

## 已挂载模块（示例占位，请替换为你的实际模块）

### ui-design-baseline（示例占位 · 非实装模块）
- 路径: `../ui-design-baseline/SKILL.md`   # 占位路径，请改为你自己的 UI 专精模块
- 触发领域: `UI` / `前端` / `界面` / `视觉`
- also_serves_as: `"task-director/ui-baseline"`   # 双通道：既作基线，也可独立触发
- 维度权重覆盖:
  ```yaml
  dimension_weights:
    proposal: 0.15
    execution: 0.20
    deliverable: 0.35    # UI 类最重：交付物（原型）质量
    innovation: 0.15
    compliance: 0.15
  ```
- 说明：挂载后，UI 类任务在 Phase 2 引用其审美/Taste 基线，Phase 4 交付物权重升至 0.35。
- **评审模型偏好**：UI 类的「交付物质量」最依赖实证（截图 / 量化读数），建议把该维交给 glm 族评审（挑刺稳、少顺着执行者的设计说明走）；`dimension_weights` 决定这维有多重，异族互审决定谁来判。

## 权重与路由的分工（避免两套规则打架）

| 问题 | 回答在哪 |
|------|----------|
| 五维各占多少权重？ | 本文件 `dimension_weights` |
| 谁是执行者、谁是评审者？ | `role-models.md` 候选池 + `SKILL.md` §供应商与模型族约束 |
| 成本档怎么选？ | `role-models.md` 复杂度映射 |
| 坏模型怎么处理？ | `role-models.md` 探针与黑名单 |
| 同族能不能评？ | **不能**，任何权重设置都不得绕过异族互审 |

**权重可以被专精模块覆盖，异族互审不能被任何模块覆盖。** 专精模块只调「怎么打分」，不调「谁来打分」。

## 预留接口（候选领域，不实装空壳）
- `code-baseline`：代码规范 / 架构审美基线
- `writing-baseline`：写作风格 / 结构基线
- `analysis-baseline`：分析严谨度 / 数据可视化基线
> 待用户提供实际模块后，按上方 schema 登记即可。

## 挂载时不要碰的三件事
1. **不要为「方便」把评审者也写成执行者的模型族**——权重调得再严，同族打分照样放水。
2. **不要用专精模块的 `also_serves_as` 去改路由**——路由只有 `role-models.md` 一个入口。
3. **不要在模块里写死某个 provider**——模型会 403 / 限流 / 下线，写死等于让整条评审链跟着那个 provider 一起挂。

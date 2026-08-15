---
specialist_registry_version: "1.0.0"
---

# 专精模块注册表

本文件登记可挂载的专精模块（质量基线 + 权重覆盖）。**不捆绑任何具体模块**——下方 `ui-design-baseline` 仅为演示接口格式的示例占位，请替换为你自己的模块路径。

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

## 预留接口（候选领域，不实装空壳）
- `code-baseline`：代码规范 / 架构审美基线
- `writing-baseline`：写作风格 / 结构基线
- `analysis-baseline`：分析严谨度 / 数据可视化基线
> 待用户提供实际模块后，按上方 schema 登记即可。

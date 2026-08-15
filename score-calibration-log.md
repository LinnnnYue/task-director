# 评分校准日志（score-calibration-log）

反「自我偏袒」的硬锚。每当用户否决交付，或用户主观满意度与机器分偏差 ≥1 分（机高分、人低满意），追加一条记录（schema 见 SKILL.md 附录 A.3）：

```markdown
---
task: "[任务简述]"
machine_score: 8.5
human_verdict: "reject"      # 用户真实判定：reject/downgrade/accept_low
score_gap: 1.5               # 机分 - 用户隐含分（正数=机偏袒）
root_cause: "[偏差根因]"
date: "2026-08-15"
---
```

量化回灌：每积累 5 条同维度正向偏差，Phase 4 自评该维度默认给分 -0.3；连续 3 次人机组一致后恢复。

> 当前为空，首次校准时由总监创建并追加。

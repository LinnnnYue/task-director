# 退役模板归档库（role-templates-archive）

被 `role-templates.md` 退役机制移入的模板统一存放于此（schema 同主库）。归档非销毁，随时可回捞。

退役触发（双条件）：`last_used` > 90 天 且 同 `task_type` 出现更高分（≥ 旧 +0.5）新模板。

> 当前为空。

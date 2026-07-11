# Golden Sets

一个 AI 场景一个 `<task>.jsonl` 文件，一行一个用例：

```json
{"id": "lead-001", "input": {"requirement_desc": "需要 CRM，预算 20 万，下月上线"}, "expect": {"intent_min": 40, "budget_signal": true}}
```

规则（PLAN.md §3 评测纪律）：

- 每个场景 **≥20 条**，覆盖正例/负例/边界（信息不足、无预算、乱填的垃圾数据）
- 反幻觉用例必须有：输入信息不足时，期望输出明确说"信息不足"而非编造
- 结构化字段用断言判分；生成质量用 LLM-as-judge（judge prompt 也纳入版本管理）
- 改 `backend/app/ai/prompts/` 必跑 `make eval`，通过率下降就回滚或修

规划中的文件（随对应里程碑添加）：

- `lead_scoring.jsonl` — M3
- `account_profile.jsonl` — M4（含"跟进记录 < 3 条不编造"用例）
- `next_action.jsonl` — M5（含"建议必须引用真实跟进内容"用例）
- `script_recommend.jsonl` — M6

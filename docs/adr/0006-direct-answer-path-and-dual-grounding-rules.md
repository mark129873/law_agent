# ADR-0006：直接回答路径与 grounding 双规则

- 状态：Accepted（2026-09-13）
- 关联：legal_agent_phase1_technical_design.md §17、plan.md 决策 D2、BE-036、PRODUCT.md §3

## 背景

旧架构所有问题都走知识库检索，问候/概念解释类问题也会得到"知识库中暂无相关依据，建议咨询专业律师"的机械回复，且校验规则把"无依据必须声明"一刀切套给所有回答。用户决策 D2：一般性问题跳过检索直接回答。

## 决策

1. **直接回答路径**：query_router 识别 general_question/other → orchestrator 选 direct_answer → direct_answer_agent 直接流式回答（不检索）。法律事实型问题默认 local_rag（宁可多检索不可漏依据——router 判定不清时倾向 legal_question）。
2. **grounding 双规则**（与 BE-017 契约对齐）：
   - 检索路径：有证据 → 回答必须含【来源：…】标注；无命中 → 必须声明"知识库中暂无相关依据"；
   - 直接回答路径：只校验"不编造法条/案例编号/精确法律数据"，不要求来源标注与信息不足声明。
   - Web/Plugin 未开通的说明性回答跳过校验（无事实断言）。
3. **流式出口划分**：direct_answer_agent 是直接路径的唯一流式出口；answer_generator_agent 是 finish 路径的唯一流式出口；direct 已有完整草稿时 answer_generator 透传（不重复调模型、不重复推增量）。任何节点再次开始流式前，若 answer_draft 已存在必须先推 regenerating 事件。

## 后果

- 正向：闲聊体验自然（不再机械声明信息不足）；少一次检索调用，直接路径延迟显著低于检索路径。
- 代价：意图路由错误会把法律问题送进直接回答——以 router 提示词倾向 legal_question 缓解，且直接回答路径的 judge 仍会拦"编造法条"。
- 中性：PRODUCT.md §3 已先行更新（生成过程展示、检索策略只出现于检索路径）。

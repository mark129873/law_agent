# AGENTS.md

此项目描述:
-这是一个法律知识库助手agent,根据用户问题, 进行法律问题回答, 并且可以存储用户的问题与回答.


## 开工流程
写代码前先做这些事：
1. 用 `pwd` 确认当前目录。
2. 阅读 docs/ARCHITECTURE.md，了解完整架构与数据流定义
3. 阅读 docs/PRODUCT.md，了解功能需求与用户侧交互行为
4. 阅读 docs/RELIABILITY.md，了解日志、可观测性以及干净环境的相关要求
5. 读取 progress.md，了解最新已验证状态和下一步任务（更早的历史 Session 在 docs/archive/progress-archive-*.md 冷分卷中，按起止序号命名, 按需读取）
6. 查看 feature_list.json，确认当前所有功能的开发进度。**冷热分层不变量：不在 features 中的历史功能条目均为 passing**，完整条目见 docs/archive/feature-archive-*.json, 按需读取；planned / in_progress / blocked / deprecated 的功能必须显式保留在热层
7. 读取 session‑handoff.md 获取记录当前会话的交接摘要, 上一轮开发上下文。
8. 用 `git log --oneline -5` 看最近提交
9. 执行`init.md`的内容, 确保项目可正常构建或启动、初始化无异常。
10. 在开始新功能前，先跑必需的测试与验证, 测试先根据 docs/RELIABILITY.md 进行测试干净环境管理
11. 如果9和10的验证一开始就失败，先修基础状态，不要在坏的起点上继续叠新功能。


## 工作规则
- 新增功能时，请**先更新对应文档，再编写代码**。
- 一次只做一个功能。
- 不要因为“代码已经写了”就把功能标记为完成。
- 除非为了消除当前 blocker 的窄范围修复，否则不要扩大到其他功能。
- 实现过程中不要悄悄改弱验证规则。
- 优先依赖仓库里的持久化文件，而不是聊天记录。

## 功能完成定义
一个功能只有在以下条件都满足时才算完成：
- 目标行为已经实现
- 必要验证真的跑过
- feature_list.json 文件内该功能状态标记为 "passing", 并附上验证证据
- docs/ARCHITECTURE.md 和 docs/PRODUCT.md 文档同步更新
- 所有服务业务操作均配有结构化日志记录
- 仓库仍然能按标准启动路径重新开始工作
- 在工作处于安全状态后, 代码已提交到git仓库, 提交信息清晰，符合项目规范。

## 收尾
结束会话前：
- 更新 `progress.md`
- 更新 `feature_list.json`, 其中evidence字段在300字以内
- 更新 `session‑handoff.md`
- 记录仍未解决的风险或 blocker
- 执行冷热分层沉降检查（规则见下节）
- 确认 clean‑state‑checklist.md 所有校验项通过。
- 在工作处于安全状态后，用清晰的提交信息提交

## 进度文档冷热分层规则
progress.md 与 feature_list.json 采用冷热数据分层，热层只放"当前状态"，历史沉入 `docs/archive/` 冷分卷（分卷生成后只读不改，文件名标注条目起止序号）：

| 文件 | 热层保留 | 沉降触发 | 每批沉降量 | 冷分卷命名 |
|------|---------|---------|-----------|-----------|
| progress.md | 头部状态 + 最近的 Session | Session 数 > 15 | 固定 10 个（最旧的优先） | `progress-archive-{起始}-{结束}.md` |
| feature_list.json | 最近 passing 条目 + 全部非 passing 条目 | passing 条目 > 40 | 固定 20 条（最旧的优先） | `feature-archive-{起始}-{结束}.json` |

- **写 evidence 直接写结论级**（≤200 字：日期 + 关键验证数字 + 结论 + commit/归档指针）；验证过程细节随条目沉降进冷分卷，不写在热层。
- 沉降时 passing 条目**整条原样**搬入新分卷（不精简），并同步递增 feature_list.json 顶层 `archivedPassing.count`；全部功能数 = 热层条目数 + archivedPassing.count，收尾时对账。
- 冷分卷序号连续不重叠；需要历史细节按需读取冷分卷。

## 后端代码规范
- 要求代码必须包含中文注释, 并解释做了什么, 这么做的原因, 涉及的设计模式, 涉及的DDD, OOP原则
- 代码遵循适合的设计模式，如工厂模式、单例模式、策略模式、观察者模式等。
- 代码遵循领域驱动设计（DDD）原则，将业务逻辑与数据访问层分离，保持代码结构清晰。
- 代码遵循面向对象设计（OOP）原则，使用类、对象、继承、多态等概念。

## 前端代码规范
- 要求代码必须包含详细中文注释, 并解释做了什么, 这么做的原因, 适合0基础开发
- 代码要求简洁精炼, 避免使用复杂的语法或模式, 保持代码结构清晰

## 测试数据源
- backend/tests/data_source/ 测试数据源,存放用于测试功能的RAG的法律文档数据


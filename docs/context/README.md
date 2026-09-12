# Harness 设计上下文

这里存放维护本代码仓库所需的长期设计说明。`AGENTS.md` 只保留入口、硬约束和记忆机制；需要具体背景时按主题读取本目录文档。

## 文档索引

- [vision.md](vision.md)：仓库要解决的问题和设计取向。
- [concepts.md](concepts.md)：Workspace、Instance、Provider、Harness、Profile、Capability、Context、Schedule 等概念。
- [target-architecture.md](target-architecture.md)：轻量装配、薄封装、工作区优先的目标架构。
- [current-state.md](current-state.md)：仓库能力、实例清单和当前加密消息面研究实例。
- [harness-design.md](harness-design.md)：当前实现说明，包括现有 harness/profile/instance/schedule 机制；它不等于最终目标架构。

新增主题时，在这里补充索引，并在 `AGENTS.md` 保留稳定入口，不把大段说明重新塞回根文件。

技能根文档只保留触发条件、边界和下一步入口；命令细节放在 `docs/`、CLI `--help`
或脚本中，按任务渐进读取。

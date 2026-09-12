# magellen-trade-harness

`AGENTS.md` 是仓库维护入口；架构和运行细节按需阅读 [`docs/context/`](docs/context/)。

## 工作约定

- 先确认实际问题和重要假设；需求有歧义时再澄清。
- 做最小、局部的改动，沿用现有模式，不顺手重构。
- 使用 `uv run`；不依赖裸 `python -m` 或手工 `PYTHONPATH`。
- 不打印、提交或记录 API key；实例目录和 secrets 文件不提交。
- 交易默认 dry-run；注册、claim 或真实下单遵守已有授权边界。
- 修改后运行相关检查；新增或修改用户可见功能时验证一条端到端路径。

## 上下文与文档

- 低频共享约定留在本文件；机器路径和个人习惯放在未提交的 [`AGENTS.local.md`](AGENTS.local.md)。
- 人类安装和使用说明放在 [`README.md`](README.md)；长期设计说明放在 [`docs/context/`](docs/context/)。
- 改变仓库设计或操作约定时，更新对应的 context 文档。

入口文档：[`docs/context/README.md`](docs/context/README.md)、
[`docs/context/harness-design.md`](docs/context/harness-design.md)、
[`docs/learn/`](docs/learn/)。

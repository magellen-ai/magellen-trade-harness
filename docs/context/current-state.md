# 当前仓库与实例状态（2026-09）

## 仓库目标

本仓库用于创建和长期运行 Trading Agent。Agent 由 runtime harness、可选 provider/model 和具体 workspace 组成；实例是 Agent 配置物化后的工作目录。基础设施以 CLI、skill 和薄 wrapper 提供，市场与供应商之间不强行统一业务接口。

## 当前已具备

- Agent → profile → workspace → instance 初始化链路。
- Provider 配置：`configs/providers/magellen.yaml`，用于需要显式 API endpoint 的模型。
- Harness：Pi、Grok Build、Claude Code 的启动和配置模板。
- CLI 工具：Fuyao、paper-ashare、OKX、ClawStreet、schedule。
- Skill：本地 path 和实例级 npx 安装。
- Schedule：规则校验、reload、tick、journal，以及 Agent 可调用的 `create/list/cancel`。
- 配置层：`runtime.paths` 集中路径、`runtime.config` 统一 YAML/模型引用/跨文件校验，入口为 `harness config check`。
- 上下文生成：技能入口和实例 Tools 索引保持精简，命令细节按需从 CLI/docs 读取；profile 自带边界不会被通用 Rules 重复覆盖。
- 默认 dry-run 和实例隔离。

## 实例清单

| 实例 | 用途 | 运行时 | 状态 |
|---|---|---|---|
| `mres-reuse` | 旧 ClawStreet/Claude 工作区 | Claude Code | 可能仍在使用，勿自动删除 |
| `a-fund` | A 股基本面研究 | Grok Build | 旧实例，建议迁移到 profile 后再决定是否归档 |
| `okx-grok-demo` | OKX 双均线实验 | Grok Build | 实验实例，保留作参考 |
| `crypto-news-demo` | 加密货币消息面策略研究 | Grok Build OAuth | 当前主工作实例 |

已清理明显测试实例：`ashare-demo`、`ashare-pi-test`、`pi-test`。

## 当前研究实例

`crypto-news-demo` 使用 Grok Build 的 host OAuth 登录，不配置 provider 或 model。工作区只提供 OKX 查询、schedule 和 Markdown memory；当前不真实下单。

研究重点是把“消息”变成可验证、可复盘的策略假设，而不是追逐单条新闻。每条记录应保留来源、时间、资产、可信度、传导路径、预期持有期、失效条件和事后结果。研究中应同时积累正例、负例和未交易样本，避免只记录成功故事。

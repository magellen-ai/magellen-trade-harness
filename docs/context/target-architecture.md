# 目标架构：轻量装配的 Agent 工作区

## 分层

```text
配置目录
  └─ 初始化实例工作区
       ├─ runtime harness（Pi / Grok / Claude）
       ├─ 工具与 skill（市场、研究、交易、回测）
       ├─ 工作区提示词（AGENTS.md / CLAUDE.md）
       ├─ memory / research / audit
       └─ schedule 工具与运行器
```

代码实现对应四个边界：

- `runtime.paths` 只负责仓库、配置和实例路径；
- `runtime.config` 负责 YAML I/O、递归合并、模型引用和跨文件校验；
- `runtime.instance` 负责把装配结果物化为实例目录，并保留旧 CLI 的兼容入口；
- `runtime.tools` 只登记能力元数据，业务 CLI 仍由 `brokers/`、`marketdata/` 和
  `competitions/` 自己维护；`runtime.schedule` 只负责规则编译和执行。
- `runtime.schedule_schema` 保存无副作用的 interval/cron 解析逻辑，避免调度
  运行器同时承担时间表达式实现。

`uv run harness config check` 是所有配置进入实例初始化前的统一检查入口。它只读取
配置，不解析 secrets，也不会触发网络请求。

配置目录只描述可重复初始化所需的装配信息：工具从哪里来、放到哪里、需要哪些环境变量、如何启动，以及默认调度动作如何绑定到某个 runtime。

投资实例的个性主要存在于工作区文件中，包括：

- 投资目标与边界；
- 研究和决策循环；
- 可用工具的使用说明；
- 风险规则和人工授权规则；
- 记忆文件的组织方式；
- Agent 自己形成的长期工作习惯。

## 基础设施的形态

基础设施不以“所有市场统一接口”为目标。不同市场的数据语义、交易规则和研究流程可能完全不同，强行统一会把复杂度转移到适配层。

优先采用以下形态：

- 一个可靠的 CLI；
- 一个配套 skill，说明参数、语义、限制和例子；
- 必要时一个薄 wrapper，负责鉴权、格式转换、日志或安全闸门；
- 原始数据流或供应商特有能力保留在其自身边界内。

只有当重复实现已经造成明显问题时，才提升为共享库或更高层抽象。

## Agent 与调度的关系

Agent 不必返回由系统解析的固定决策对象。系统应提供它可以调用的调度工具，例如：

```text
./bin/schedule create --at ... --prompt ...
./bin/schedule create --after ... --prompt ...
./bin/schedule cancel ...
```

Agent 完成当前工作后，可以直接创建下一次研究、复盘、风险检查或事件触发任务。调度系统负责持久化、唤醒、并发控制和审计；任务内容仍然是 Agent 可读的 prompt/context，而不是框架预先定义的状态机。

## 当前阶段不做的事

- 不为所有市场定义统一的 market data interface；
- 不把 strategy、mandate、risk、research workflow 全部变成配置 schema；
- 不要求每次 Agent 唤醒都输出固定 JSON；
- 不提前建设完整的投资组合状态领域模型；
- 不把某个 runtime、交易所或数据供应商提升为平台核心。

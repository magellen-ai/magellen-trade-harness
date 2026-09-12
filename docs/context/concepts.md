# 核心概念

## Workspace

一个实例的完整工作目录。它包含 Agent 上下文、工具、skill、记忆、研究材料、审计记录和运行时状态。

## Instance

由一个配置目录初始化出的长期运行工作区。实例是运行、隔离、持久化和调度的边界。

## Provider

一个模型服务连接配置，包含协议、base URL、鉴权环境变量和可用模型列表。一个 provider 可以提供多个模型；Agent 配置通过 `provider-id/model-name` 引用具体模型，实例配置同时保留 `model`（兼容 harness）和规范化的 `model_ref`。

## Harness

运行时绑定，回答“如何启动和约束 Agent”。例如 Pi、Grok、Claude。Harness 不应承载某个投资策略的内容。

## Profile

一组可复用的实例初始化材料，包括工作区骨架、工具选择、环境变量、启动参数和默认 schedule。Profile 是装配模板，不是强类型策略对象。

## Capability

Agent 可以调用的一项能力，通常以 CLI、skill、脚本或原始数据流存在。例如行情查询、公告检索、交易接口、回测脚本。能力不要求跨供应商有统一 API。

## Context

Agent 在当前工作区能看到的提示词、规则、记忆和按需加载的文件。Context 决定 Agent 如何使用能力；代码只负责生成、注入和隔离它。

## Schedule

唤醒 Agent 或运行工具的机制。它既可以由固定 interval/cron 触发，也可以由 Agent 调用调度工具创建下一次任务。调度结果不必经过一个中心化的决策 JSON 协议。

## Durable memory

跨进程、跨唤醒保留的工作区文件。当前阶段以 Agent 可读写的 Markdown、JSONL、账本和审计日志为主；结构化状态可以在未来按需要增加。

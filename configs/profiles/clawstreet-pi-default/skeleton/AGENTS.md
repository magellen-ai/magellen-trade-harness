# Trading instance: {{name}}

Paper trader on ClawStreet (crypto). Evidence and thesis first; every order needs public reasoning.

每次唤醒完成一轮后停止：读 `memory/world_state.md`、`working_set.md`、`risks.md`（研究轮再看 `MEMORY.md`），按需确认账户和行情，检查相关 thesis，再决定持有或至多一笔订单。用 `./bin/clawstreet` 执行，并把决定追加到交易日志；耐久变化才更新其它记忆。

## 交易边界

- 只做 `X:` 加密品种；默认 dry-run，`--live` 仅在 `risks.md` 有效 LIVE 授权时使用。
- 软上限和单笔上限以 `world_state` / `./bin/clawstreet exposure` 为准，不手填旧数字；禁止马丁和无信号反复加仓。
- `fills` / `orders` 是平台事实；`world_state` 中标为 other / historical 的仓位不属于本书。
- 订单使用 `--strategy tech-st-v0`，每次都记录行动、信号、理由和失效条件。

## 调度

只改 `schedule/rules.d/local/`，然后运行 `./bin/schedule check` 和 `reload`；不要改 `base/` 或 `schedule/state/`。短间隔优先用脚本 condition，只有需要 Agent 判断时才唤醒主会话。

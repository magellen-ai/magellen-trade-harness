# OKX — 生产级交易服务层 + 薄 CLI

对接欧易 OKX API v5。与 `paper_ashare` / `clawstreet` 不同：这是**真交易所能力面**（普通单 + 策略单/止盈止损等），不是本地纸面玩具。

默认走**模拟盘**（`x-simulated-trading: 1` / `OKX_SIMULATED=1`）。写操作仍默认 dry-run，需显式 `--live` 才发往 OKX。

## 分层

| 层 | 路径 | 给谁用 |
|----|------|--------|
| **Service** | `brokers.okx.OkxService` + `types` | 量化程序、脚本、agent skills — **首选** |
| **REST** | `brokers.okx.OkxRestClient` | 需要打未封装端点时 |
| **CLI** | `uv run okx …` | 人工 / agent 命令行；薄封装，无额外业务逻辑 |

```python
from brokers.okx import OkxService, OrderRequest, stop_loss, oco_tp_sl

svc = OkxService.from_env()  # 默认 simulated=True

# 普通单
svc.place_order(
    OrderRequest(inst_id="BTC-USDT", side="buy", sz="0.001", td_mode="cash", ord_type="market"),
    dry_run=False,  # 发到模拟盘
)

# 止损（conditional algo）
svc.place_stop_loss(
    inst_id="BTC-USDT", side="sell", sz="0.001", trigger_px="50000", dry_run=False
)

# OCO 止盈+止损
svc.place_oco_tp_sl(
    inst_id="BTC-USDT",
    side="sell",
    sz="0.001",
    tp_trigger_px="70000",
    sl_trigger_px="50000",
    dry_run=False,
)
```

## 密钥

在 `instances/<name>/agent/secrets.env`（或 legacy `~/.config/magellen-trade-harness/secrets.env`）：

```bash
OKX_API_KEY=...          # 也认 OKX_APIKEY
OKX_API_SECRET=...       # 不要写成 OKX_API_SECRET=="..."（多一个 = 会导致签名失败）
OKX_PASSPHRASE=...
OKX_SIMULATED=1          # 模拟盘 Key 时用 1；实盘 Key 必须改 0
OKX_HTTP_PROXY=http://127.0.0.1:7890   # 直连 www.okx.com 超时时常需要
```

模拟盘 Key：OKX 网页先进入 **模拟交易**，再在该模式下创建 API。与实盘 Key **不是同一套**。  
用实盘 Key 却带 `x-simulated-trading: 1` → `50101 APIKey does not match current environment`。

## CLI

```bash
uv run okx status
uv run okx balance
uv run okx positions --inst-type SWAP
uv run okx ticker BTC-USDT

# 默认 dry-run（只打印将要发送的 payload）
uv run okx order place --inst-id BTC-USDT --side buy --sz 0.001 --td-mode cash --ord-type market

# 真正发到模拟盘
uv run okx order place --inst-id BTC-USDT --side buy --sz 0.001 --td-mode cash --live

# 限价 + 附带 TP/SL（attachAlgoOrds；若交易所拒单可改用 algo 子命令）
uv run okx order place --inst-id BTC-USDT --side buy --sz 0.001 --ord-type limit --px 60000 \
  --tp-trigger 65000 --sl-trigger 55000 --live

# 策略单：止损 / 止盈 / OCO
uv run okx algo sl  --inst-id BTC-USDT --side sell --sz 0.001 --trigger-px 50000 --live
uv run okx algo tp  --inst-id BTC-USDT --side sell --sz 0.001 --trigger-px 70000 --live
uv run okx algo oco --inst-id BTC-USDT --side sell --sz 0.001 \
  --tp-trigger 70000 --sl-trigger 50000 --live

uv run okx orders
uv run okx fills
uv run okx algos --ord-type conditional
uv run okx http-docs
```

永续示例：`--inst-id BTC-USDT-SWAP --td-mode cross`（按账户模式可能还要 `--pos-side`）。

## 已覆盖能力（服务层）

- 账户：`status` / `balance` / `positions` / `account_config`
- 行情：`ticker` / `instruments`（公有）
- 普通单：市价/限价/post_only/IOC/FOK；撤单；改单；查询；挂单/历史；成交
- 策略单：conditional（止盈或止损）、OCO、trigger、trailing、iceberg、TWAP；撤单；挂单/历史
- 入口附带 TP/SL：`AttachTpSl` → `attachAlgoOrds`（交易所侧能力；失败时用独立 algo）
- `extra=` 透传未建模字段，避免每次等类型扩展

## 安全约定

| 开关 | 含义 |
|------|------|
| `OKX_SIMULATED=1`（默认） | 请求带模拟盘 header；用 Demo Key |
| `--live` / `dry_run=False` | 真的发请求（仍可能是模拟盘） |
| `--live-env` / `OKX_SIMULATED=0` | 去掉模拟盘 header → **实盘**；需 live Key |

量化程序应：`OkxService.from_env(simulated=True)` 验证策略，再显式切 live。

## 非目标（本轮）

- WebSocket 私有推送 / 行情流（可后加 transport）
- 统一抽象成跨所 `Broker` 接口（先把 OKX 做厚；币安另接）
- 自动风控引擎（仓位限额等由上层策略负责）

文档：https://www.okx.com/docs-v5/zh/

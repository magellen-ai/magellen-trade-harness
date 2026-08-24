# 同花顺金融数据 API（Fuyao / HiThink）

只读行情与研究数据。**不能下单。** 交易用 `paper-ashare` / `clawstreet`。

- Base URL: `https://fuyao.aicubes.cn`
- 鉴权头: `X-api-key: <key>`
- 签发 Key: <https://fuyao.aicubes.cn/admin/>
- 环境变量（任一即可）: `HITHINK_FINANCE_API_KEY` / `FUYAO_API_KEY`
- 写入位置: `instances/<name>/agent/secrets.env`（勿打印、勿提交）

## CLI

```bash
uv run fuyao ping
uv run fuyao quote 600519.SH 000001.SZ
uv run fuyao search 茅台
uv run fuyao bars 600519 --days 30
uv run fuyao calendar
uv run fuyao http-docs
```

## 常用 HTTP

```bash
# 快照
curl 'https://fuyao.aicubes.cn/api/a-share/prices/snapshot?thscodes=600519.SH' \
  -H 'X-api-key: <your-api-key>'

# 日 K（start/end 为毫秒 Unix）
curl 'https://fuyao.aicubes.cn/api/a-share/prices/historical?thscode=600519.SH&interval=1d&start=…&end=…&adjust=forward' \
  -H 'X-api-key: <your-api-key>'

# 标的检索
curl 'https://fuyao.aicubes.cn/api/meta/tickers/search?q=茅台&limit=10' \
  -H 'X-api-key: <your-api-key>'
```

## MCP（Agent 可选）

官方 MCP 与 REST 同 Key，见 <https://fuyao.aicubes.cn/docs/mcp/overview/>。  
本仓库默认路径仍是 CLI（`uv run fuyao`），便于与 schedule / 实例包装对齐。

## 说明

- 业务错误多半 HTTP 200 + JSON `code != 0`（如 2001 缺 Key、2003 无权限）。
- `thscode` 需带交易所后缀（`600519.SH`）；CLI 对 6 位数字会按沪/深启发式补全。
- 完整文档: <https://fuyao.aicubes.cn/docs/> · `llms.txt`: <https://fuyao.aicubes.cn/llms.txt>

# 美股 ↔ Binance 合约 资金费率套利 (Funding Rate Arbitrage)

**策略**：通过 Bit.com 接口买入美股正股（LONG）+ 做空 Binance 同名永续合约（SHORT），赚取资金费率。

## 原理

Binance 上线了许多美股代币化合约（如 MUUSDT、AAPLUSDT、TSLAUSDT），其价格跟踪对应美股。永续合约每 8 小时结算一次资金费率（Funding Rate）：

- **资金费率 > 0**：多头支付给空头 → 持有空头仓位**赚取**费率
- **资金费率 < 0**：空头支付给多头 → 持有空头仓位**亏损**费率

**套利逻辑**：
1. 通过 **Bit.com Stock API** 买入正股（如 MU）→ 持有多头头寸
2. 在 **Binance** 做空同名永续合约（如 MUUSDT）→ 持有空头头寸
3. 两边对冲，价格涨跌不影响总头寸 → **纯赚资金费率**

## 执行策略：Maker-First（费率优化）

| 平台 | Maker 费率 | Taker 费率 |
|------|-----------|-----------|
| Binance TradFi 合约 | **0%** | 0.04% |
| Bit.com 美股 | ~0.01% | ~0.01% |

为了最小化交易费用，执行顺序为：

1. **先在 Binance 挂 Maker 限价单**（postOnly=true，保证 0% 手续费）
2. **等待 Binance 成交**（轮询订单状态，超时自动撤单）
3. **成交后立即在 Bit.com 下 Taker 市价单**（~0.01% 手续费）

这样总手续费仅 **~0.01%**，而不是 Binance taker 的 0.04%。

## 交易接口

| 功能 | 平台 | API |
|------|------|-----|
| 买卖美股 (taker) | Bit.com (Matrixport) | `https://mapi.matrixport.com/stock/v1/...` |
| 做空合约 (maker) | Binance | ccxt 库 (postOnly) |

Bit.com Stock API 文档: https://www.bit.com/docs/en-us/stock.html#stock-api

## 支持的交易对

| 美股 (Bit.com) | Binance 合约 | 说明 |
|---------------|-------------|------|
| MU.US   | MUUSDT      | Micron Technology |
| AAPL.US | AAPLUSDT    | Apple |
| TSLA.US | TSLAUSDT    | Tesla |
| AMZN.US | AMZNUSDT    | Amazon |
| GOOG.US | GOOGUSDT    | Alphabet |
| COIN.US | COINUSDT    | Coinbase |
| MSTR.US | MSTRUSDT    | MicroStrategy |
| NVDA.US | NVDAUSDT    | Nvidia |
| META.US | METAUSDT    | Meta |
| MSFT.US | MSFTUSDT    | Microsoft |

> 可在 `config.py` 中自由添加/删除交易对。

## 安装

```bash
cd arbitrage
pip install -r requirements.txt
```

## 配置

```bash
cp .env.example .env
# 编辑 .env 填入 Bit.com 和 Binance 的 API key
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BITCOM_ACCESS_KEY` | - | Bit.com Stock API Access Key |
| `BITCOM_SECRET_KEY` | - | Bit.com Stock API Secret Key |
| `BITCOM_BASE_URL` | `https://mapi.matrixport.com` | Bit.com API 基础 URL |
| `BINANCE_API_KEY` | - | Binance API Key |
| `BINANCE_API_SECRET` | - | Binance API Secret |
| `BINANCE_TESTNET` | `true` | 是否使用 Binance 测试网 |
| `MIN_FUNDING_APY` | `10.0` | 最低年化收益率阈值（%），低于此值不建议入场 |
| `MAX_BASIS_PCT` | `1.0` | 最大可接受基差（%），基差过大时不建议新开仓 |
| `DEFAULT_TRADE_QTY` | `10` | 每笔交易默认股数 |
| `POLL_INTERVAL` | `10` | 轮询间隔（秒） |
| `MAKER_ORDER_TIMEOUT` | `60` | Binance maker 单等待成交超时（秒），超时自动撤单 |
| `MAKER_POLL_INTERVAL` | `0.5` | 轮询 Binance 订单成交状态的间隔（秒） |
| `LOG_LEVEL` | `INFO` | 日志级别 |

## 使用

```bash
# 持续监控（Ctrl+C 停止）
python main.py

# 单次快照
python main.py --once

# 输出到 CSV 文件
python main.py --csv spreads.csv

# 🔴 开启实盘交易（自动开平仓）
python main.py --trade

# 查看当前持仓（Bit.com + Binance）
python main.py --positions
```

## 运行模式

### 监控模式（默认）
仅显示行情 + 信号，不下单。适合观察和调参。

### 交易模式 (`--trade`)
根据信号自动执行（Maker-First 策略）：
- **ENTER 信号** → ① 在 Binance 挂 maker 限价空单 → ② 等待成交 → ③ 在 Bit.com taker 市价买入正股
- **EXIT 信号** → ① 在 Binance 挂 maker 限价买回平仓 → ② 等待成交 → ③ 在 Bit.com taker 市价卖出正股

如果 Binance maker 单在 `MAKER_ORDER_TIMEOUT` 秒内未成交，自动撤单，不执行美股侧。

### 持仓查看 (`--positions`)
显示两个平台的当前仓位，确认对冲是否平衡。

## 信号说明

| 信号 | 含义 | 操作建议 |
|------|------|----------|
| 🟢 **ENTER** | 资金费率年化 ≥ 阈值 且 基差 ≤ 阈值 | 可以开仓：买入正股 + 做空合约 |
| 🟡 **HOLD** | 资金费率好但基差偏大 | 已有仓位可继续持有，不建议新开仓 |
| 🔴 **EXIT** | 资金费率为负（空头需支付费率） | 建议平仓止损 |
| ⚪ **UNFAVORABLE** | 条件不满足 | 观望 |

## 输出示例

```
╔══════════════════════════════════════════════════════════════════╗
║  Funding-Rate Arbitrage: LONG Stock (Bit.com) + SHORT Binance  ║
╚══════════════════════════════════════════════════════════════════╝
  Pairs: 10  |  Min APY: 10.0%  |  Max Basis: 1.0%  |  Interval: 10s
────────────────────────────────────────────────────────────────
[2026-05-24 13:30:00 UTC]  MU     Stock $    98.50  Futures $    98.80  │  Basis +0.30%  │  FR +0.0150%  APY +16.4%  AvgAPY +14.2%  Next 08:00 UTC  │  ENTER
[2026-05-24 13:30:00 UTC]  TSLA   Stock $   250.00  Futures $   251.50  │  Basis +0.60%  │  FR +0.0080%  APY +8.8%   AvgAPY +9.1%   Next 08:00 UTC  │  UNFAVORABLE

  ✅ 1 pair(s) with ENTER signal

  📈 Opening position: MU ...
  [13:30:01 UTC] OPEN MU  Stock: Buy 10sh @98.50 (id=701276261045858304)  |  Futures: sell 10.0000 @98.80 (id=abc123)  |  ✅ SUCCESS
```

## 文件结构

```
arbitrage/
├── main.py            # 入口：命令行参数解析 + 主循环 + 交易执行
├── config.py          # 配置：API key、交易对、策略参数
├── bitcom_client.py   # Bit.com Stock API 客户端（下单/撤单/查仓位/行情）
├── price_fetcher.py   # 数据获取：Bit.com 股价 + Binance 合约价格/费率
├── spread_monitor.py  # 基差计算 + 费率年化 + 信号生成
├── trader.py          # 交易执行：开仓/平仓（买股票 + 空合约）
├── requirements.txt   # Python 依赖
├── .env.example       # 环境变量模板
└── README.md          # 本文档
```

## Bit.com Stock API 接口说明

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 下单 | POST | `/stock/v1/place_order` | 买入/卖出股票 |
| 撤单 | POST | `/stock/v1/cancel_order` | 取消未成交订单 |
| 查询订单 | GET | `/stock/v1/open_orders` | 获取挂单列表 |
| 查询持仓 | GET | `/stock/v1/positions` | 获取股票持仓 |
| 实时报价 | GET | `/stock/v1/quote` | 获取股票实时价格 |
| 账户信息 | GET | `/stock/v1/account` | 获取账户余额 |

认证方式：HMAC-SHA256 签名，通过 `X-MatrixPort-Access-Key` / `X-MatrixPort-Signature` / `X-MatrixPort-Request-Timestamp` 请求头传递。

## ⚠️ 风险提示

本脚本仅用于学习和研究目的，**不构成投资建议**。风险包括：
- **基差风险**：股价和合约价格可能出现偏离
- **费率波动**：资金费率随时可能变为负值
- **执行风险**：两个市场交易时间不同步（美股有开盘/收盘时间）
- **汇率风险**：美股以 USD 计价，Binance 合约以 USDT 计价
- **合约流动性**：某些美股合约在 Binance 上流动性可能不足
- **杠杆风险**：Binance 合约涉及保证金，需注意爆仓风险
- **单腿风险**：如果一边下单成功另一边失败，会产生敞口

建议先在测试网（Testnet）上验证策略。`--trade` 模式请谨慎使用！

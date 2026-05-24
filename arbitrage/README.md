# 美股 ↔ Binance 合约 资金费率套利 (Funding Rate Arbitrage)

**策略**：持有美股正股（LONG）+ 做空 Binance 同名永续合约（SHORT），赚取资金费率。

## 原理

Binance 上线了许多美股代币化合约（如 MUUSDT、AAPLUSDT、TSLAUSDT），其价格跟踪对应美股。永续合约每 8 小时结算一次资金费率（Funding Rate）：

- **资金费率 > 0**：多头支付给空头 → 持有空头仓位**赚取**费率
- **资金费率 < 0**：空头支付给多头 → 持有空头仓位**亏损**费率

**套利逻辑**：
1. 在美股市场**买入**正股（如 MU）→ 持有多头头寸
2. 在 Binance **做空**同名永续合约（如 MUUSDT）→ 持有空头头寸
3. 两边对冲，价格涨跌不影响总头寸 → **纯赚资金费率**

## 支持的交易对

| 美股 | Binance 合约 | 说明 |
|------|-------------|------|
| MU   | MUUSDT      | Micron Technology |
| AAPL | AAPLUSDT    | Apple |
| TSLA | TSLAUSDT    | Tesla |
| AMZN | AMZNUSDT    | Amazon |
| GOOG | GOOGUSDT    | Alphabet |
| COIN | COINUSDT    | Coinbase |
| MSTR | MSTRUSDT    | MicroStrategy |
| NVDA | NVDAUSDT    | Nvidia |
| META | METAUSDT    | Meta |
| MSFT | MSFTUSDT    | Microsoft |

> 可在 `config.py` 中自由添加/删除交易对。

## 安装

```bash
cd arbitrage
pip install -r requirements.txt
```

## 配置

```bash
cp .env.example .env
# 编辑 .env 填入你的 Binance API key
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BINANCE_API_KEY` | - | Binance API Key |
| `BINANCE_API_SECRET` | - | Binance API Secret |
| `BINANCE_TESTNET` | `true` | 是否使用测试网 |
| `MIN_FUNDING_APY` | `10.0` | 最低年化收益率阈值（%），低于此值不建议入场 |
| `MAX_BASIS_PCT` | `1.0` | 最大可接受基差（%），基差过大时不建议新开仓 |
| `POLL_INTERVAL` | `10` | 轮询间隔（秒） |
| `LOG_LEVEL` | `INFO` | 日志级别 |

## 使用

```bash
# 持续监控（Ctrl+C 停止）
python main.py

# 单次快照
python main.py --once

# 输出到 CSV 文件
python main.py --csv spreads.csv
```

## 信号说明

| 信号 | 含义 | 操作建议 |
|------|------|----------|
| 🟢 **ENTER** | 资金费率年化 ≥ 阈值 且 基差 ≤ 阈值 | 可以开仓：买入正股 + 做空合约 |
| 🟡 **HOLD** | 资金费率好但基差偏大 | 已有仓位可继续持有，不建议新开仓 |
| 🔴 **EXIT** | 资金费率为负（空头需支付费率） | 建议平仓止损 |
| ⚪ **UNFAVORABLE** | 条件不满足 | 观望 |

## 输出示例

```
╔══════════════════════════════════════════════════════════════╗
║   Funding-Rate Arbitrage: LONG Stock + SHORT Binance Perp  ║
╚══════════════════════════════════════════════════════════════╝
  Pairs: 10  |  Min APY: 10.0%  |  Max Basis: 1.0%  |  Interval: 10s
────────────────────────────────────────────────────────────────
[2026-05-24 13:30:00 UTC]  MU     Stock $    98.50  Futures $    98.80  │  Basis +0.30%  │  FR +0.0150%  APY +16.4%  AvgAPY +14.2%  Next 08:00 UTC  │  ENTER
[2026-05-24 13:30:00 UTC]  TSLA   Stock $   250.00  Futures $   251.50  │  Basis +0.60%  │  FR +0.0080%  APY +8.8%   AvgAPY +9.1%   Next 08:00 UTC  │  UNFAVORABLE
```

## 文件结构

```
arbitrage/
├── main.py            # 入口：命令行参数解析 + 主循环
├── config.py          # 配置：API key、交易对、策略参数
├── price_fetcher.py   # 数据获取：Yahoo Finance 股价 + Binance 合约价格/费率
├── spread_monitor.py  # 基差计算 + 费率年化 + 信号生成
├── requirements.txt   # Python 依赖
├── .env.example       # 环境变量模板
└── README.md          # 本文档
```

## ⚠️ 风险提示

本脚本仅用于学习和研究目的，**不构成投资建议**。风险包括：
- **基差风险**：股价和合约价格可能出现偏离
- **费率波动**：资金费率随时可能变为负值
- **执行风险**：两个市场交易时间不同步（美股有开盘/收盘时间）
- **汇率风险**：美股以 USD 计价，Binance 合约以 USDT 计价
- **合约流动性**：某些美股合约在 Binance 上流动性可能不足
- **杠杆风险**：Binance 合约涉及保证金，需注意爆仓风险

建议先在测试网（Testnet）上验证策略。

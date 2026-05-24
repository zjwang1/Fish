# US Stock ↔ Binance Futures Arbitrage Monitor

监控美股（通过 Yahoo Finance）和 Binance 合约之间的价差，当价差超过阈值时发出套利信号。

## 原理

某些美股（如 MSTR、COIN、IBIT、ETHE）的价格与加密货币高度相关。通过对比股票隐含的加密货币价格和 Binance 永续合约的实际价格，可以发现套利机会：

- **正向价差（stock implied > futures）**：做空股票 + 做多合约
- **负向价差（stock implied < futures）**：做多股票 + 做空合约

## 支持的交易对

| 股票 | 合约 | 说明 |
|------|------|------|
| MSTR | BTC/USDT | MicroStrategy 持有大量 BTC |
| COIN | BTC/USDT | Coinbase 与 BTC 价格正相关 |
| IBIT | BTC/USDT | iShares Bitcoin Trust ETF |
| ETHE | ETH/USDT | Grayscale Ethereum Trust |

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

环境变量说明：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BINANCE_API_KEY` | - | Binance API Key |
| `BINANCE_API_SECRET` | - | Binance API Secret |
| `BINANCE_TESTNET` | `true` | 是否使用测试网 |
| `SPREAD_THRESHOLD` | `2.0` | 触发信号的价差阈值（%） |
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

## 输出示例

```
Monitoring 4 pairs | Spread threshold: 2.0% | Interval: 10s
──────────────────────────────────────────────────────────
  MSTR   ↔ BTC/USDT:USDT    hedge_ratio=0.0025  (MicroStrategy vs BTC futures)
  COIN   ↔ BTC/USDT:USDT    hedge_ratio=0.001   (Coinbase stock correlated with BTC)
  IBIT   ↔ BTC/USDT:USDT    hedge_ratio=0.00002 (iShares Bitcoin Trust ETF vs BTC futures)
  ETHE   ↔ ETH/USDT:USDT    hedge_ratio=0.01    (Grayscale Ethereum Trust vs ETH futures)
──────────────────────────────────────────────────────────
[2026-05-24 13:30:00 UTC] MSTR   $    420.50  |  BTC/USDT:USDT  $  68500.00  |  Implied $ 168200.00  |  Spread +145.55%  |  FR 0.0100%  |  Signal: LONG_STOCK_SHORT_FUTURES
```

## 文件结构

```
arbitrage/
├── main.py            # 入口：命令行参数解析 + 主循环
├── config.py          # 配置：API key、交易对定义、阈值
├── price_fetcher.py   # 数据获取：Yahoo Finance + Binance ccxt
├── spread_monitor.py  # 价差计算 + 信号生成
├── requirements.txt   # Python 依赖
├── .env.example       # 环境变量模板
└── README.md          # 本文档
```

## ⚠️ 免责声明

本脚本仅用于学习和研究目的，**不构成投资建议**。套利交易存在风险，包括但不限于：
- 执行延迟导致的滑点风险
- 交易所 API 限流或宕机
- hedge ratio 估算不准确
- 美股与加密货币市场交易时间不同步

请在充分理解风险后谨慎使用。建议先在测试网（Testnet）上验证策略。

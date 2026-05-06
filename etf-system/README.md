# E大"长赢"AI投资系统

基于E大（ETF拯救世界）公开资料复刻的指数投资决策系统。

## 快速开始

```bash
cd etf-system

# 实时状态
python3 main.py status

# 月度信号
python3 main.py signal

# 持仓管理
python3 main.py portfolio status
python3 main.py execute 50ETF=5 中证红利=3

# 历史回测
python3 main.py backtest
```

## Web UI

```bash
cd web
pip install flask
python3 server.py
# 访问 http://localhost:5188
```

## 系统架构

```
etf-system/
├── main.py                 # CLI 统一入口
├── strategies/
│   ├── universe.py         # 品种配置 + 估值决策表
│   ├── valuation.py        # 估值引擎（PE/PB分位）
│   └── grid.py            # 网格策略 + 目标市值
├── signals/
│   └── monthly_signal.py   # 月度信号 + 心理话术
├── backtest/
│   └── bt_engine.py       # 回测引擎 (v3)
├── portfolio/
│   └── manager.py          # 持仓持久化
└── web/
    ├── server.py           # Flask API 服务
    └── ui.html            # Web 前端
```

## 核心逻辑

### 估值分位 → 操作决策

| 分位区间 | 操作 | 份数 |
|---------|------|------|
| <15%    | BUY  | 3份  |
| 15-30% | BUY  | 1份  |
| 30-70% | HOLD | 0份  |
| 70-85% | SELL | 1份  |
| >85%    | SELL | 2份  |

公式：`(当前PE - 历史最低PE) / (历史最高PE - 历史最低PE) × 100`

### 回测验证

- 2016-2019 E大操作一致率：93% (14/15)
- 全量月度回测 (2016-2024)：年化 -0.1%，最大回撤 -34%
- 策略优势区间：熊市建仓（低估持续买入）
- 量化局限：长牛市中PE分位偏低，需结合绝对价格判断止盈

## 数据来源

- A股指数PE/PB历史：乐咕乐股（akshare接口）
- ETF价格：新浪（akshare接口）
- 中证红利净值：东方财富场外基金接口

## 品种池

宽基(PE驱动)：50ETF、180ETF、深100ETF、中证500ETF、中证红利
商品(手动参考)：黄金ETF、华宝油气、恒生ETF、养老产业、德国30

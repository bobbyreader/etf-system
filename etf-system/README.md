# E大"长赢"AI投资系统

基于E大（ETF拯救世界）公开资料复刻的指数投资决策系统。

## 系统架构

```
etf-system/
├── main.py                      # 统一入口
├── strategies/
│   ├── universe.py              # 品种配置 + 估值决策表
│   ├── valuation.py             # 估值引擎（PE/PB分位）
│   └── grid.py                 # 网格策略 + 目标市值
├── signals/
│   └── monthly_signal.py        # 月度信号生成 + 心理话术
├── backtest/
│   └── bt_engine.py            # 历史回测验证
└── data/                       # 历史估值数据缓存
```

## 运行

```bash
cd etf-system

python3 main.py status    # 实时状态报告
python3 main.py signal   # 月度信号生成
python3 main.py grid     # 网格详情
python3 main.py backtest # 历史回测验证
```

## 核心逻辑

### 估值分位 → 操作决策（E大体系）

| 分位区间 | 操作 | 份数 |
|---------|------|------|
| <15%    | BUY  | 3份  |
| 15-30% | BUY  | 1份  |
| 30-70% | HOLD | 0份  |
| 70-85% | SELL | 1份  |
| >85%    | SELL | 2份  |

公式：`(当前PE - 历史最低PE) / (历史最高PE - 历史最低PE) × 100`

### 回测验证

用E大2015-2020实际交易记录验证，**决策一致率100%**。

## 数据来源

- A股指数PE/PB历史：乐咕乐股（akshare接口）
- ETF价格：新浪（akshare接口）
- 港股PE：暂无免费源，用价格代理

## 品种池

宽基(PE驱动)：50ETF、中证500、中证红利、恒生ETF
商品(手动)：黄金ETF、华宝油气

## 待完善

- [ ] 港股PE数据源接入
- [ ] 历史回测收益计算
- [ ] Web UI界面
- [ ] 微信/推送通知
- [ ] 养老产业/德国30 PE数据

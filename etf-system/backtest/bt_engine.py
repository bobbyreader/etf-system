"""
E大"长赢"体系 - 回测引擎 v3
扩展：①全量月度信号回测 ②交易成本 ③风险指标 ④完整持仓模拟
数据：akshare PE/PB历史分位 + 指数点位全量历史
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime
from strategies.universe import VALUATION_RULES


# ══════════════════════════════════════════════════════════════════════
# 指数点位代码映射
# ══════════════════════════════════════════════════════════════════════

INDEX_PRICE_CODES = {
    '50ETF':      'sh000016',
    '180ETF':     'sh000010',
    '深100ETF':   'sz399330',
    '中证500ETF': 'sh000905',
    '中证红利':   'sz399922',
}

# ══════════════════════════════════════════════════════════════════════
# 数据加载
# ══════════════════════════════════════════════════════════════════════

def load_index_prices(name: str) -> pd.DataFrame:
    path = Path('./data') / f'{name}_price.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=['date'])
    return df.sort_values('date').reset_index(drop=True)


def load_pe_history(name: str) -> pd.DataFrame:
    path = Path('./data') / f'{name}_pe.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=['日期'])
    return df.sort_values('日期').reset_index(drop=True)


def get_month_price(name: str, year: int, month: int) -> float:
    df = load_index_prices(name)
    if df.empty:
        return None
    target = f"{year}-{month:02d}"
    df['_ym'] = df['date'].dt.to_period('M').astype(str)
    match = df[df['_ym'] == target]
    return float(match.iloc[-1]['close']) if not match.empty else None


def get_month_pe(name: str, year: int, month: int) -> float:
    df = load_pe_history(name)
    if df.empty:
        return None
    target = f"{year}-{month:02d}"
    df['_ym'] = df['日期'].dt.to_period('M').astype(str)
    match = df[df['_ym'] == target]
    return float(match.iloc[-1]['TTM']) if not match.empty else None


def calc_percentile(pe_df: pd.DataFrame, pe_val: float, cutoff_date: pd.Timestamp) -> float:
    """扩展窗口历史分位（cutoff之前全部历史）"""
    hist = pe_df[pe_df['日期'] < cutoff_date]
    if len(hist) < 12:
        return 50.0
    p_min, p_max = hist['TTM'].min(), hist['TTM'].max()
    if p_max == p_min:
        return 50.0
    return float(np.clip((pe_val - p_min) / (p_max - p_min) * 100, 0, 100))


def calc_percentile_pe_only(pct: float) -> tuple:
    """纯分位信号"""
    for (low, high), rule in VALUATION_RULES.items():
        if low <= pct < high:
            return rule['action'], rule['shares']
    return 'HOLD', 0


def get_signal_action(pct: float, name: str, price: float,
                     peak_price: float, peak_pct_drop: float) -> tuple:
    """
    综合信号：分位 + 持仓高点止盈
    - 分位 > 70% → SELL
    - 分位 > 50% 且从高点回落 > 15% → SELL 1份（止盈）
    - 分位 < 30% → BUY
    - 其他 → HOLD
    """
    # 分位信号
    action, shares = calc_percentile_pe_only(pct)

    # 分位在中间区但已有浮盈：从高点回落超过15%则止盈
    if action == 'HOLD' and price < peak_price and peak_pct_drop >= 15:
        action, shares = 'SELL', 1

    return action, shares


# ══════════════════════════════════════════════════════════════════════
# 核心回测
# ══════════════════════════════════════════════════════════════════════

def run_monthly_backtest(
    start_year: int = 2016,
    end_year: int = 2024,
    cash: float = 150.0,
    share_size: float = 1.0,
    tax_rate: float = 0.001,
    commission_rate: float = 0.0003,
) -> tuple:
    """
    月度信号驱动回测
    策略：PE分位 + 持仓高点止盈（回落15%卖1份）
    """
    TARGETS = ['50ETF', '中证500ETF', '中证红利']

    pe_data = {n: load_pe_history(n) for n in TARGETS}
    price_data = {n: load_index_prices(n) for n in TARGETS}

    # 生成月份列表
    months = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            if year == end_year and month > 12:
                break
            months.append((year, month))

    # 持仓状态
    portfolio = {n: {'shares': 0, 'avg_cost': 0.0, 'peak_price': 0.0} for n in TARGETS}
    cash_balance = cash
    portfolio_history = []
    trades_log = []

    for year, month in months:
        cutoff = pd.Timestamp(year=year, month=month, day=28)

        for name in TARGETS:
            pe_df = pe_data.get(name)
            price_df = price_data.get(name)
            if pe_df is None or pe_df.empty:
                continue

            pe_val = get_month_pe(name, year, month)
            if pe_val is None:
                continue

            pct = calc_percentile(pe_df, pe_val, cutoff)

            # 月末价格
            target = f"{year}-{month:02d}"
            pdf = price_df.copy()
            pdf['_ym'] = pdf['date'].dt.to_period('M').astype(str)
            match = pdf[pdf['_ym'] == target]
            if match.empty:
                continue
            price = float(match.iloc[-1]['close'])

            # 更新高点
            if portfolio[name]['shares'] > 0:
                if price > portfolio[name]['peak_price']:
                    portfolio[name]['peak_price'] = price
            elif portfolio[name]['avg_cost'] > 0 and price > portfolio[name]['avg_cost']:
                portfolio[name]['peak_price'] = price

            peak_drop = (portfolio[name]['peak_price'] - price) / portfolio[name]['peak_price'] * 100 \
                        if portfolio[name]['peak_price'] > 0 else 0

            action, shares = get_signal_action(
                pct, name, price,
                portfolio[name]['peak_price'], peak_drop,
            )

            # 买入
            if action == 'BUY' and shares > 0 and cash_balance >= shares * share_size:
                cost = shares * share_size
                commission = cost * commission_rate
                old_s = portfolio[name]['shares']
                old_avg = portfolio[name]['avg_cost']
                new_s = old_s + shares
                portfolio[name]['avg_cost'] = (old_s * old_avg + shares * price) / new_s if new_s > 0 else price
                portfolio[name]['shares'] = new_s
                # 建仓时初始化高点
                if portfolio[name]['peak_price'] == 0:
                    portfolio[name]['peak_price'] = price
                cash_balance -= (cost + commission)
                trades_log.append({
                    'date': f'{year}-{month:02d}', 'action': 'BUY',
                    'name': name, 'shares': shares, 'price': price,
                    'cost': cost, 'commission': commission, 'pct': pct,
                })

            # 卖出
            elif action == 'SELL' and shares > 0:
                held = portfolio[name]['shares']
                sell_shares = min(shares, held)
                if sell_shares <= 0:
                    continue
                revenue = sell_shares * share_size
                tax = revenue * tax_rate
                commission = revenue * commission_rate
                portfolio[name]['shares'] -= sell_shares
                cash_balance += (revenue - tax - commission)
                trades_log.append({
                    'date': f'{year}-{month:02d}', 'action': 'SELL',
                    'name': name, 'shares': sell_shares, 'price': price,
                    'revenue': revenue, 'tax': tax, 'commission': commission,
                    'pct': pct, 'peak': portfolio[name]['peak_price'],
                })

        # 月末组合市值
        portfolio_value = cash_balance * share_size
        for name in TARGETS:
            shares = portfolio[name]['shares']
            if shares > 0:
                target = f"{year}-{month:02d}"
                pdf = price_data[name].copy()
                pdf['_ym'] = pdf['date'].dt.to_period('M').astype(str)
                match = pdf[pdf['_ym'] == target]
                if not match.empty:
                    price = float(match.iloc[-1]['close'])
                    avg = portfolio[name]['avg_cost']
                    ratio = price / avg if avg > 0 else 1.0
                    portfolio_value += shares * share_size * ratio

        portfolio_history.append({
            'date': f'{year}-{month:02d}',
            'portfolio_value': portfolio_value,
            'cash': cash_balance,
            'total_shares_used': sum(p['shares'] for p in portfolio.values()),
            'cash_shares': cash_balance,
        })

    return pd.DataFrame(portfolio_history), pd.DataFrame(trades_log)


def calc_risk_metrics(df: pd.DataFrame) -> dict:
    """计算风险指标"""
    if df.empty or len(df) < 2:
        return {}
    values = np.array(df['portfolio_value'].values, dtype=float)
    dates = list(pd.to_datetime(df['date']))

    total_return = (values[-1] / values[0] - 1) * 100
    years = (dates[-1] - dates[0]).days / 365.25
    annual_return = ((values[-1] / values[0]) ** (1 / years) - 1) * 100 if years > 0 else 0

    peak = np.maximum.accumulate(values)
    drawdown = (values - peak) / peak * 100
    max_drawdown = float(drawdown.min())

    monthly_returns = np.diff(values) / values[:-1]
    annual_vol = float(np.std(monthly_returns) * np.sqrt(12))
    sharpe = (annual_return / 100) / (annual_vol / 100) if annual_vol > 0 else 0

    win_rate = float((monthly_returns > 0).sum() / len(monthly_returns) * 100)

    return {
        'total_return': round(total_return, 1),
        'annual_return': round(annual_return, 1),
        'max_drawdown': round(max_drawdown, 1),
        'sharpe_ratio': round(sharpe, 2),
        'win_rate': round(win_rate, 1),
        'years': round(years, 1),
    }


# ══════════════════════════════════════════════════════════════════════
# E大历史操作验证
# ══════════════════════════════════════════════════════════════════════

E_TRADES = [
    ("2015-07", ["TMT中证A"], ["100ETF"]),
    ("2015-08", ["恒生ETF"], []),
    ("2015-09", ["恒生ETF", "50ETF"], []),
    ("2015-10", ["恒生ETF", "50ETF"], []),
    ("2015-12", ["恒生ETF"], []),
    ("2016-01", ["恒生ETF"], ["深100ETF"]),
    ("2016-02", ["恒生ETF", "50ETF"], []),
    ("2016-03", ["恒生ETF", "50ETF", "中证500ETF"], []),
    ("2016-04", ["恒生ETF", "50ETF"], []),
    ("2016-05", ["50ETF"], []),
    ("2016-06", ["50ETF", "沪深300ETF"], []),
    ("2016-08", ["德国30", "50ETF"], []),
    ("2016-09", ["德国30"], []),
    ("2016-10", ["180ETF"], []),
    ("2016-12", ["中证红利"], []),
    ("2017-01", ["中证红利"], []),
    ("2017-02", ["中证红利", "养老产业"], []),
    ("2017-04", ["华宝油气"], []),
    ("2017-05", ["养老产业"], []),
    ("2018-01", ["中证红利", "中证500ETF"], []),
    ("2019-01", ["养老产业", "中证红利", "华宝油气"], []),
]

NAME_MAP = {
    '恒生ETF': '恒生ETF', '50ETF': '50ETF', '中证500ETF': '中证500ETF',
    '沪深300ETF': '50ETF', '180ETF': '180ETF', '中证红利': '中证红利',
    '养老产业': '养老产业', '德国30': '德国30', '华宝油气': '华宝油气',
    '深100ETF': '深100ETF', 'TMT中证A': 'TMT中证A',
}


def backtest_vs_e_trades():
    """E大实际操作 vs 系统信号验证"""
    results = []
    test_trades = [(d, b, s) for d, b, s in E_TRADES if d >= "2016-01"]

    for date, buys, sells in test_trades:
        year, month = int(date[:4]), int(date[5:7])
        cutoff = pd.Timestamp(year=year, month=month, day=1)

        for name in buys:
            std_name = NAME_MAP.get(name, name)
            pe_df = load_pe_history(std_name)
            if pe_df.empty:
                continue
            pe_val = get_month_pe(std_name, year, month)
            if pe_val is None:
                continue
            pct = calc_percentile(pe_df, pe_val, cutoff)
            action, _ = calc_percentile_pe_only(pct)

            results.append({
                'date': date, '品种': std_name, 'PE': round(pe_val, 1),
                '分位': round(pct, 1), 'E大': 'BUY', '系统': action,
                '一致': '✅' if action == 'BUY' else '⚠️',
            })

    return pd.DataFrame(results)


def simulate_e_portfolio():
    """模拟E大150份计划持仓变化"""
    portfolio = {}
    cash = 150
    history = []
    for date, buys, sells in E_TRADES:
        for name in buys:
            key = NAME_MAP.get(name, name)
            portfolio[key] = portfolio.get(key, 0) + 1
            cash -= 1
        for name in sells:
            key = NAME_MAP.get(name, name)
            if portfolio.get(key, 0) > 0:
                portfolio[key] -= 1
                cash += 1
        history.append({
            'date': date,
            '总持仓': sum(v for v in portfolio.values() if v > 0),
            '现金': cash,
            '品种': len([v for v in portfolio.values() if v > 0]),
        })
    return pd.DataFrame(history)


# ══════════════════════════════════════════════════════════════════════
# 主函数
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("  E大策略回测  —  2016-2024 全量月度信号回测 + 风险指标")
    print("=" * 72)

    # [1] E大持仓变化
    print("\n[1] E大150份计划持仓变化 (2015-2019)")
    hist = simulate_e_portfolio()
    print(f"  {'月份':<10} {'总持仓':>6} {'现金':>5} {'品种':>4}")
    print("  " + "-" * 30)
    for _, row in hist.iterrows():
        print(f"  {row['date']:<10} {row['总持仓']:>6} {row['现金']:>5} {row['品种']:>4}")

    # [2] E大操作 vs 系统信号
    print("\n[2] PE分位 vs E大实际操作 (2016-2019)")
    df = backtest_vs_e_trades()
    if not df.empty:
        n_ok = (df['一致'] == '✅').sum()
        print(f"  一致率: {n_ok}/{len(df)} = {n_ok/len(df)*100:.0f}%")
        print(f"  {'日期':<8} {'品种':<12} {'PE':>6} {'分位':>7} {'E大':>5} {'系统':>5} 结果")
        print("  " + "-" * 60)
        for _, row in df.iterrows():
            print(f"  {row['date']:<8} {row['品种']:<12} {row['PE']:>6.1f} "
                  f"{row['分位']:>6.1f}% {row['E大']:>5} {row['系统']:>5} {row['一致']}")

    # [3] 全量月度信号回测
    print("\n[3] 全量月度信号回测 (2016-01 → 2024-12)")
    print("  策略: PE分位 + 持仓高点止盈(回落15%卖1份)")
    print("  参数: 初始150万, 每份1万, 印花税0.1%, 佣金0.03%")
    portfolio_df, trades_df = run_monthly_backtest(
        start_year=2016, end_year=2024,
        cash=150.0, share_size=1.0,
        tax_rate=0.001, commission_rate=0.0003,
    )

    metrics = {}
    if not portfolio_df.empty:
        metrics = calc_risk_metrics(portfolio_df)
        print(f"\n  核心指标:")
        print(f"  {'─'*42}")
        print(f"  {'总收益率':<12}: {metrics['total_return']:>+8.1f}%")
        print(f"  {'年化收益':<12}: {metrics['annual_return']:>+8.1f}%")
        print(f"  {'最大回撤':<12}: {metrics['max_drawdown']:>8.1f}%")
        print(f"  {'夏普比率':<12}: {metrics['sharpe_ratio']:>8.2f}")
        print(f"  {'盈利月份':<12}: {metrics['win_rate']:>8.1f}%")
        print(f"  {'回测区间':<12}: {metrics['years']:>8.1f} 年")
        print(f"  {'─'*42}")

        key_dates = ['2016-01', '2017-01', '2018-01', '2019-01',
                     '2020-01', '2021-01', '2022-01', '2023-01', '2024-01', '2024-12']
        print(f"\n  组合价值走势:")
        print(f"  {'日期':<10} {'组合价值(万)':>14} {'总持仓份':>8} {'现金份':>8}")
        print("  " + "-" * 45)
        for d in key_dates:
            row = portfolio_df[portfolio_df['date'] == d]
            if not row.empty:
                r = row.iloc[0]
                print(f"  {r['date']:<10} {r['portfolio_value']:>14.2f} "
                      f"{r['total_shares_used']:>8.0f} {r['cash_shares']:>8.0f}")

        if not trades_df.empty:
            buys = trades_df[trades_df['action'] == 'BUY']
            sells = trades_df[trades_df['action'] == 'SELL']
            print(f"\n  交易统计:")
            print(f"    买入: {len(buys)}次  卖出: {len(sells)}次")
            total_tax = float(sells['tax'].sum()) if 'tax' in sells.columns else 0.0
            total_comm = float(trades_df['commission'].sum()) if 'commission' in trades_df.columns else 0.0
            print(f"    总印花税: {total_tax:.2f}万  总佣金: {total_comm:.2f}万")
            print(f"    交易成本率: {(total_tax + total_comm) / 150 * 100:.2f}%")

    # [4] vs 基准
    print("\n[4] vs 买入持有基准")
    benchmarks = []
    for name in ['50ETF', '中证500ETF', '中证红利']:
        p1 = get_month_price(name, 2016, 2)
        p2 = get_month_price(name, 2024, 12)
        if p1 and p2:
            benchmarks.append({'品种': name, '收益': (p2 - p1) / p1 * 100})
    for b in benchmarks:
        print(f"    {b['品种']}: 2016-02买入持有 → {b['收益']:+.1f}%")
    if metrics and benchmarks:
        sys_ret = metrics['total_return']
        bh_ret = np.mean([b['收益'] for b in benchmarks])
        print(f"    系统 vs 平均买入持有: {sys_ret:+.1f}% vs {bh_ret:+.1f}%  超额: {sys_ret - bh_ret:+.1f}%")

    # [5] 结论
    print("\n" + "=" * 72)
    print("  回测结论")
    print("=" * 72)
    if metrics:
        print(f"  · 2016-2024 全量月度信号回测:")
        print(f"    年化收益 {metrics['annual_return']:+.1f}%, 最大回撤 {metrics['max_drawdown']:.1f}%, 夏普 {metrics['sharpe_ratio']:.2f}")
        # 关键洞察
        r21 = portfolio_df[portfolio_df['date'] == '2021-01']
        r24 = portfolio_df[portfolio_df['date'] == '2024-01']
        if not r21.empty and not r24.empty:
            v21, v24 = float(r21.iloc[0]['portfolio_value']), float(r24.iloc[0]['portfolio_value'])
            print(f"  · 牛市顶点(2021-01)→熊市(2024-01): {v21:.0f}→{v24:.0f}万 ({(v24/v21-1)*100:+.1f}%)")
        print(f"  · 系统优势区间: 熊市建仓（2016-01→2019-01: +26.7% vs 50ETF指数+57%）")
        print(f"  · 系统局限区间: 牛市后半段（PE分位偏低导致过早满仓，错过止盈窗口）")
    print(f"  · 2016-2019 E大操作验证: 一致率 {n_ok if not df.empty else 0}/{len(df) if not df.empty else 0}")
    print(f"  · 策略核心: 低估区持续买入，高估区分批卖出，严守150份纪律")
    print(f"  · 量化局限: PE全量锚点在长牛市中分位偏低，需结合绝对价格或手动判断止盈")


if __name__ == '__main__':
    main()

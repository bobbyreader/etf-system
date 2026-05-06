#!/usr/bin/env python3
"""
E大"长赢"AI投资系统 - 统一入口
用法: python main.py [command]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from strategies.valuation import ValuationEngine
from strategies.grid import GridEngine, create_油气_grid, create_恒生_target_market
from signals.monthly_signal import SignalGenerator
from portfolio.manager import PortfolioManager


def cmd_status():
    """状态报告（含持仓浮盈亏）"""
    print("\n" + "=" * 70)
    print("  E大长赢投资系统  —  实时状态")
    print("=" * 70)

    engine = ValuationEngine(data_dir='./data')
    df = engine.generate_all_signals()

    # 信号统计
    buys = df[df['操作'] == 'BUY']
    sells = df[df['操作'] == 'SELL']
    holds = df[df['操作'] == 'HOLD']

    print(f"\n  品种数量: {len(df)}")
    print(f"  买入: {len(buys)} | 卖出: {len(sells)} | 持有: {len(holds)}")

    # 分位区间分布
    def pct_range(row):
        try:
            return float(str(row['综合分位']).replace('%',''))
        except:
            return 50.0

    df['_pct'] = df.apply(pct_range, axis=1)
    for lo, hi, label in [(0,15,'极度低估'),(15,30,'低估'),(30,50,'偏低'),(50,70,'偏高'),(70,85,'高估'),(85,100,'极度高估')]:
        subset = df[(df['_pct']>=lo)&(df['_pct']<hi)]
        if len(subset):
            names = list(subset['品种'].values)
            print(f"  {label}({lo}-{hi}%): {names}")

    # 持仓状态
    pm = PortfolioManager(data_dir='./data')
    positions = pm.get_positions()
    if positions:
        # 收集当前价格
        prices = {}
        for name in positions:
            price = engine.fetch_etf_price(name)
            if price is None:
                # 尝试从品种配置获取
                sig = engine.generate_signal(name)
                if sig and sig.get('ETF价格'):
                    prices[name] = sig['ETF价格']
            else:
                prices[name] = price
        pm.print_status(current_prices=prices)
    else:
        print(f"\n  持仓状态: 空仓 (可用 150 份)")
        pm.print_status()

    # 油气网格状态
    print(f"  华宝油气网格:")
    grid = create_油气_grid()
    for l in grid.levels:
        s = '✅' if l['filled'] else '⬜'
        print(f"    L{l['level']:>2} {s} {l['trigger_price']:.4f} ({l['trigger_pct']:+.1f}%)")

    print(f"\n  恒生目标市值:")
    hk = create_恒生_target_market(current_cost=1.0, current_shares=0, target_value=10000)
    print(f"    {hk['逻辑']}")


def cmd_signal():
    """月度信号"""
    pm = PortfolioManager(data_dir='./data')
    holdings = {k: v['shares'] for k, v in pm.get_positions().items() if v['shares'] > 0}

    gen = SignalGenerator()
    signals, buys, sells, holds = gen.generate_monthly_report()
    plan = gen.generate_150_plan(signals, current_holdings=holdings)
    gen.print_monthly_report(plan, signals)


def cmd_execute():
    """执行月度计划"""
    if len(sys.argv) < 3:
        print("用法: python main.py execute <买1份数,买2份数...>")
        print("  例: python main.py execute 50ETF=2,中证红利=1")
        print("  例: python main.py execute 50ETF=2  (仅买入50ETF 2份)")
        return

    # 解析参数: 品种=份数,品种=份数... 或 品种=份数 品种=份数...
    buy_list = []
    for arg in sys.argv[2:]:
        if arg.startswith('-'):
            # sell: -品种=份数
            parts = arg[1:].split('=')
            if len(parts) == 2:
                buy_list.append({'品种': parts[0].strip(), '份数': -int(parts[1].strip())})
        elif '=' in arg:
            parts = arg.split('=', 1)
            buy_list.append({'品种': parts[0].strip(), '份数': int(parts[1].strip())})

    if not buy_list:
        print("错误: 未指定操作。例: python main.py execute 50ETF=2")
        return

    # 日期：最后一个非品种参数，格式为 YYYY-MM-DD 或 YYYYMMDD
    import re
    date = None
    date_arg_idx = None
    for i, arg in enumerate(sys.argv[2:], 2):
        if re.match(r'^\d{4}-?\d{2}-?\d{2}$', arg):
            date = arg.replace('/', '-')
            date_arg_idx = i
            break

    # 收集当前价格（从 akshare 实时拉取）
    engine = ValuationEngine(data_dir='./data')
    prices = {}
    for name in set(x['品种'] for x in buy_list):
        sig = engine.generate_signal(name)
        if sig and sig.get('ETF价格'):
            prices[name] = sig['ETF价格']

    buys = [x for x in buy_list if x['份数'] > 0]
    sells = [{'品种': x['品种'], '份数': -x['份数']} for x in buy_list if x['份数'] < 0]

    pm = PortfolioManager(data_dir='./data')
    result = pm.execute_plan(buys, sells, prices=prices, date=date)

    print("\n" + "=" * 60)
    print(f"  执行结果  ({result['summary']['date']})")
    print("=" * 60)
    print(f"  买入: {result['summary']['买入']}  卖出: {result['summary']['卖出']}")
    if result['errors']:
        print(f"  错误:")
        for e in result['errors']:
            print(f"    ⚠️  {e}")

    # 显示最新持仓状态
    pm.print_status(current_prices=prices)


def cmd_portfolio():
    """持仓管理"""
    pm = PortfolioManager(data_dir='./data')

    sub = sys.argv[2] if len(sys.argv) > 2 else 'status'

    if sub == 'status' or sub == '':
        engine = ValuationEngine(data_dir='./data')
        prices = {}
        for name in pm.get_positions():
            p = engine.fetch_etf_price(name)
            if p:
                prices[name] = p
        pm.print_status(current_prices=prices if prices else None)
    elif sub == 'history':
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        pm.print_history(limit=limit)
    elif sub == 'reset':
        pm.data = pm._empty_portfolio()
        pm.save()
        print("持仓已清空。")
    else:
        print(f"用法: python main.py portfolio [status|history|reset]")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'

    if cmd == 'status':
        cmd_status()
    elif cmd == 'signal':
        cmd_signal()
    elif cmd == 'grid':
        cmd_grid()
    elif cmd == 'backtest':
        from backtest.bt_engine import main as bt_main
        bt_main()
    elif cmd == 'execute':
        cmd_execute()
    elif cmd == 'portfolio' or cmd == 'pf':
        cmd_portfolio()
    else:
        print(f"用法: python main.py [status|signal|grid|backtest|execute|portfolio]")
        print(f"  status   — 实时状态报告（含持仓浮盈亏）")
        print(f"  signal   — 月度信号生成")
        print(f"  grid     — 网格详情")
        print(f"  backtest — 历史回测验证")
        print(f"  execute  — 执行月度计划")
        print(f"  portfolio— 持仓管理")


if __name__ == '__main__':
    main()

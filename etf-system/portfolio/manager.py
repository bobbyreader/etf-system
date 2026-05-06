"""
E大"长赢"体系 - 持仓管理器
持仓持久化 + 浮盈亏计算 + 执行信号
"""

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime


class PortfolioManager:
    """150份计划持仓管理器"""

    def __init__(self, data_dir: str = './data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.data_dir / 'portfolio.json'
        self._load()

    def _load(self):
        if self.file.exists():
            with open(self.file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        else:
            self.data = self._empty_portfolio()

    def _empty_portfolio(self) -> dict:
        return {
            'created': datetime.now().isoformat(),
            'updated': datetime.now().isoformat(),
            'total_shares': 150,
            'cash': 150.0,
            'positions': {},  # {品种: {shares, cost, buy_dates}}
            'history': [],     # [{date, action, name, shares, price}]
        }

    def save(self):
        self.data['updated'] = datetime.now().isoformat()
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ─── 持仓查询 ────────────────────────────────────────────────────

    def get_positions(self) -> dict:
        return self.data['positions']

    def get_summary(self) -> dict:
        pos = self.data['positions']
        total_shares = sum(v['shares'] for v in pos.values())
        cash = self.data['cash']
        return {
            'total_shares': total_shares,
            'cash': cash,
            'used_shares': total_shares,
            'total_invested_value': self._calc_invested_value(),
        }

    def _calc_invested_value(self) -> float:
        """计算已投入金额（份数 × 1万）"""
        return sum(v['shares'] for v in self.data['positions'].values()) * 1.0

    def calc_unrealized_pnl(self, current_prices: dict) -> dict:
        """
        计算浮盈亏
        current_prices: {品种: float}  每份对应价格（指数点位或ETF净值）
        """
        results = []
        total_cost = 0.0
        total_market = 0.0

        for name, pos in self.data['positions'].items():
            shares = pos['shares']
            if shares <= 0:
                continue
            avg_cost = pos.get('avg_cost', 1.0)
            current = current_prices.get(name, avg_cost)
            # 每份=1万，成本=份数×1万；市值=份数×(现价/均价)×1万
            cost = shares * 1.0          # 成本，万
            ratio = current / avg_cost if avg_cost and avg_cost > 0 else 1.0
            market = shares * ratio * 1.0  # 当前市值，万
            pnl = market - cost           # 浮盈亏，万
            pnl_pct = (ratio - 1.0) * 100
            results.append({
                '品种': name,
                '持仓份数': shares,
                '持仓均价': round(avg_cost, 4),
                '当前价': round(current, 4),
                '浮盈亏(万)': round(pnl, 2),
                '浮盈亏率': round(pnl_pct, 1),
            })
            total_cost += cost
            total_market += market

        total_pnl = total_market - total_cost
        total_pnl_pct = total_pnl / total_cost * 100 if total_cost > 0 else 0

        return {
            'positions': results,
            '总浮盈亏(万)': round(total_pnl, 2),
            '总浮盈亏率': round(total_pnl_pct, 1),
        }

    # ─── 执行操作 ────────────────────────────────────────────────────

    def buy(self, name: str, shares: int, price: float, date: str = None) -> dict:
        """买入品种"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        pos = self.data['positions'].get(name, {'shares': 0, 'cost': 0.0, 'avg_cost': 1.0, 'buy_records': []})
        old_shares = pos['shares']

        # 更新均价
        total_cost = old_shares * pos.get('avg_cost', 1.0) + shares * price
        new_shares = old_shares + shares
        new_avg = total_cost / new_shares if new_shares > 0 else price

        self.data['positions'][name] = {
            'shares': new_shares,
            'avg_cost': round(new_avg, 6),
            'buy_records': pos.get('buy_records', []) + [{
                'date': date, 'shares': shares, 'price': price,
            }],
        }
        self.data['cash'] -= shares

        self.data['history'].append({
            'date': date, 'action': 'BUY', 'name': name,
            'shares': shares, 'price': price,
        })

        self.save()
        return {'ok': True, 'name': name, 'bought': shares, 'total': new_shares}

    def sell(self, name: str, shares: int, price: float, date: str = None) -> dict:
        """卖出品种"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        pos = self.data['positions'].get(name, {'shares': 0})
        held = pos.get('shares', 0)
        if held < shares:
            return {'ok': False, 'error': f'{name} 持仓{held}份，不足{shears}份'}

        self.data['positions'][name]['shares'] = held - shares
        self.data['cash'] += shares

        self.data['history'].append({
            'date': date, 'action': 'SELL', 'name': name,
            'shares': shares, 'price': price,
        })

        # 清理空持仓
        if self.data['positions'][name]['shares'] <= 0:
            del self.data['positions'][name]

        self.save()
        return {'ok': True, 'name': name, 'sold': shares, 'remaining': held - shares}

    def execute_plan(self, buy_list: list, sell_list: list = None,
                     prices: dict = None, date: str = None) -> dict:
        """
        执行月度计划
        buy_list: [{'品种': str, '份数': int}, ...]
        sell_list: [{'品种': str, '份数': int}, ...]
        prices: {品种: 当前价格}
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        if sell_list is None:
            sell_list = []
        if prices is None:
            prices = {}

        results = {'buys': [], 'sells': [], 'errors': [], 'summary': {}}

        for item in sell_list:
            r = self.sell(item['品种'], item['份数'], prices.get(item['品种'], 1.0), date)
            if r['ok']:
                results['sells'].append(r)
            else:
                results['errors'].append(r.get('error', str(r)))

        for item in buy_list:
            name = item['品种']
            shares = item['份数']
            price = prices.get(name, 1.0)
            # 检查资金
            if self.data['cash'] < shares:
                results['errors'].append(f'现金不足：{name}需要{shares}份，剩余{self.data['cash']}份')
                continue
            r = self.buy(name, shares, price, date)
            if r['ok']:
                results['buys'].append(r)

        # 汇总
        summary = self.get_summary()
        results['summary'] = {
            'date': date,
            '买入': len(results['buys']),
            '卖出': len(results['sells']),
            '错误': len(results['errors']),
            '已用份数': summary['used_shares'],
            '现金份数': summary['cash'],
        }

        return results

    def print_status(self, current_prices: dict = None):
        """打印持仓状态"""
        print("\n" + "=" * 65)
        print(f"  E大150份计划  持仓状态  (更新: {self.data['updated'][:10]})")
        print("=" * 65)

        summary = self.get_summary()
        print(f"\n  总持仓: {summary['used_shares']}/{self.data['total_shares']} 份  "
              f"现金: {summary['cash']:.0f} 份  投入: {summary['total_invested_value']:.0f}万")

        positions = self.data['positions']
        if not positions:
            print("\n  (空仓，无持仓记录)")
        else:
            print(f"\n  {'品种':<12} {'份数':>5} {'均价':>8} {'当前价':>8}")
            print("  " + "-" * 40)
            for name, pos in sorted(positions.items(), key=lambda x: -x[1]['shares']):
                cur = current_prices.get(name) if current_prices else None
                avg = pos.get('avg_cost', 1.0)
                print(f"  {name:<12} {pos['shares']:>5} {avg:>8.4f} "
                      f"{(str(round(cur,4)) if cur else '--'):>8}")

        # 浮盈亏
        if current_prices:
            pnl = self.calc_unrealized_pnl(current_prices)
            if pnl['positions']:
                print(f"\n  浮盈亏:")
                print(f"  {'品种':<12} {'持仓':>5} {'浮盈亏(万)':>10} {'收益率':>8}")
                print("  " + "-" * 40)
                for r in pnl['positions']:
                    sign = '+' if r['浮盈亏(万)'] >= 0 else ''
                    print(f"  {r['品种']:<12} {r['持仓份数']:>5} "
                          f"{sign}{r['浮盈亏(万)']:>9.2f} {sign}{r['浮盈亏率']:>6.1f}%")
                print(f"\n  总浮盈亏: {pnl['总浮盈亏(万)']:+.2f}万  ({pnl['总浮盈亏率']:+.1f}%)")

        # 历史操作摘要
        history = self.data['history']
        if history:
            print(f"\n  最近操作:")
            for h in history[-5:]:
                icon = '🟢+' if h['action'] == 'BUY' else '🔴-'
                print(f"  {icon} {h['date']} {h['name']} {h['shares']}份 @{h['price']:.4f}")

        print("=" * 65)

    def print_history(self, limit: int = 20):
        """打印完整操作历史"""
        history = self.data['history']
        if not history:
            print("\n  (无操作记录)")
            return
        print(f"\n  操作历史 (共{len(history)}笔):")
        print(f"  {'日期':<12} {'操作':>5} {'品种':<12} {'份数':>5} {'价格':>8}")
        print("  " + "-" * 50)
        for h in history[-limit:]:
            icon = 'BUY+' if h['action'] == 'BUY' else 'SELL-'
            print(f"  {h['date']:<12} {icon:>5} {h['name']:<12} "
                  f"{h['shares']:>5} {h['price']:>8.4f}")


def main():
    """测试入口"""
    pm = PortfolioManager(data_dir='./data')

    # 模拟建仓
    print("=== 模拟建仓 ===")
    r = pm.buy('50ETF', 5, 2.8, '2024-01-15')
    print(r)
    r = pm.buy('中证红利', 3, 1.2, '2024-01-15')
    print(r)
    r = pm.buy('恒生ETF', 8, 1.1, '2024-01-15')
    print(r)

    # 模拟当月信号执行
    print("\n=== 执行月度计划 ===")
    plan = pm.execute_plan(
        buy_list=[{'品种': '50ETF', '份数': 2}],
        sell_list=[],
        prices={'50ETF': 2.6, '中证红利': 1.15, '恒生ETF': 1.05},
        date='2024-02-10',
    )
    print(f"执行结果: 买入{plan['summary']['买入']}笔, 卖出{plan['summary']['卖出']}笔, "
          f"错误{plan['summary']['错误']}笔")
    for e in plan['errors']:
        print(f"  错误: {e}")

    # 显示状态（含浮盈亏）
    pm.print_status(current_prices={'50ETF': 2.6, '中证红利': 1.15, '恒生ETF': 1.05})

    # 历史
    pm.print_history()


if __name__ == '__main__':
    main()

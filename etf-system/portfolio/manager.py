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
from strategies.universe import UNIVERSE, ASSET_CLASS_LIMITS, ALL_UNIVERSE


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

# 再平衡阈值（漂移超过此比例则触发调仓）
REBALANCE_INDIVIDUAL_THRESHOLD = 0.05   # 单品偏离目标5%以上
REBALANCE_CLASS_THRESHOLD = 0.08        # 大类偏离目标8%以上
REBALANCE_CASH_THRESHOLD = 0.10         # 现金偏离超过10%（满仓或空仓）


class RebalanceEngine:
    """
    E大定期再平衡引擎
    核心逻辑：
    1. 漂移检测：检查单品/大类是否偏离目标配置
    2. 优先级排序：按估值低买高卖
    3. 生成调仓建议：卖高估 → 买低估
    """

    def __init__(self, portfolio_manager: 'PortfolioManager', valuations: dict):
        """
        portfolio_manager: PortfolioManager 实例
        valuations: {品种: {'score': float, 'action': str, ...}}
        """
        self.pm = portfolio_manager
        self.valuations = valuations  # 品种估值信号
        self.total = portfolio_manager.data.get('total_shares', 150)
        self._analyze()

    def _analyze(self):
        """分析当前配置与目标的差距"""
        positions = self.pm.data.get('positions', {})

        # 目标配置（每个品种的目标份数）
        self.targets = {}    # {品种: 目标份数比例}
        for name, info in UNIVERSE.items():
            max_alloc = info.get('max_allocation', 0.20)
            self.targets[name] = max_alloc

        # 当前配置
        self.current = {}   # {品种: 当前份数比例}
        for name, pos in positions.items():
            shares = pos.get('shares', 0)
            self.current[name] = shares / self.total

        # 大类汇总
        self.class_current = {}
        self.class_target = {}
        for name in ALL_UNIVERSE:
            info = UNIVERSE.get(name, {})
            cls = info.get('type', 'other')
            self.class_current[cls] = self.class_current.get(cls, 0) + self.current.get(name, 0)
            self.class_target[cls] = max(self.class_target.get(cls, 0), info.get('max_allocation', 0.20))

        # 现金
        self.cash_ratio = self.pm.data.get('cash', 0) / self.total
        self.cash_shares = self.pm.data.get('cash', 0)

    def check_drift(self) -> list:
        """检测漂移，返回偏离项列表"""
        drifts = []

        # 单品漂移：只检查当前已持仓的品种
        for name, pos in self.pm.data.get('positions', {}).items():
            info = UNIVERSE.get(name, {})
            if not info:
                continue
            max_alloc = info.get('max_allocation', 0.20)
            cur = self.current.get(name, 0)
            drift = cur - max_alloc

            if abs(drift) >= REBALANCE_INDIVIDUAL_THRESHOLD:
                val = self.valuations.get(name, {})
                drifts.append({
                    'level': '单品超配' if drift > 0 else '单品不足',
                    'name': name,
                    'current_pct': round(cur * 100, 1),
                    'target_pct': round(max_alloc * 100, 1),
                    'drift_pct': round(drift * 100, 1),
                    'score': val.get('score', 'N/A'),
                    'action': val.get('action', 'N/A'),
                    'type': info.get('type', 'other'),
                    'max_shares': int(max_alloc * self.total),
                    'current_shares': round(cur * self.total, 1),
                })

        # 大类漂移
        for cls in self.class_current:
            cur = self.class_current.get(cls, 0)
            target = self.class_target.get(cls, 0)
            drift = cur - target
            if abs(drift) >= REBALANCE_CLASS_THRESHOLD:
                drifts.append({
                    'level': '大类超配' if drift > 0 else '大类不足',
                    'name': cls,
                    'current_pct': round(cur * 100, 1),
                    'target_pct': round(target * 100, 1),
                    'drift_pct': round(drift * 100, 1),
                    'score': 'N/A',
                    'action': 'N/A',
                    'type': cls,
                    'max_shares': int(target * self.total),
                    'current_shares': round(cur * self.total, 1),
                })

        # 现金偏离
        if abs(self.cash_ratio - 0.0) >= REBALANCE_CASH_THRESHOLD and self.cash_ratio >= 0.15:
            drifts.append({
                'level': '现金冗余',
                'name': '现金',
                'current_pct': round(self.cash_ratio * 100, 1),
                'target_pct': 0,
                'drift_pct': round(self.cash_ratio * 100, 1),
                'cash_shares': self.cash_shares,
            })

        return drifts

    def generate_rebalance_plan(self) -> dict:
        """
        生成再平衡计划
        原则：
        1. 只卖高估/正常偏高区的品种（PE分位>=50%）
        2. 只买低估/正常偏低区的品种（PE分位<50%）
        3. 优先处理漂移最大的项
        4. 保持现金不低于总份数的5%
        """
        drifts = self.check_drift()
        if not drifts:
            return {'needs_rebalance': False, 'buys': [], 'sells': [], 'reason': '配置正常，无漂移'}

        sells = []
        buys = []

        # 按漂移幅度排序，优先处理最极端的
        drifts.sort(key=lambda x: -abs(x['drift_pct']))

        cash = self.cash_shares
        min_cash = self.total * 0.05  # 最少保留5%现金

        for d in drifts:
            if d['level'] == '单品超配' and d['drift_pct'] > 0:
                # 超配 → 建议卖出
                excess_pct = d['drift_pct'] / 100
                excess_shares = excess_pct * self.total

                # 检查估值是否支持卖出（高估区才卖）
                val = self.valuations.get(d['name'], {})
                score_str = val.get('score', '50%')
                try:
                    score = float(str(score_str).replace('%', ''))
                except:
                    score = 50.0

                if score >= 50:
                    sell_shares = min(int(excess_shares * 0.5), int(d['current_shares'] * 0.3)) if d['level'] == '单品' else int(excess_shares * 0.5)
                    sell_shares = max(1, sell_shares)
                    sells.append({
                        'name': d['name'],
                        'reason': f"超配漂移{d['drift_pct']:+.1f}%，估值{score:.0f}%分位，建议卖出",
                        'sell_shares': sell_shares,
                        'priority': abs(d['drift_pct']),
                        'score': score,
                    })

            elif d['level'] in ('单品不足',) and d['drift_pct'] < 0:
                # 不足 → 建议买入（但需要现金）
                shortage_pct = abs(d['drift_pct']) / 100
                shortage_shares = shortage_pct * self.total
                available = cash - min_cash

                if available > 1:
                    val = self.valuations.get(d['name'], {})
                    score_str = val.get('score', '50%')
                    try:
                        score = float(str(score_str).replace('%', ''))
                    except:
                        score = 50.0

                    # 低估才买
                    if score <= 50:
                        buy_shares = min(int(shortage_shares * 0.3), max(1, int(available * 0.5)))
                        if buy_shares >= 1:
                            buys.append({
                                'name': d['name'],
                                'reason': f"配置不足{d['drift_pct']:+.1f}%，估值{score:.0f}%分位，建议买入",
                                'buy_shares': buy_shares,
                                'priority': abs(d['drift_pct']),
                                'score': score,
                            })
                            cash -= buy_shares

        # 按优先级排序
        sells.sort(key=lambda x: -x['priority'])
        buys.sort(key=lambda x: x['score'])  # 估值越低越优先

        needs = len(sells) > 0 or len(buys) > 0
        reason = '配置正常，无漂移' if not needs else f'检测到{len(sells)}个超配项，{len(buys)}个不足项'

        return {
            'needs_rebalance': needs,
            'buys': buys,
            'sells': sells,
            'reason': reason,
            'current_cash': self.cash_shares,
            'cash_after_plan': cash,
        }

    def get_rebalance_report(self) -> dict:
        """完整的再平衡诊断报告"""
        drifts = self.check_drift()
        plan = self.generate_rebalance_plan()
        return {
            'needs_rebalance': plan['needs_rebalance'],
            'drifts': drifts,
            'plan': plan,
            'cash_ratio': round(self.cash_ratio * 100, 1),
            'cash_shares': self.cash_shares,
            'total_shares': self.total,
            'thresholds': {
                'individual': REBALANCE_INDIVIDUAL_THRESHOLD * 100,
                'class': REBALANCE_CLASS_THRESHOLD * 100,
                'cash': REBALANCE_CASH_THRESHOLD * 100,
            },
        }


def print_rebalance_report(report: dict):
    """打印再平衡报告"""
    print("\n" + "=" * 65)
    print("  E大定期再平衡诊断报告")
    print("=" * 65)

    print(f"\n  现金: {report['cash_shares']:.0f}/{report['total_shares']} 份 ({report['cash_ratio']}%)")
    print(f"  阈值: 单品>{report['thresholds']['individual']}% 大类>{report['thresholds']['class']}%")

    drifts = report['drifts']
    if not drifts:
        print("\n  ✅ 配置正常，无漂移")
    else:
        print(f"\n  漂移检测 ({len(drifts)}项):")
        print(f"  {'级别':<8} {'品种/大类':<10} {'当前':>6} {'目标':>6} {'漂移':>6} {'分位':>6} {'操作':>5}")
        print("  " + "-" * 55)
        for d in drifts:
            print(f"  {d['level']:<8} {d['name']:<10} {d['current_pct']:>5.1f}% {d['target_pct']:>5.1f}% "
                  f"{d['drift_pct']:>+5.1f}% {str(d['score']):>6} {d['action']:>5}")

    plan = report['plan']
    if plan['needs_rebalance']:
        print(f"\n  调仓建议:")
        for s in plan['sells']:
            print(f"  🔴 卖出 {s['name']} {s['sell_shares']}份 — {s['reason']}")
        for b in plan['buys']:
            print(f"  🟢 买入 {b['name']} {b['buy_shares']}份 — {b['reason']}")
        print(f"\n  调仓后现金: {plan['cash_after_plan']:.0f}份")
    else:
        print(f"\n  ✅ {plan['reason']}")

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

"""
E大网格策略引擎 v1
- 网格1.0: 基础等间距网格
- 网格2.0: 留利润 + 逐格加码 + 一网打尽(大/中/小网)
- 压力测试: 最大跌幅模拟
"""

import pandas as pd
import numpy as np
from typing import Optional
from dataclasses import dataclass, field


# ─── 网格配置 ──────────────────────────────────────────────────────────

@dataclass
class GridConfig:
    """网格参数"""
    name: str
    base_price: float          # 基准价格（首次建仓价）
    grid_pct: float = 5.0      # 网格间距(%)
    n_grids: int = 10          # 网格层数
    max_drop_pct: float = 50.0 # 预计最大跌幅(%)
    # 2.0策略开关
    keep_profit: bool = True   # 留利润子策略
    keep_ratio: float = 0.05   # 每网留利润比例（卖出的%保留）
    progressive: bool = True    # 逐格加码
    progressive_pct: float = 5.0 # 每格加码幅度(%)
    # 一网打尽
    multi_grid: bool = True     # 大/中/小三网
    mid_pct: float = 15.0      # 中网间距(%)
    large_pct: float = 30.0    # 大网间距(%)


@dataclass
class GridLevel:
    """单个网格层"""
    level: int
    buy_price: float
    sell_price: float
    shares: float
    cost: float
    grid_type: str = 'small'   # small/medium/large
    sold: bool = False
    sell_price_received: float = 0.0
    profit_kept: bool = False  # 留利润


@dataclass
class GridPosition:
    """持仓状态"""
    name: str
    base_price: float
    total_cost: float = 0.0
    total_shares: float = 0.0
    avg_cost: float = 0.0
    peak_price: float = 0.0
    levels: list = field(default_factory=list)
    realized_profit: float = 0.0
    kept_shares: float = 0.0   # 留利润份数(0成本)


# ─── 核心引擎 ──────────────────────────────────────────────────────────

class GridEngine:
    """
    E大网格策略引擎
    """

    def __init__(self, name: str, config: GridConfig):
        self.name = name
        self.cfg = config
        self.position = GridPosition(name=name, base_price=config.base_price)
        self._build_grids()

    def _build_grids(self):
        """生成所有网格层"""
        cfg = self.cfg
        levels = []

        # 小网 (5%)
        for i in range(1, cfg.n_grids + 1):
            buy_p = cfg.base_price * (1 - cfg.grid_pct / 100 * i)
            sell_p = cfg.base_price * (1 - cfg.grid_pct / 100 * (i - 1))
            base_shares = 1.0
            # 逐格加码
            if cfg.progressive:
                base_shares = 1.0 + (cfg.progressive_pct / 100 * (i - 1))
            levels.append(GridLevel(
                level=i, buy_price=buy_p, sell_price=sell_p,
                shares=base_shares, cost=buy_p * base_shares,
                grid_type='small'
            ))

        # 中网 (15%) + 大网 (30%) — 一网打尽
        if cfg.multi_grid:
            mid_start = cfg.n_grids
            for i in range(1, 4):
                buy_p = cfg.base_price * (1 - cfg.mid_pct / 100 * i)
                sell_p = cfg.base_price * (1 - cfg.mid_pct / 100 * (i - 1))
                levels.append(GridLevel(
                    level=mid_start + i, buy_price=buy_p, sell_price=sell_p,
                    shares=1.0, cost=buy_p,
                    grid_type='medium'
                ))
            large_start = mid_start + 3
            for i in range(1, 3):
                buy_p = cfg.base_price * (1 - cfg.large_pct / 100 * i)
                sell_p = cfg.base_price * (1 - cfg.large_pct / 100 * (i - 1))
                levels.append(GridLevel(
                    level=large_start + i, buy_price=buy_p, sell_price=sell_p,
                    shares=1.0, cost=buy_p,
                    grid_type='large'
                ))

        self.position.levels = sorted(levels, key=lambda x: x.level)

    def get_grid_status(self, current_price: float) -> dict:
        """获取网格当前状态"""
        pos = self.position
        cfg = self.cfg

        # 更新峰值
        if current_price > pos.peak_price:
            pos.peak_price = current_price

        # 各层状态
        grid_status = []
        for lv in pos.levels:
            status = 'idle'
            if current_price <= lv.buy_price:
                status = 'pending_buy'
            elif current_price >= lv.sell_price and not lv.sold:
                status = 'pending_sell'
            elif lv.sold:
                status = 'sold'
            grid_status.append({
                'level': lv.level,
                'type': lv.grid_type,
                'buy_price': round(lv.buy_price, 4),
                'sell_price': round(lv.sell_price, 4),
                'shares': lv.shares,
                'status': status,
                'profit_kept': lv.profit_kept,
            })

        # 统计
        pending_buys = [g for g in grid_status if g['status'] == 'pending_buy']
        pending_sells = [g for g in grid_status if g['status'] == 'pending_sell']
        total_invested = sum(lv.cost for lv in pos.levels if not lv.sold)
        total_sold_cost = sum(lv.cost for lv in pos.levels if lv.sold and not lv.profit_kept)

        return {
            'name': self.name,
            'base_price': cfg.base_price,
            'current_price': round(current_price, 4),
            'price_vs_base': round((current_price / cfg.base_price - 1) * 100, 2),
            'peak_price': round(pos.peak_price, 4),
            'from_peak_pct': round((pos.peak_price - current_price) / pos.peak_price * 100, 2) if pos.peak_price > 0 else 0,
            'realized_profit': round(pos.realized_profit, 4),
            'kept_shares': pos.kept_shares,
            'total_invested': round(total_invested, 2),
            'pending_buys': len(pending_buys),
            'pending_sells': len(pending_sells),
            'grids': grid_status,
        }

    def sim_trigger(self, current_price: float) -> dict:
        """模拟触发: 哪些网格该买/该卖"""
        result = {'buys': [], 'sells': [], 'total_cost': 0.0, 'total_revenue': 0.0}

        for lv in self.position.levels:
            if lv.sold:
                continue
            # 触发买入
            if current_price <= lv.buy_price:
                result['buys'].append({
                    'level': lv.level, 'type': lv.grid_type,
                    'price': round(lv.buy_price, 4),
                    'shares': lv.shares, 'cost': round(lv.cost, 2),
                })
                result['total_cost'] += lv.cost
            # 触发卖出
            elif current_price >= lv.sell_price:
                # 留利润策略
                keep = self.cfg.keep_ratio if self.cfg.keep_profit else 0
                sell_shares = lv.shares * (1 - keep)
                if sell_shares > 0:
                    revenue = sell_shares * lv.sell_price
                    profit = sell_shares * (lv.sell_price - lv.buy_price)
                    result['sells'].append({
                        'level': lv.level, 'type': lv.grid_type,
                        'price': round(lv.sell_price, 4),
                        'shares': round(sell_shares, 3),
                        'revenue': round(revenue, 2),
                        'profit': round(profit, 2),
                        'profit_kept': keep > 0,
                    })
                    result['total_revenue'] += revenue
                    lv.sold = True
                    lv.sell_price_received = lv.sell_price
                    self.position.realized_profit += profit
                    if keep > 0:
                        lv.profit_kept = True
                        kept = lv.shares * keep
                        self.position.kept_shares += kept

        return result

    def pressure_test(self) -> dict:
        """
        压力测试: 模拟最坏情况下账户表现
        E大: "根据具体品种，模拟最大下跌幅度，在此基础上再加10%是铁底"
        """
        cfg = self.cfg
        max_drop = cfg.max_drop_pct
        worst_price = cfg.base_price * (1 - max_drop / 100)

        results = []
        total_cost = 0.0
        for lv in self.position.levels:
            if lv.buy_price >= worst_price:
                cost = round(lv.cost, 2)
                unreal_loss = round(cost * (max_drop / 100), 2)
                results.append({
                    'level': lv.level,
                    'type': lv.grid_type,
                    'buy_price': round(lv.buy_price, 4),
                    'triggered': True,
                    'cost': cost,
                    'unreal_loss': unreal_loss,
                })
                total_cost += cost

        # 最坏情况汇总
        worst_case = {
            'base_price': cfg.base_price,
            'worst_price': round(worst_price, 4),
            'max_drop_pct': max_drop,
            'total_cost_if_all_fill': round(total_cost, 2),
            'worst_unreal_loss': round(total_cost * max_drop / 100, 2),
            'triggered_grids': results,
            'note': f'假设价格从{cfg.base_price}跌至{worst_price:.4f}（-{max_drop}%）',
        }

        # 逐格加码影响
        if cfg.progressive:
            progressive_cost = sum(
                lv.cost for lv in self.position.levels
                if lv.buy_price >= worst_price
            )
            base_cost = sum(
                lv.shares * cfg.base_price * (1 - cfg.grid_pct/100 * lv.level)
                for lv in self.position.levels
                if lv.buy_price >= worst_price
            )
            if progressive_cost > base_cost:
                extra = round(progressive_cost - base_cost, 2)
                worst_case['progressive_extra_cost'] = extra
                worst_case['note'] += f'，逐格加码额外投入{extra:.0f}元/份'

        return worst_case

    def get_recommendation(self, current_price: float) -> str:
        """生成网格操作建议"""
        status = self.get_grid_status(current_price)
        pending_buy = status['pending_buys']
        pending_sell = status['pending_sells']

        if pending_buy > 0:
            return f'价格{current_price:.4f}触发{pending_buy}层网格买入，合计约{status["total_invested"]:.1f}元/份'
        elif pending_sell > 0:
            return f'价格{current_price:.4f}触发{pending_sell}层网格卖出，建议执行止盈'
        else:
            pct = status['price_vs_base']
            if pct > 0:
                return f'价格{current_price:.4f}(+{pct}%)高于基准，网格等待中'
            else:
                return f'价格{current_price:.4f}({pct}%)在网格区间内，等待触发'


# ─── 入口 ──────────────────────────────────────────────────────────

def main():
    """华宝油气网格示例"""
    print("=" * 60)
    print("  E大网格策略引擎  —  华宝油气示例")
    print("=" * 60)

    # 华宝油气配置 (以某个建仓价为基准)
    cfg = GridConfig(
        name='华宝油气',
        base_price=0.5,      # 假设基准价
        grid_pct=5.0,
        n_grids=8,
        max_drop_pct=50.0,
        keep_profit=True,
        keep_ratio=0.05,
        progressive=True,
        progressive_pct=5.0,
        multi_grid=True,
    )

    engine = GridEngine('华宝油气', cfg)

    print(f"\n基准价格: {cfg.base_price}")
    print(f"网格间距: {cfg.grid_pct}%")
    print(f"最大跌幅: {cfg.max_drop_pct}%")

    # 压力测试
    print("\n[压力测试]")
    pt = engine.pressure_test()
    print(f"  最坏价格: {pt['worst_price']} (-{pt['max_drop_pct']}%)")
    print(f"  全部触发成本: {pt['total_cost_if_all_fill']}元/份")
    print(f"  最坏浮亏: {pt['worst_unreal_loss']}元/份")
    if pt.get('progressive_extra_cost'):
        print(f"  逐格加码额外: {pt['progressive_extra_cost']}元/份")

    # 模拟不同价格
    print("\n[网格触发模拟]")
    prices = [0.5, 0.475, 0.45, 0.43, 0.40, 0.38, 0.35, 0.30, 0.25]
    for p in prices:
        r = engine.sim_trigger(p)
        rec = engine.get_recommendation(p)
        buys = len(r['buys'])
        sells = len(r['sells'])
        print(f"  价格={p:.3f} | 触发买{buys}层 卖{sells}层 | {rec}")


if __name__ == '__main__':
    main()

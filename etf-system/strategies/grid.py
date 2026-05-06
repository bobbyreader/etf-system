"""
E大"长赢"体系 - 网格策略引擎
适用于高波动品种（油气等）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class GridEngine:
    """
    E大网格策略

    核心逻辑：
    - 设定基准价格和网格间距
    - 价格每下跌一个网格间距 → 买入1份
    - 价格每上涨一个网格间距 → 卖出1份
    - 不预测，只应对
    """

    def __init__(self, name: str, base_price: float, total_grids: int = 10,
                 grid_spacing: float = 5.0, initial_lots: int = 1):
        """
        name: 品种名
        base_price: 基准价格（开始网格的起点）
        total_grids: 网格层数
        grid_spacing: 每层间距百分比(%)
        initial_lots: 初始每层份数
        """
        self.name = name
        self.base_price = base_price
        self.total_grids = total_grids
        self.grid_spacing = grid_spacing  # e.g. 5 = 5%
        self.initial_lots = initial_lots

        # 计算每层触发价格
        self.levels = []
        price = base_price
        for i in range(total_grids):
            trigger = round(price * (1 - grid_spacing / 100), 4)
            self.levels.append({
                'level': i + 1,
                'trigger_price': trigger,
                'trigger_pct': round((trigger - base_price) / base_price * 100, 2),
                'action': 'BUY',
                'lots': initial_lots,
                'filled': False,
                'filled_price': None,
            })
            price = trigger

    def check_signal(self, current_price: float) -> dict:
        """
        检查当前价格是否触发网格信号
        返回: {action, level, trigger_price, lots, message}
        """
        signals = []

        for level in self.levels:
            if not level['filled'] and current_price <= level['trigger_price']:
                level['filled'] = True
                level['filled_price'] = current_price
                signals.append({
                    'action': 'BUY',
                    'level': level['level'],
                    'trigger_price': level['trigger_price'],
                    'filled_price': current_price,
                    'lots': level['lots'],
                    'message': (f"[{self.name}] 网格L{level['level']}触发: "
                               f"价格${current_price:.4f} ≤ 触发价${level['trigger_price']:.4f}, "
                               f"买入{level['lots']}份"),
                })

        return {
            'triggered': len(signals) > 0,
            'signals': signals,
            'current_price': current_price,
            'levels_status': self.get_status(),
        }

    def get_status(self) -> list:
        """获取所有网格层状态"""
        return [
            {
                'level': l['level'],
                'trigger': l['trigger_price'],
                'pct': l['trigger_pct'],
                'filled': l['filled'],
                'filled_price': l.get('filled_price'),
            }
            for l in self.levels
        ]

    def print_grid(self, current_price: float = None):
        """打印网格状态"""
        print(f"\n  {'='*50}")
        print(f"  网格: {self.name}")
        print(f"  基准价: {self.base_price:.4f}  间距: {self.grid_spacing}%  "
              f"总层数: {self.total_grids}")
        print(f"  {'-'*50}")
        print(f"  {'层级':>5} {'触发价':>10} {'距基准':>8} {'状态':>8} {'成交价':>10}")
        print(f"  {'-'*50}")
        for l in self.levels:
            status = '✅已买' if l['filled'] else '⬜待触发'
            fp = f"{l['filled_price']:.4f}" if l.get('filled_price') else '-'
            print(f"  L{l['level']:>3}   {l['trigger_price']:>10.4f}  "
                  f"{l['trigger_pct']:>7.2f}%  {status:>8}  {fp:>10}")
        if current_price:
            print(f"  {'-'*50}")
            print(f"  当前价: {current_price:.4f}  "
                  f"距基准: {(current_price/self.base_price-1)*100:+.2f}%")


# ══════════════════════════════════════════════════════════════════════
# E大实际网格参数（从PDF提取）
# 华宝油气：基准价~0.55，间距5%，10层
# 恒生目标市值：2015年1.3元起，目标市值策略
# ══════════════════════════════════════════════════════════════════════

def create_油气_grid():
    """华宝油气网格（E大实际使用参数）"""
    # E大2015-2019年华宝油气网格参考参数
    return GridEngine(
        name='华宝油气',
        base_price=0.55,      # 基准价格
        total_grids=10,       # 10层
        grid_spacing=5.0,     # 每层5%
        initial_lots=1,       # 每层1份
    )


def create_恒生_target_market(current_cost: float, current_shares: int,
                               target_value: float) -> dict:
    """
    恒生ETF目标市值策略

    逻辑（E大2015-2019持续使用）：
    - 低估区持续买入，直到市值达到目标
    - 市值达标后：每上涨10%卖出一份
    - 每下跌5%补入一份

    current_cost: 当前买入均价
    current_shares: 当前持仓份数
    target_value: 目标市值
    """
    return {
        'strategy': '目标市值',
        '品种': '恒生ETF',
        '当前成本': current_cost,
        '持仓份数': current_shares,
        '目标市值': target_value,
        '逻辑': (
            "低估区持续买入直到市值达标 → 达标后越涨越卖\n"
            "每涨10%卖1份，每跌5%补1份"
        ),
    }


def main():
    """网格演示"""
    grid = create_油气_grid()
    grid.print_grid()

    # 模拟价格下跌触发
    print("\n  --- 模拟价格下跌触发 ---")
    test_prices = [0.55, 0.52, 0.50, 0.47, 0.45, 0.43, 0.41]
    for price in test_prices:
        result = grid.check_signal(price)
        if result['triggered']:
            for sig in result['signals']:
                print(f"\n  🚨 {sig['message']}")

    grid.print_grid(current_price=0.40)


if __name__ == '__main__':
    main()

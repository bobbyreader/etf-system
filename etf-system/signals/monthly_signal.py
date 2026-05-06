"""
E大"长赢"体系 - 月度信号生成器
150份计划的份数管理 + 品种优先级排序
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime
from strategies.valuation import ValuationEngine
from strategies.universe import UNIVERSE, PE_UNIVERSE


class SignalGenerator:
    """
    月度信号生成器
    核心逻辑：
    1. 获取所有品种估值分位
    2. 按分位排序，最低估的优先买
    3. 生成150份计划份数建议
    4. 生成心理按摩话术
    """

    def __init__(self, total_shares: int = 150):
        self.total_shares = total_shares
        self.engine = ValuationEngine(data_dir='./data')

    def generate_monthly_report(self, portfolio: dict = None) -> pd.DataFrame:
        """
        生成月度信号报告

        portfolio: dict，键=品种名，值={持仓份数, 成本, 浮亏比例}
        示例：
        {
            '50ETF': {'shares': 5, 'cost': 2.8, 'current': 3.1},
            '恒生ETF': {'shares': 8, 'cost': 1.1, 'current': 1.0},
        }
        """
        df = self.engine.generate_all_signals(PE_UNIVERSE)

        # 添加优先级（分位越低优先级越高）
        df['_分位数值'] = df['综合分位'].apply(lambda x: float(x.replace('%','')) if isinstance(x, str) and x != '需手动' else 50.0)
        df = df.sort_values('_分位数值')

        # 过滤商品（手动）
        signals = df[df['操作'] != '手动'].copy()

        # 生成优先级
        signals['优先级'] = range(1, len(signals) + 1)

        # 汇总
        buys = signals[signals['操作'] == 'BUY']
        sells = signals[signals['操作'] == 'SELL']
        holds = signals[signals['操作'] == 'HOLD']

        return signals, buys, sells, holds

    def generate_150_plan(self, signals_df: pd.DataFrame,
                          current_holdings: dict = None,
                          cash_ratio: float = 1.0) -> dict:
        """
        生成150份操作计划

        current_holdings: {品种: 已持仓份数}
        cash_ratio: 剩余资金比例 (0-1)
        """
        if current_holdings is None:
            current_holdings = {}

        plan = {
            '生成时间': datetime.now().strftime('%Y-%m-%d %H:%M'),
            '已用份数': sum(current_holdings.values()),
            '可用份数': self.total_shares - sum(current_holdings.values()),
            '资金充足度': f"{cash_ratio*100:.0f}%",
            '买入建议': [],
            '卖出建议': [],
            '持仓建议': [],
            '心理话术': '',
        }

        # 分配份数
        available = self.total_shares - sum(current_holdings.values())

        for _, row in signals_df.iterrows():
            name = row['品种']
            action = row['操作']
            base_shares = row['份数']
            held = current_holdings.get(name, 0)
            pct = row['_分位数值']

            # 资金不足时缩减份数
            if available <= 0:
                actual_shares = 0
            elif action == 'BUY':
                # 极度低估(分位<15)时加倍
                if pct < 15:
                    actual_shares = min(base_shares * 2, 3)
                else:
                    actual_shares = base_shares
                available -= actual_shares
            elif action == 'SELL':
                actual_shares = min(base_shares, held) if held > 0 else 0
            else:
                actual_shares = 0

            if actual_shares > 0 or held > 0:
                plan['持仓建议'].append({
                    '品种': name,
                    '操作': action,
                    '建议份数': actual_shares,
                    '已持仓': held,
                    '分位': row['综合分位'],
                    '强度': row['强度'],
                    '最大跌幅': row['最大跌幅'],
                })

            if action == 'BUY' and actual_shares > 0:
                plan['买入建议'].append({
                    '品种': name,
                    '份数': actual_shares,
                    '理由': row['强度'],
                    '最大跌幅': row['最大跌幅'],
                    'PE': row['PE_TTM'],
                    'PE分位': row['PE分位'],
                })

            if action == 'SELL' and actual_shares > 0:
                plan['卖出建议'].append({
                    '品种': name,
                    '份数': actual_shares,
                    '理由': row['强度'],
                    'PE分位': row['PE分位'],
                })

        # 生成心理话术
        plan['心理话术'] = self._generate_psychology_copy(plan, signals_df)

        return plan

    def _generate_psychology_copy(self, plan: dict, signals_df: pd.DataFrame) -> str:
        """生成E大风格的心理按摩话术"""
        buys = plan['买入建议']
        sells = plan['卖出建议']
        avg_pct = signals_df['_分位数值'].mean() if len(signals_df) > 0 else 50

        if avg_pct < 20:
            tone = "历史性机会期"
            copy = (
                f"【{datetime.now().strftime('%Y年%m月')}心理按摩】\n\n"
                f"当前市场综合分位约{avg_pct:.0f}%，处于历史性低估区域。\n"
                f"多个品种已进入重仓买入区间。\n\n"
                f"记住E大的话：跌得越多，买得越多。不要怕熊市，越长越好。\n"
                f"你能买的更多。无非是时间嘛，给点耐心。\n\n"
                f"本轮买入后，请做好最大跌幅的心理准备：\n"
            )
            for b in buys:
                copy += f"  · {b['品种']} 最大跌幅{b['最大跌幅']}\n"
            copy += "\n这些跌幅是正常的，不是错误。\n"
            copy += "历史上，每一次这样的时候，最终都给投资者丰厚的回报。\n"
            copy += "握紧筹码，等待微笑曲线。\n"

        elif avg_pct < 40:
            tone = "正常布局期"
            copy = (
                f"【{datetime.now().strftime('%Y年%m月')}心理按摩】\n\n"
                f"当前市场综合分位约{avg_pct:.0f}%，处于正常偏低区域。\n"
                f"估值有吸引力，可以继续布局。\n\n"
                f"记住：我们的目标不是在最低点买满，而是在合理价格慢慢收集筹码。\n"
                f"越低估买越多，这才是节奏。\n"
            )

        elif avg_pct < 60:
            tone = "持有观察期"
            copy = (
                f"【{datetime.now().strftime('%Y年%m月')}心理按摩】\n\n"
                f"当前市场综合分位约{avg_pct:.0f}%，整体处于正常偏高区域。\n"
                f"部分品种值得继续持有，部分需要警惕。\n\n"
                f"E大说过：到了牛市，人声鼎沸，大部分时间都是噪音。\n"
                f"如果你的操作跟大部分人一样，那收益也就跟大部分人一样——亏钱。\n"
                f"保持仓位，等待高估区域的收割时机。\n"
            )

        else:
            tone = "收割警惕期"
            copy = (
                f"【{datetime.now().strftime('%Y年%m月')}心理按摩】\n\n"
                f"当前市场综合分位约{avg_pct:.0f}%，已进入高估区域。\n"
                f"请注意逐步收割利润。\n\n"
                f"E大说过：牛市不是比谁赚最多，是比谁保住利润。\n"
                f"身边的噪音会越来越大，请保持清醒。\n"
            )

        return copy

    def print_monthly_report(self, plan: dict, signals_df: pd.DataFrame):
        """打印月度报告"""
        print("\n" + "=" * 75)
        print(f"  E大150份计划  月度信号报告  {datetime.now().strftime('%Y-%m-%d')}")
        print("=" * 75)

        # 信号总览
        print(f"\n  信号总览:")
        print(f"  已用份数: {plan['已用份数']}/{self.total_shares}  "
              f"可用: {plan['可用份数']}份  资金:{plan['资金充足度']}")

        buys = plan['买入建议']
        sells = plan['卖出建议']
        if buys:
            print(f"\n  🟢 买入建议 ({len(buys)}个品种)")
            print(f"  {'品种':<12} {'份数':>5} {'PE分位':>8} {'强度':>8} {'最大跌幅':>10}")
            print("  " + "-" * 50)
            for b in buys:
                print(f"  {b['品种']:<12} {b['份数']:>5} {b['PE分位']:>8} "
                      f"{b['强度']:>8} {b['最大跌幅']:>10}")
        else:
            print(f"\n  🟡 本月无买入建议")

        if sells:
            print(f"\n  🔴 卖出建议 ({len(sells)}个品种)")
            for s in sells:
                print(f"  · {s['品种']} 卖出{s['份数']}份 ({s['理由']})")

        # 持仓状态
        holds = plan['持仓建议']
        if holds:
            print(f"\n  持仓状态 ({len(holds)}个品种)")
            for h in holds:
                op_icon = {'BUY': '🟢+', 'SELL': '🔴-', 'HOLD': '🟡='}.get(h['操作'], '  ')
                print(f"  {op_icon} {h['品种']:<12} 持仓:{h['已持仓']:>3}份  "
                      f"本次:{h['建议份数']:>2}份  分位:{h['分位']:>7}  {h['强度']}")

        # 心理话术
        print("\n" + "-" * 75)
        print(plan['心理话术'])
        print("=" * 75)


def main():
    """月度报告入口"""
    gen = SignalGenerator(total_shares=150)

    # 模拟持仓（E大2019年初的大致状态）
    holdings = {
        '50ETF': 5,
        '中证500ETF': 2,
        '中证红利': 3,
        '恒生ETF': 8,
    }

    signals_df, buys, sells, holds = gen.generate_monthly_report()
    plan = gen.generate_150_plan(signals_df, current_holdings=holdings, cash_ratio=0.8)
    gen.print_monthly_report(plan, signals_df)


if __name__ == '__main__':
    main()

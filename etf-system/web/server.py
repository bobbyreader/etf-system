"""
E大长赢系统 - Web 服务端
启动: python web/server.py
访问: http://localhost:5000
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request

from strategies.valuation import ValuationEngine
from portfolio.manager import PortfolioManager


app = Flask(__name__)
app.template_folder = '.'

DATA_DIR = Path(__file__).parent.parent / 'data'


@app.route('/')
def index():
    return render_template('ui.html')


@app.route('/status.json')
def status_json():
    """生成信号数据 JSON"""
    engine = ValuationEngine(data_dir=str(DATA_DIR))
    df = engine.generate_all_signals()

    signals = []
    for _, row in df.iterrows():
        try:
            pct_str = str(row.get('综合分位', '50%')).replace('%', '')
            score = float(pct_str)
        except:
            score = 50.0

        hist = row.get('历史', {}) or {}
        action = row.get('操作', 'HOLD')

        signals.append({
            'name': row.get('品种', ''),
            'code': row.get('代码', ''),
            'pe_ttm': row.get('PE_TTM'),
            'pe_static': row.get('PE_静态'),
            'pb': row.get('PB'),
            'score': f"{score:.1f}%",
            'pct': score,
            'pe_pct': str(row.get('PE分位', 'N/A')),
            'pb_pct': str(row.get('PB分位', 'N/A')),
            'action': action,
            'shares': row.get('份数', 0),
            'intensity': row.get('强度', ''),
            'max_drop': row.get('最大跌幅', ''),
            'price': row.get('ETF价格'),
            'date': row.get('数据日期', ''),
            'history': {
                'pe_min': hist.get('pe_ttm_min'),
                'pe_max': hist.get('pe_ttm_max'),
                'pe_mean': hist.get('pe_ttm_mean'),
                'note': '10年滚动窗口分位',
            },
            'ma_trend': row.get('均线趋势'),
            'zone': row.get('估值区间', ''),
            'zone_emoji': row.get('估值emoji', ''),
            'zone_color': row.get('估值color', ''),
            'advice': row.get('投资建议', ''),
            'e_note': row.get('E大原话', ''),
            'max_drop_detailed': row.get('最大跌幅详细', {}),
        })

    # 汇总
    buys = [s for s in signals if s['action'] == 'BUY']
    sells = [s for s in signals if s['action'] == 'SELL']
    pcts = [s['pct'] for s in signals if not s['score'].startswith('需')]

    # 估值区间分布
    zone_counts = {}
    for s in signals:
        z = s.get('zone', '未知')
        zone_counts[z] = zone_counts.get(z, 0) + 1

    return jsonify({
        'generated': datetime.now().isoformat(),
        'signals': signals,
        'summary': {
            'total': len(signals),
            'buy': len(buys),
            'sell': len(sells),
            'avg_pct': round(sum(pcts) / len(pcts), 1) if pcts else 50.0,
            'buy_names': [s['name'] for s in buys],
            'sell_names': [s['name'] for s in sells],
            'zone_distribution': zone_counts,
            'market_outlook': _build_market_outlook(signals, zone_counts),
        }
    })


def _build_market_outlook(signals, zone_counts):
    """根据估值区间分布生成市场展望"""
    if not signals:
        return '暂无数据'

    diamond = zone_counts.get('钻石坑', 0)
    gold = zone_counts.get('黄金坑', 0)
    low = zone_counts.get('正常偏低', 0)
    high = zone_counts.get('正常偏高', 0)
    rich = zone_counts.get('高估', 0) + zone_counts.get('极度高估', 0)

    total = len(signals)
    if diamond >= 1:
        return '💎 市场处于钻石坑区域，是历史性战略建仓机会。保持信心，持续买入。'
    elif gold >= 2:
        return '🥇 市场整体低估，遍地黄金。低估品种积极买入，高估品种分批止盈。'
    elif rich >= 2:
        return '⚠️ 市场整体高估，注意风险。高估品种逐步清仓，保留现金等待机会。'
    elif high >= 3:
        return '⚖️ 市场估值偏高，部分品种进入高估区间。谨慎加仓，准备止盈。'
    elif low >= 3:
        return '📊 市场估值正常偏低，保持耐心持有。等待估值回归或继续积累便宜筹码。'
    else:
        return '📊 市场整体估值处于正常区间，均衡配置，耐心等待。'


@app.route('/portfolio.json')
def portfolio_json():
    """生成持仓数据 JSON"""
    pm = PortfolioManager(data_dir=str(DATA_DIR))

    # 获取当前价格
    engine = ValuationEngine(data_dir=str(DATA_DIR))
    current_prices = {}
    for name in pm.get_positions():
        sig = engine.generate_signal(name)
        if sig and sig.get('ETF价格'):
            current_prices[name] = sig['ETF价格']

    summary = pm.get_summary()
    pnl = pm.calc_unrealized_pnl(current_prices) if current_prices else {'positions': [], '总浮盈亏(万)': 0}

    return jsonify({
        'generated': datetime.now().isoformat(),
        'updated': pm.data.get('updated', ''),
        'total_shares': pm.data.get('total_shares', 150),
        'cash': summary['cash'],
        'positions': pm.data.get('positions', {}),
        'history': pm.data.get('history', [])[-20:],
        'unrealized_pnl': {
            'total': pnl.get('总浮盈亏(万)', 0),
            'pct': pnl.get('总浮盈亏率', 0),
            'positions': pnl.get('positions', []),
        }
    })


@app.route('/execute.json', methods=['POST'])
def execute_json():
    """执行买卖操作"""
    data = request.get_json() or {}
    buys = data.get('buys', [])
    sells = data.get('sells', [])
    date = data.get('date')

    pm = PortfolioManager(data_dir=str(DATA_DIR))
    engine = ValuationEngine(data_dir=str(DATA_DIR))

    # 把 name 转成品种（与 manager.py 接口对齐）
    buys = [{'品种': x['name'], '份数': x['shares']} for x in data.get('buys', []) if x.get('name')]
    sells = [{'品种': x['name'], '份数': x['shares']} for x in data.get('sells', []) if x.get('name')]

    # 获取实时价格
    prices = {}
    for item in buys + sells:
        sig = engine.generate_signal(item['品种'])
        if sig and sig.get('ETF价格'):
            prices[item['品种']] = sig['ETF价格']

    result = pm.execute_plan(buys, sells, prices=prices, date=date)
    return jsonify(result)


def main():
    print("=" * 50)
    print("  E大长赢系统 Web UI")
    print("=" * 50)
    print("  访问: http://localhost:5000")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5188, debug=False)


if __name__ == '__main__':
    main()

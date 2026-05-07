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
from flask import Flask, render_template, jsonify, send_from_directory

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
            }
        })

    # 汇总
    buys = [s for s in signals if s['action'] == 'BUY']
    sells = [s for s in signals if s['action'] == 'SELL']
    pcts = [s['pct'] for s in signals if not s['score'].startswith('需')]

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
        }
    })


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
>>>>>>> 5f289aa (fix: 修复中证红利价格NaN + 标注10年滚动窗口分位)

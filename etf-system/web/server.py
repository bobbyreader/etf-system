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
from strategies.grid_engine import GridEngine, GridConfig
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


def _build_asset_allocation(pm, total):
    """构建大类资产配置分布"""
    from strategies.universe import UNIVERSE, ASSET_CLASS_LIMITS
    TYPE_LABELS = {
        'broad': '宽基A股', 'hk': '港股', 'overseas': '海外成熟',
        'commodity': '商品', 'sector': '行业', 'other': '其他',
    }
    TYPE_COLORS = {
        'broad': '#5b9cf6', 'hk': '#f59e0b', 'overseas': '#8b5cf6',
        'commodity': '#c9a84c', 'sector': '#2dd4a0', 'other': '#6b7280',
    }
    pos_dict = pm.data.get('positions', {})
    items = []
    for name, pos in pos_dict.items():
        info = UNIVERSE.get(name, {})
        cls = info.get('type', 'other')
        shares = pos.get('shares', 0)
        pct = shares / total * 100 if total > 0 else 0
        items.append({
            'name': name, 'type': cls, 'label': TYPE_LABELS.get(cls, '其他'),
            'shares': shares, 'pct': round(pct, 1), 'avg_cost': pos.get('avg_cost', 0),
        })
    class_map = {}
    for it in items:
        cls = it['type']
        if cls not in class_map:
            class_map[cls] = {'label': TYPE_LABELS.get(cls, '其他'), 'color': TYPE_COLORS.get(cls, '#6b7280'), 'shares': 0, 'pct': 0}
        class_map[cls]['shares'] += it['shares']
        class_map[cls]['pct'] += it['pct']
    for cls in class_map:
        class_map[cls]['pct'] = round(class_map[cls]['pct'], 1)
    cash_pct = pm.data.get('cash', 0) / total * 100 if total > 0 else 0
    return {
        'total': total, 'cash': pm.data.get('cash', 0),
        'cash_pct': round(cash_pct, 1), 'invested_pct': round(100 - cash_pct, 1),
        'positions': items, 'classes': list(class_map.values()),
    }


def _build_target_market(pm, engine, current_prices):
    """构建目标市值止盈建议"""
    results = []
    for name, pos in pm.data.get('positions', {}).items():
        avg_cost = pos.get('avg_cost', 0)
        shares = pos.get('shares', 0)
        cur_price = current_prices.get(name, avg_cost)
        if avg_cost <= 0 or shares <= 0:
            continue
        r = engine.calc_target_market_value(name, avg_cost, cur_price, shares)
        results.append({
            'name': name,
            'profit_pct': r['profit_pct'],
            'profit_ratio': r['profit_ratio'],
            'sell_shares': r['sell_shares'],
            'target_price': r.get('target_price', 0),
            'action': r['action'],
            'advice': r['advice'],
            'e_note': r['e_note'],
        })
    return results


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

    # 资产配置告警
    from strategies.universe import UNIVERSE, ASSET_CLASS_LIMITS
    total = pm.data.get('total_shares', 150)
    warnings = []

    # 品种级别超配
    for name, pos in pm.data.get('positions', {}).items():
        shares = pos.get('shares', 0)
        pct = shares / total * 100
        info = UNIVERSE.get(name, {})
        max_alloc = info.get('max_allocation', 0.20)
        max_shares = int(max_alloc * total)
        if shares > max_shares:
            warnings.append({
                'type': '品种超配',
                'level': 'warning',
                'name': name,
                'current': f'{shares}份({pct:.1f}%)',
                'limit': f'{max_shares}份({max_alloc*100:.0f}%)',
                'msg': f'{name}持仓{shares}份，占{pct:.1f}%，超过单品上限{max_alloc*100:.0f}%',
            })

    # 大类级别超配
    asset_classes = {}
    for name, pos in pm.data.get('positions', {}).items():
        info = UNIVERSE.get(name, {})
        cls = info.get('type', 'other')
        asset_classes[cls] = asset_classes.get(cls, 0) + pos.get('shares', 0)

    for cls, shares in asset_classes.items():
        pct = shares / total * 100
        limits_map = {
            'broad': ('broad', '宽基'),
            'hk': ('hk', '港股'),
            'overseas': ('us_eu', '海外'),
            'commodity': ('commodity', '商品'),
            'sector': ('sector', '行业'),
        }
        if cls in limits_map:
            key, label = limits_map[cls]
            limit = ASSET_CLASS_LIMITS.get(key, 0.20)
            max_shares = int(limit * total)
            if shares > max_shares:
                warnings.append({
                    'type': '大类超配',
                    'level': 'warning',
                    'name': label,
                    'current': f'{shares}份({pct:.1f}%)',
                    'limit': f'{max_shares}份({limit*100:.0f}%)',
                    'msg': f'{label}仓位{shares}份，占{pct:.1f}%，超过大类上限{limit*100:.0f}%',
                })

    return jsonify({
        'generated': datetime.now().isoformat(),
        'updated': pm.data.get('updated', ''),
        'total_shares': total,
        'cash': summary['cash'],
        'positions': pm.data.get('positions', {}),
        'history': pm.data.get('history', [])[-20:],
        'warnings': warnings,
        'asset_allocation': _build_asset_allocation(pm, total),
        'unrealized_pnl': {
            'total': pnl.get('总浮盈亏(万)', 0),
            'pct': pnl.get('总浮盈亏率', 0),
            'positions': pnl.get('positions', []),
            'target_market': _build_target_market(pm, engine, current_prices),
        }
    })


@app.route('/grid.json')
def grid_json():
    """网格策略状态"""
    GRID_NAMES = ['华宝油气']  # 网格品种列表

    engine = ValuationEngine(data_dir=str(DATA_DIR))
    grids = []

    for name in GRID_NAMES:
        price = engine.fetch_etf_price(name)
        if price is None:
            continue

        # 华宝油气默认配置
        cfg = GridConfig(
            name=name, base_price=price,
            grid_pct=5.0, n_grids=8,
            max_drop_pct=50.0,
            keep_profit=True, keep_ratio=0.05,
            progressive=True, progressive_pct=5.0,
            multi_grid=True,
        )
        eng = GridEngine(name, cfg)

        # 获取实时状态
        status = eng.get_grid_status(price)
        pt = eng.pressure_test()
        sim = eng.sim_trigger(price)
        rec = eng.get_recommendation(price)

        grids.append({
            'name': name,
            'current_price': price,
            'status': status,
            'pressure_test': pt,
            'pending_buys': sim['buys'],
            'pending_sells': sim['sells'],
            'recommendation': rec,
        })

    return jsonify({
        'generated': datetime.now().isoformat(),
        'grids': grids,
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

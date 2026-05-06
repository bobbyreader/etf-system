"""
E大"长赢"投资体系 - 品种定义与配置
从PDF中提取的实际品种清单
"""

UNIVERSE = {
    '50ETF': {
        'code': '510050', 'name': '上证50ETF', 'market': 'SH', 'type': 'broad',
        'pe_weight': 0.8, 'pb_weight': 0.2,
        'note': '大盘价值，E大核心品种', 'max_allocation': 0.20,
    },
    '180ETF': {
        'code': '510180', 'name': '上证180ETF', 'market': 'SH', 'type': 'broad',
        'pe_weight': 0.8, 'pb_weight': 0.2,
        'note': '大盘蓝筹', 'max_allocation': 0.20,
    },
    '深100ETF': {
        'code': '159901', 'name': '深证100ETF', 'market': 'SZ', 'type': 'broad',
        'pe_weight': 0.8, 'pb_weight': 0.2,
        'note': '大盘成长', 'max_allocation': 0.20,
    },
    '中证500ETF': {
        'code': '510500', 'name': '中证500ETF', 'market': 'SH', 'type': 'broad',
        'pe_weight': 0.9, 'pb_weight': 0.1,
        'note': '中盘成长，2016年后E大持续买入', 'max_allocation': 0.20,
    },
    '中证红利': {
        'code': '100032', 'name': '富国中证红利增强', 'market': '场外', 'type': 'broad',
        'pe_weight': 0.6, 'pb_weight': 0.4,
        'note': '价值型，E大长期定投标的', 'max_allocation': 0.15,
    },
    '恒生ETF': {
        'code': '159920', 'name': '华夏恒生ETF', 'market': 'SZ', 'type': 'hk',
        'pe_weight': 0.7, 'pb_weight': 0.3,
        'note': '港股核心，目标市值策略，无免费PE数据', 'max_allocation': 0.20,
        'target_market_value': True, 'use_price_signal': True,
    },
    '德国30': {
        'code': '513030', 'name': '华安德国30DAX', 'market': 'SH', 'type': 'overseas',
        'pe_weight': 0.8, 'pb_weight': 0.2,
        'note': '少量配置，无免费PE数据', 'max_allocation': 0.10,
        'use_price_signal': True,
    },
    '黄金ETF': {
        'code': '518880', 'name': '国泰黄金ETF', 'market': 'SH', 'type': 'commodity',
        'pe_weight': 0.0, 'pb_weight': 0.0,
        'note': '避险资产，参考金银比/美元指数', 'max_allocation': 0.10,
        'use_price_signal': True,
    },
    '华宝油气': {
        'code': '162411', 'name': '华宝标普油气', 'market': '场外', 'type': 'commodity',
        'pe_weight': 0.0, 'pb_weight': 0.0,
        'note': '高波动，网格策略主力品种', 'max_allocation': 0.08,
        'use_price_signal': True, 'use_grid': True,
    },
    '养老产业': {
        'code': '000968', 'name': '广发养老产业', 'market': '场外', 'type': 'sector',
        'pe_weight': 0.8, 'pb_weight': 0.2,
        'note': '2016年E大纳入，无免费PE数据', 'max_allocation': 0.12,
        'use_price_signal': True,
    },
}

# PE数据可用的品种（akshare stock_index_pe_lg）
PE_UNIVERSE = ['50ETF', '180ETF', '深100ETF', '中证500ETF', '中证红利']
# 手动判断品种（无免费PE数据）
MANUAL_UNIVERSE = ['恒生ETF', '黄金ETF', '华宝油气', '养老产业', '德国30']
# 全品种
ALL_UNIVERSE = PE_UNIVERSE + MANUAL_UNIVERSE

# akshare PE接口中文名称映射
INDEX_PE_NAME = {
    '50ETF':      '上证50',
    '180ETF':     '上证180',
    '深100ETF':   '深证100',
    '中证500ETF': '中证500',
    '中证红利':   '深证红利',
}

# ETF新浪代码
ETF_PRICE_CODES = {
    '50ETF': 'sh510050', '180ETF': 'sh510180', '深100ETF': 'sz159901',
    '中证500ETF': 'sh510500', '黄金ETF': 'sh518880', '恒生ETF': 'sz159920',
    '德国30': 'sh513030', '华宝油气': 'sz162411',
}

# 大类资产配置上限（E大2015年原文）
ASSET_CLASS_LIMITS = {
    'bond_cash': 0.75, 'hk': 0.50, 'us_eu': 0.15, 'gold': 0.10,
    'broad': 0.20, 'sector': 0.15, 'commodity': 0.10,
}

# 估值分位 → 操作决策表
VALUATION_RULES = {
    (0, 15):   {'action': 'BUY',  'shares': 3, 'intensity': '重仓买', 'max_drop': '15%-25%'},
    (15, 30): {'action': 'BUY',  'shares': 1, 'intensity': '正常买', 'max_drop': '25%-35%'},
    (30, 50): {'action': 'HOLD', 'shares': 0, 'intensity': '持有',   'max_drop': '30%-40%'},
    (50, 70): {'action': 'HOLD', 'shares': 0, 'intensity': '警惕',   'max_drop': '35%-45%'},
    (70, 85): {'action': 'SELL', 'shares': 1, 'intensity': '少量卖', 'max_drop': 'N/A'},
    (85, 100):{'action': 'SELL', 'shares': 2, 'intensity': '大量卖', 'max_drop': 'N/A'},
}

def get_valuation_action(score: float) -> dict:
    for (low, high), rule in VALUATION_RULES.items():
        if low <= score < high:
            return rule
    if score <= 0:
        return VALUATION_RULES[(0, 15)]
    return VALUATION_RULES[(85, 100)]

def get_max_drop(品种名: str, score: float) -> str:
    drops = {
        (0, 15):  {'default': '15%-25%', '恒生ETF': '20%-30%', '华宝油气': '40%-50%'},
        (15, 30): {'default': '25%-35%', '恒生ETF': '30%-40%', '华宝油气': '45%-55%'},
        (30, 50): {'default': '30%-40%', '恒生ETF': '35%-45%', '华宝油气': '50%-60%'},
    }
    for (low, high), dmap in drops.items():
        if low <= score < high:
            return dmap.get(品种名, dmap['default'])
    return '未知'

"""
E大"长赢"投资体系 - 估值引擎 v3（生产可用版）
整合PE/PB历史分位 + ETF实时价格 + 信号生成
"""

import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime
from pathlib import Path
from typing import Optional
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from strategies.universe import (
    UNIVERSE, PE_UNIVERSE, MANUAL_UNIVERSE, ALL_UNIVERSE,
    get_valuation_action, get_max_drop
)


# ══════════════════════════════════════════════════════════════════════
# 数据映射
# ══════════════════════════════════════════════════════════════════════

# 指数 → akshare PE/PB接口的中文名称
INDEX_PE_NAMES = {
    '50ETF':      '上证50',
    '180ETF':     '上证180',
    '深100ETF':   '深证100',
    '中证500ETF': '中证500',
    '中证红利':   '深证红利',
}

# ETF代码 → 新浪市场前缀
ETF_PRICE_CODES = {
    '50ETF':      'sh510050',
    '180ETF':     'sh510180',
    '深100ETF':   'sz159901',
    '中证500ETF': 'sh510500',
    '黄金ETF':    'sh518880',
    '恒生ETF':    'sz159920',
    '德国30':     'sh513030',
    '华宝油气':   'sz162411',
}

# ══════════════════════════════════════════════════════════════════════
# 核心引擎
# ══════════════════════════════════════════════════════════════════════

class ValuationEngine:
    """
    E大估值引擎：获取指数PE/PB历史 → 计算分位 → 生成买卖信号
    """

    def __init__(self, data_dir: str = './data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ─── 数据获取 ────────────────────────────────────────────────────

    def fetch_pe_history(self, 品种名: str, years: int = 10) -> Optional[pd.DataFrame]:
        """获取指数PE(TTM)历史"""
        cache = self.data_dir / f'{品种名}_pe.csv'
        name = INDEX_PE_NAMES.get(品种名)
        if not name:
            return None

        # 读缓存
        if cache.exists():
            df = pd.read_csv(cache, parse_dates=['日期'])
            df = df[df['日期'] >= datetime.now() - pd.DateOffset(years=years)]
            if len(df) >= 50:
                return df

        try:
            raw = ak.stock_index_pe_lg(symbol=name)
            if raw is None or raw.empty:
                return None
            df = pd.DataFrame({
                '日期': pd.to_datetime(raw['日期']),
                'TTM': pd.to_numeric(raw['滚动市盈率'], errors='coerce'),
                'Static': pd.to_numeric(raw['静态市盈率'], errors='coerce'),
            })
            df = df.dropna(subset=['日期', 'TTM']).sort_values('日期').reset_index(drop=True)
            # 全量缓存
            df.to_csv(cache, index=False)
            print(f"  [CACHE] {品种名} PE: {len(df)}条")
            # 返回近N年
            return df[df['日期'] >= datetime.now() - pd.DateOffset(years=years)]
        except Exception as e:
            print(f"  [ERROR] {品种名} PE: {e}")
            return None

    def fetch_pb_history(self, 品种名: str, years: int = 10) -> Optional[pd.DataFrame]:
        """获取指数PB历史"""
        cache = self.data_dir / f'{品种名}_pb.csv'
        name = INDEX_PE_NAMES.get(品种名)
        if not name:
            return None

        if cache.exists():
            df = pd.read_csv(cache, parse_dates=['日期'])
            df = df[df['日期'] >= datetime.now() - pd.DateOffset(years=years)]
            if len(df) >= 50:
                return df

        try:
            raw = ak.stock_index_pb_lg(symbol=name)
            if raw is None or raw.empty:
                return None
            df = pd.DataFrame({
                '日期': pd.to_datetime(raw['日期']),
                'PB': pd.to_numeric(raw['市净率'], errors='coerce'),
            })
            df = df.dropna(subset=['日期', 'PB']).sort_values('日期').reset_index(drop=True)
            df.to_csv(cache, index=False)
            print(f"  [CACHE] {品种名} PB: {len(df)}条")
            return df[df['日期'] >= datetime.now() - pd.DateOffset(years=years)]
        except Exception as e:
            print(f"  [ERROR] {品种名} PB: {e}")
            return None

    def fetch_etf_price(self, 品种名: str) -> Optional[float]:
        """获取ETF最新收盘价"""
        code = ETF_PRICE_CODES.get(品种名)
        if not code:
            return None
        try:
            df = ak.fund_etf_hist_sina(symbol=code)
            if df is not None and not df.empty:
                return float(df.iloc[-1]['close'])
        except Exception as e:
            print(f"  [ERROR] {品种名} 价格: {e}")
        return None

    # ─── 分位计算 ────────────────────────────────────────────────────

    def calc_percentile(self, pe_df: pd.DataFrame, current_pe: float,
                       col: str = 'TTM') -> float:
        """
        E大公式: (当前PE - 历史最低PE) / (历史最高PE - 历史最低PE) * 100
        """
        series = pe_df[col].dropna()
        if len(series) < 30:
            return 50.0
        p_min, p_max = series.min(), series.max()
        if p_max == p_min:
            return 50.0
        return round(float(np.clip((current_pe - p_min) / (p_max - p_min) * 100, 0, 100)), 1)

    def get_hist_stats(self, 品种名: str, years: int = 10) -> Optional[dict]:
        """历史估值统计"""
        pe_df = self.fetch_pe_history(品种名, years)
        pb_df = self.fetch_pb_history(品种名, years)
        s = {}
        if pe_df is not None:
            t = pe_df['TTM'].dropna()
            s.update({
                'pe_ttm_min': round(float(t.min()), 2),
                'pe_ttm_max': round(float(t.max()), 2),
                'pe_ttm_mean': round(float(t.mean()), 2),
                'pe_ttm_median': round(float(t.median()), 2),
                'pe_ttm_q25': round(float(t.quantile(0.25)), 2),
                'pe_ttm_q75': round(float(t.quantile(0.75)), 2),
            })
        if pb_df is not None:
            p = pb_df['PB'].dropna()
            s.update({
                'pb_min': round(float(p.min()), 2),
                'pb_max': round(float(p.max()), 2),
                'pb_mean': round(float(p.mean()), 2),
                'pb_median': round(float(p.median()), 2),
            })
        return s if s else None

    # ─── 信号生成 ────────────────────────────────────────────────────

    def generate_signal(self, 品种名: str) -> Optional[dict]:
        """生成单个品种完整信号"""
        info = UNIVERSE.get(品种名)
        if not info:
            return None

        # 商品类（不用PE）
        if info.get('use_price_signal'):
            return self._commodity_signal(品种名, info)

        pe_df = self.fetch_pe_history(品种名, 10)
        pb_df = self.fetch_pb_history(品种名, 10)
        if pe_df is None or pe_df.empty:
            return None

        latest_pe = pe_df.iloc[-1]
        current_pe_ttm = float(latest_pe['TTM'])
        current_pe_static = float(latest_pe['Static'])
        date = str(latest_pe['日期'].date())

        # 计算分位
        pe_pct = self.calc_percentile(pe_df, current_pe_ttm, 'TTM')
        pe_static_pct = self.calc_percentile(pe_df, current_pe_static, 'Static')

        pb_pct = None
        current_pb = None
        if pb_df is not None and not pb_df.empty:
            current_pb = float(pb_df.iloc[-1]['PB'])
            pb_pct = self.calc_percentile(pb_df, current_pb, 'PB')

        # 综合分位
        pw, pbw = info.get('pe_weight', 0.8), info.get('pb_weight', 0.2)
        if pe_pct and pb_pct:
            score = pe_pct * pw + pb_pct * pbw
        elif pe_pct:
            score = pe_pct
        else:
            score = 50.0

        action = get_valuation_action(score)
        max_drop = get_max_drop(品种名, score)
        stats = self.get_hist_stats(品种名, 10)
        price = self.fetch_etf_price(品种名)

        return {
            '品种': 品种名,
            '代码': info['code'],
            'PE_TTM': round(current_pe_ttm, 2),
            'PE_静态': round(current_pe_static, 2),
            'PB': round(current_pb, 2) if current_pb else None,
            'ETF价格': price,
            'PE分位': f"{pe_pct:.1f}%",
            'PB分位': f"{pb_pct:.1f}%" if pb_pct else "N/A",
            '综合分位': f"{score:.1f}%",
            '操作': action['action'],
            '份数': action['shares'],
            '强度': action['intensity'],
            '最大跌幅': max_drop,
            '数据日期': date,
            '历史': stats,
        }

    def _commodity_signal(self, 品种名: str, info: dict) -> dict:
        """大宗商品信号"""
        price = self.fetch_etf_price(品种名)
        return {
            '品种': 品种名,
            '代码': info['code'],
            'PE_TTM': 0,
            'PE_静态': 0,
            'PB': None,
            'PE分位': 'N/A',
            'PB分位': 'N/A',
            '综合分位': '需手动',
            '操作': '手动',
            '份数': 0,
            '强度': '参考宏观',
            '最大跌幅': 'N/A',
            '数据日期': datetime.now().strftime('%Y-%m-%d'),
            'ETF价格': price,
            'note': info.get('note', ''),
        }

    def generate_all_signals(self, universe: list = None) -> pd.DataFrame:
        """生成所有品种信号"""
        if universe is None:
            universe = PE_UNIVERSE
        signals = []
        for name in universe:
            sig = self.generate_signal(name)
            if sig:
                signals.append(sig)
        return pd.DataFrame(signals)

    def print_report(self, df: pd.DataFrame):
        """格式化输出信号报告"""
        print("\n" + "=" * 80)
        print(f"  E大估值信号报告  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 80)
        for _, row in df.iterrows():
            action = row['操作']
            icon = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡', '手动': '⚪'}.get(action, '⚪')
            print(f"\n  {icon} {row['品种']} ({row['代码']})")
            print(f"     PE_TTM={row['PE_TTM']}  PE分位={row['PE分位']}  PB分位={row['PB分位']}")
            print(f"     综合分位={row['综合分位']}  →  [{action}] {row['强度']} {row['份数']}份")
            print(f"     最大跌幅估算: {row['最大跌幅']}  |  日期: {row['数据日期']}")
            if row.get('历史') and isinstance(row['历史'], dict):
                h = row['历史']
                print(f"     历史区间: PE {h.get('pe_ttm_min','?')}-{h.get('pe_ttm_max','?')}  "
                      f"均值={h.get('pe_ttm_mean','?')} 中位数={h.get('pe_ttm_median','?')}")
            if row.get('ETF价格'):
                p = row['ETF价格']
                print(f"     ETF现价: {p:.3f}" if p and p == p else f"     ETF现价: --")


# ══════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════

def main():
    engine = ValuationEngine(data_dir='./data')
    print("=" * 80)
    print("  E大估值引擎 v3  —  实时信号生成")
    print("=" * 80)
    df = engine.generate_all_signals()
    engine.print_report(df)

    # 汇总
    print("\n" + "=" * 80)
    print("  信号汇总")
    print("=" * 80)
    buys = df[df['操作'] == 'BUY']
    sells = df[df['操作'] == 'SELL']
    holds = df[df['操作'] == 'HOLD']
    print(f"  买入信号: {len(buys)} 个  {list(buys['品种'].values) if len(buys) else '无'}")
    print(f"  卖出信号: {len(sells)} 个  {list(sells['品种'].values) if len(sells) else '无'}")
    print(f"  持有观望: {len(holds)} 个  {list(holds['品种'].values) if len(holds) else '无'}")


if __name__ == '__main__':
    main()

"""
趋势分析 — 销售趋势、移动平均、线性回归、变化率
提取自 modules/analysis.py 的 analyze_sales_trend
"""
import pandas as pd
import numpy as np

try:
    from scipy import stats
    def _calc_linreg(x, y):
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        return float(slope), float(r_value ** 2)
except ImportError:
    def _calc_linreg(x, y):
        if len(x) < 2:
            return 0.0, 0.0
        slope, intercept = np.polyfit(x, y, 1)
        r = np.corrcoef(x, y)[0, 1] if len(x) > 1 else 0
        return float(slope), float(r ** 2 if not np.isnan(r) else 0.0)


def analyze_sales_trend(rank_df, item_name, threshold=0.5):
    """
    对单个商品的销售序列做趋势分析。

    Args:
        rank_df: 包含 '销售数量' 列的 DataFrame（按时间排序）
        item_name: 商品名称
        threshold: 显著变化阈值 (0~1)

    Returns:
        dict with trend, confidence, total_change, avg_daily_change
    """
    if len(rank_df) < 3:
        return {
            'item_name': item_name,
            'trend': '数据不足',
            'confidence': None,
            'total_change': None,
            'avg_daily_change': None
        }

    sales = rank_df['销售数量'].values
    ma = pd.Series(sales).rolling(window=3, min_periods=1).mean().values
    slope, r_squared = _calc_linreg(range(len(sales)), sales)

    total_change = (sales[-1] - sales[0]) / sales[0] if sales[0] != 0 else 0.0
    daily_changes = np.diff(sales) / np.where(sales[:-1] != 0, sales[:-1], np.nan)
    avg_daily_change = float(np.nanmean(daily_changes))

    if total_change > threshold:
        trend = "增长"
        confidence = "高" if r_squared > 0.6 else "中"
    elif total_change < -threshold:
        trend = "下降"
        confidence = "高" if r_squared > 0.6 else "中"
    else:
        trend = "无显著变化"
        confidence = "低"

    return {
        'item_name': item_name,
        'trend': trend,
        'confidence': confidence,
        'slope': slope,
        'r_squared': r_squared,
        'total_change': total_change,
        'avg_daily_change': avg_daily_change,
    }

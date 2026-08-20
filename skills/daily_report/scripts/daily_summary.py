"""
每日经营汇总 — 从 sales/loss/cards/weather 计算每日关键指标
提取自 modules/analysis.py 的 calculate_daily_summary
"""
import pandas as pd
import numpy as np
from modules.config import CATEGORY_COST_RATIOS


def _calc_loss_by_remark(loss_df, pattern, exclude_tasting=True):
    """按备注模式过滤报损金额"""
    mask = loss_df["备注"].str.contains(pattern, na=False)
    if exclude_tasting:
        mask &= ~loss_df["备注"].str.contains("试吃", na=False)
        mask &= loss_df["报损原因"].shift(-1).fillna('') != "试吃"
    return (
        loss_df[mask]
        .groupby("调整日期")["报损金额"]
        .sum()
        .reset_index()
        .rename(columns={"调整日期": "日期", "报损金额": pattern})
    ).fillna(0)


def _calc_tasting_loss(loss_df):
    """试吃报损"""
    mask = (
        loss_df["备注"].str.contains("试吃", na=False)
        | (loss_df["报损原因"].shift(-1).fillna('') == "试吃")
    )
    return (
        loss_df[mask]
        .groupby("调整日期")["报损金额"]
        .sum()
        .reset_index()
        .rename(columns={"调整日期": "日期", "报损金额": "试吃"})
    ).fillna(0)


def _calc_category_cost(sales_df, raw_material_ratio=0.40):
    """按商品分类计算每日成本"""
    if sales_df.empty or '商品分类' not in sales_df.columns:
        daily_cost = sales_df.groupby(sales_df['销售时间'].dt.date)['商品总价'].sum() * raw_material_ratio
        return daily_cost.reset_index().rename(columns={'销售时间': '日期', '商品总价': '商品成本'})

    s = sales_df.copy()
    s['成本率'] = s['商品分类'].map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS['default'])
    s['商品成本'] = s['商品总价'] * s['成本率']
    daily_cost = s.groupby(s['销售时间'].dt.date)['商品成本'].sum()
    return daily_cost.reset_index().rename(columns={'销售时间': '日期'})


def _calc_loss_cost(loss_df, raw_material_ratio=0.40):
    """按商品分类计算损耗成本"""
    if loss_df.empty or '商品分类' not in loss_df.columns:
        daily = loss_df.groupby('调整日期')['报损金额'].sum() * raw_material_ratio
        return daily.reset_index().rename(columns={'调整日期': '日期', '报损金额': '损耗成本'})

    l = loss_df.copy()
    l['成本率'] = l['商品分类'].map(CATEGORY_COST_RATIOS).fillna(CATEGORY_COST_RATIOS['default'])
    l['损耗成本'] = l['报损金额'] * l['成本率']
    daily = l.groupby('调整日期')['损耗成本'].sum()
    return daily.reset_index().rename(columns={'调整日期': '日期'})


def calculate_daily_summary(
    sales_df, loss_df, cards_df, financial_params, weather_df=None
):
    """
    计算每日经营汇总。

    Args:
        sales_df: sales 表 DataFrame
        loss_df: loss 表 DataFrame
        cards_df: cards 表 DataFrame
        financial_params: dict with 固定支出, 原料成本比, 运营管理
        weather_df: weather 表 DataFrame（可选）

    Returns:
        DataFrame with columns: 日期, 商品总价, 实收金额, 订单笔数, 天气,
        损耗价值总计, 试吃, 现烤报废, 西点报废, 商品成本, 损耗成本,
        运营成本, 固定支出, 净利润, 净利润率
    """
    fixed_cost = financial_params.get("固定支出", 0)
    raw_material_ratio = financial_params.get("原料成本比", 0)
    operation_management = financial_params.get("运营管理", 0)

    # 订单笔数 (TC)
    order_counts = (
        sales_df.groupby(sales_df["销售时间"].dt.date)["流水号"]
        .nunique()
        .reset_index()
        .rename(columns={"流水号": "订单笔数", "销售时间": "日期"})
    )

    # 销售汇总
    sales_summary = (
        sales_df.groupby(sales_df["销售时间"].dt.date)
        .agg({"商品总价": "sum", "实收金额": "sum"})
        .reset_index()
        .rename(columns={"销售时间": "日期"})
    )
    daily = pd.merge(sales_summary, order_counts, on="日期", how="left")

    # 天气
    if weather_df is not None and not weather_df.empty and "日期" in weather_df.columns:
        w = weather_df.copy()
        if pd.api.types.is_datetime64_any_dtype(w['日期']):
            w['日期'] = w['日期'].dt.date
        w = w.groupby("日期")["天气"].first().reset_index()
        daily = pd.merge(daily, w, on="日期", how="left")
    else:
        daily["天气"] = "无数据"

    # 损耗价值总计
    loss_value = (
        loss_df.groupby("调整日期")["报损金额"]
        .sum()
        .reset_index()
        .rename(columns={"调整日期": "日期", "报损金额": "损耗价值总计"})
    )
    daily = pd.merge(daily, loss_value, on="日期", how="left").fillna({"损耗价值总计": 0})

    # 储值卡赠送消费
    cards_summary = (
        cards_df.groupby(cards_df["日期"].dt.date)
        .agg({"赠送消费金额": "sum"})
        .reset_index()
    )
    daily = pd.merge(daily, cards_summary, on="日期", how="left").fillna({"赠送消费金额": 0})

    # 报损分类
    for pattern, col_name in [
        ("试吃", "试吃"),
        ("现烤", "现烤报废"),
        ("西点", "西点报废"),
        ("蛋糕", "蛋糕报损"),
        ("饼干", "饼干报损"),
        ("带走", "股东带走"),
        ("非正常", "非正常报损"),
    ]:
        is_tasting = pattern == "试吃"
        if is_tasting:
            ldf = _calc_tasting_loss(loss_df)
        else:
            ldf = _calc_loss_by_remark(loss_df, pattern)
        daily = pd.merge(daily, ldf, on="日期", how="left").fillna({ldf.columns[-1]: 0})
        if ldf.columns[-1] != col_name:
            daily = daily.rename(columns={ldf.columns[-1]: col_name})

    # 成本和利润
    daily["固定支出"] = fixed_cost
    daily["原料成本比"] = raw_material_ratio
    daily["运营管理"] = operation_management

    category_costs = _calc_category_cost(sales_df, raw_material_ratio)
    daily = pd.merge(daily, category_costs, on="日期", how="left").fillna({"商品成本": 0})

    loss_costs = _calc_loss_cost(loss_df, raw_material_ratio)
    daily = pd.merge(daily, loss_costs, on="日期", how="left").fillna({"损耗成本": 0})

    daily["运营成本"] = daily["实收金额"] * daily["运营管理"]

    daily["净利润"] = (
        daily["实收金额"]
        - daily["商品成本"]
        - daily["损耗成本"]
        - daily["运营成本"]
        - daily["固定支出"]
    )
    daily["净利润率"] = daily["净利润"] / daily["实收金额"]

    # 日期格式化
    weekday_dict = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    daily["日期"] = daily["日期"].apply(
        lambda d: d.strftime("%Y-%m-%d") + " " + weekday_dict[d.weekday()]
    )

    return daily

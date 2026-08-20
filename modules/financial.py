"""Streamlit-free financial helpers for the dashboard data path.

This module deliberately has no UI dependency so the web dashboard server can
import it without pulling in the legacy Streamlit stack.
"""
from __future__ import annotations
import pandas as pd


def get_financial_parameters(df_financial: pd.DataFrame | None) -> dict[str, float]:
    """提取财务数据中的财务参数，支持兼容多种列名及空表兜底。"""
    if df_financial is not None and not df_financial.empty:
        fixed_cost = (
            float(df_financial["固定支出"].iloc[-1])
            if "固定支出" in df_financial.columns
            else 850.0
        )
        if "原料成本比" in df_financial.columns:
            raw_material_ratio = float(df_financial["原料成本比"].iloc[0])
        elif "原料成本" in df_financial.columns:
            raw_material_ratio = float(df_financial["原料成本"].iloc[0])
        else:
            raw_material_ratio = 0.35

        if "运营管理比" in df_financial.columns:
            operation_management = float(df_financial["运营管理比"].iloc[0])
        elif "运营管理" in df_financial.columns:
            operation_management = float(df_financial["运营管理"].iloc[0])
        else:
            operation_management = 0.12
    else:
        fixed_cost = 850.0
        raw_material_ratio = 0.35
        operation_management = 0.12

    return {
        "固定支出": fixed_cost,
        "原料成本比": raw_material_ratio,
        "运营管理": operation_management,
        "运营管理比": operation_management,
    }

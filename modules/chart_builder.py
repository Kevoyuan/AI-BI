"""
Chart Builder Module
Thin adapter: converts LLM-generated chart specifications
into pyecharts or Plotly figures.
"""
import pandas as pd
import plotly.express as px
from typing import Optional


def build_chart(
    chart_type: str,
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    color: Optional[str] = None,
):
    """
    Build a Plotly figure from a chart specification.

    Args:
        chart_type: "bar" | "line" | "scatter" | "pie"
        df:         Source DataFrame
        x:          Column for x-axis (or labels for pie)
        y:          Column for y-axis (or values for pie)
        title:      Chart title
        color:      Optional grouping column

    Returns:
        plotly.graph_objects.Figure or None
    """
    if df is None or df.empty:
        return None

    ct = chart_type.lower()
    kwargs = dict(data_frame=df, title=title)

    try:
        if ct == "bar":
            return px.bar(x=x, y=y, color=color, **kwargs)
        elif ct == "line":
            return px.line(x=x, y=y, color=color, **kwargs)
        elif ct == "scatter":
            return px.scatter(x=x, y=y, color=color, **kwargs)
        elif ct == "pie":
            return px.pie(names=x, values=y, **kwargs)
        else:
            return px.bar(x=x, y=y, color=color, **kwargs)
    except Exception as exc:
        print(f"[chart_builder] Failed to build '{chart_type}' chart: {exc}")
        return None

"""
Analysis Module — public re-export shim.
The actual implementations live inside skills/ to keep the
"Thin Harness, Fat Skills" architecture intact.
"""
from skills.daily_report.scripts.daily_summary import calculate_daily_summary  # noqa: F401
from skills.deep_analysis.scripts.trend import analyze_trend                   # noqa: F401

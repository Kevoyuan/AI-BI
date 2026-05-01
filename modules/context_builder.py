"""
Context Builder
Assembles a rich business context summary from live data,
injected into the LLM system prompt so it has real numbers to work with.
"""
import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime, timedelta


def _get_day_targets(date) -> Dict[str, int]:
    """
    Return revenue / order targets for a given date.
    Targets increase on Friday → Saturday → Sunday.
    Replace these with your actual targets.
    """
    weekday = date.weekday()
    if weekday <= 3:   # Mon–Thu
        return {"revenue": 8000,  "orders": 200}
    elif weekday == 4: # Fri
        return {"revenue": 10000, "orders": 250}
    elif weekday == 5: # Sat
        return {"revenue": 15000, "orders": 380}
    else:              # Sun
        return {"revenue": 18000, "orders": 450}


def _calc_waste(df_waste: pd.DataFrame, date=None) -> Dict[str, float]:
    """Compute waste and sample amounts for a given date (or all dates)."""
    empty = {"waste_fresh": 0, "waste_pastry": 0, "waste_total": 0, "samples": 0}
    if df_waste.empty:
        return empty

    df = df_waste[df_waste["adj_date"] == date].copy() if date else df_waste.copy()
    if df.empty:
        return empty

    df["note"]   = df.get("note", pd.Series()).fillna("").astype(str)
    df["reason"] = df.get("reason", pd.Series()).fillna("").astype(str)

    if "waste_amount" not in df.columns:
        return empty

    waste_fresh = df[
        df["note"].str.contains("fresh_baked", case=False, na=False) &
        ~df["note"].str.contains("sample", case=False, na=False)
    ]["waste_amount"].sum()

    waste_pastry = df[
        df["note"].str.contains("pastry|cake", case=False, na=False) &
        ~df["note"].str.contains("sample", case=False, na=False)
    ]["waste_amount"].sum()

    samples = df[
        df["note"].str.contains("sample", case=False, na=False) |
        (df["reason"].shift(-1).fillna("") == "sample")
    ]["waste_amount"].sum()

    return {
        "waste_fresh":  float(waste_fresh),
        "waste_pastry": float(waste_pastry),
        "waste_total":  float(waste_fresh + waste_pastry),
        "samples":      float(samples),
    }


def build_business_context(
    data: Dict[str, pd.DataFrame],
    financial_params: Dict[str, float],
    available_months: Optional[List[str]] = None,
) -> str:
    """
    Produce a structured markdown context block that summarises:
    - Recent revenue trends (7-day, 30-day, 3-month, 12-month)
    - Yesterday's order count (TC) and average check (AC)
    - Yesterday's waste and sample metrics
    - Membership recharge activity
    - Target achievement rate

    This block is prepended to every LLM system prompt.
    """
    if available_months is None:
        from modules.data_loader import get_available_months
        available_months = get_available_months()

    today     = datetime.now().date()
    yesterday = today - timedelta(days=1)
    month_start   = today.replace(day=1)
    last_30_start = today - timedelta(days=29)
    last_3m_start = (today.replace(day=1) - timedelta(days=90)).replace(day=1)

    parts = ["## Business Data Overview\n"]

    # ── Revenue from sales_detail ─────────────────────────────────────────────
    yesterday_revenue = 0.0
    df_detail = data.get("sales_detail", pd.DataFrame())

    if not df_detail.empty and "sale_date" in df_detail.columns and "amount" in df_detail.columns:
        yd = df_detail[df_detail["sale_date"].dt.date == yesterday]
        yesterday_revenue = yd["amount"].sum()

        monthly_rev = df_detail[
            df_detail["sale_date"].dt.date >= month_start
        ]["amount"].sum()

        # 30-day daily breakdown
        last30 = df_detail[df_detail["sale_date"].dt.date >= last_30_start]
        if not last30.empty:
            daily30 = last30.groupby(last30["sale_date"].dt.date)["amount"].sum().sort_index()
            trend_7d = ", ".join(
                f"{d.strftime('%m/%d')}: ${v:,.0f}" for d, v in daily30.tail(7).items()
            )
            avg30, max30, min30 = daily30.mean(), daily30.max(), daily30.min()
        else:
            trend_7d = "insufficient data"
            avg30 = max30 = min30 = 0

        # 3-month monthly summary
        last3m = df_detail[df_detail["sale_date"].dt.date >= last_3m_start]
        if not last3m.empty:
            mo3 = last3m.groupby(last3m["sale_date"].dt.to_period("M"))["amount"].sum().sort_index()
            text_3m = "; ".join(f"{p.strftime('%Y-%m')}: ${v:,.0f}" for p, v in mo3.items())
        else:
            text_3m = "insufficient data"
            mo3 = pd.Series(dtype=float)

        # All-time monthly summary
        all_mo = df_detail.groupby(
            df_detail["sale_date"].dt.to_period("M")
        )["amount"].sum().sort_index()
        text_all = "; ".join(f"{p.strftime('%Y-%m')}: ${v:,.0f}" for p, v in all_mo.items())
        last12 = all_mo.tail(12)

        parts.append(
            f"### Revenue (source: sales_detail)\n"
            f"- **Yesterday total**: ${yesterday_revenue:,.2f}\n"
            f"- **Month-to-date**: ${monthly_rev:,.2f}\n"
            f"- **Last 7 days**: {trend_7d}\n"
            f"- **Last 30 days**: {len(daily30) if not last30.empty else 0} days, "
            f"avg ${avg30:,.0f}, max ${max30:,.0f}, min ${min30:,.0f}\n"
            f"- **Last 3 months**: {text_3m}\n"
            f"- **Last 3 months total**: ${mo3.sum():,.0f}, avg/mo ${mo3.mean():,.0f}\n"
            f"- **Last 12 months total**: ${last12.sum():,.0f}, avg/mo ${last12.mean():,.0f}\n"
            f"- **All-time monthly**: {text_all}\n"
        )

        # Payment method breakdown (if columns present)
        pay_cols = {
            "digital_pay":  "Digital (mobile/QR)",
            "card_pay":     "Membership card",
            "cash":         "Cash",
            "platform_pay": "Platform pay",
        }
        present = {k: v for k, v in pay_cols.items() if k in yd.columns}
        if present:
            lines = [f"- {label}: ${yd[col].sum():,.2f}" for col, label in present.items()]
            parts.append("### Yesterday Payment Breakdown\n" + "\n".join(lines) + "\n")

    # ── TC / AC from sales ────────────────────────────────────────────────────
    df_sales = data.get("sales", pd.DataFrame())
    tc = 0
    if not df_sales.empty and "sale_time" in df_sales.columns:
        yd_sales = df_sales[df_sales["sale_time"].dt.date == yesterday]
        tc = yd_sales["order_id"].nunique() if "order_id" in yd_sales.columns else 0
        ac = yesterday_revenue / tc if tc > 0 else 0

        cat_text = "no data"
        if "category" in yd_sales.columns and not yd_sales.empty:
            cats = yd_sales.groupby("category")["amount"].sum().sort_values(ascending=False)
            cat_text = ", ".join(f"{c}: ${v:,.0f}" for c, v in cats.items())

        parts.append(
            f"### Yesterday Orders & Products (source: sales)\n"
            f"- **TC (transactions)**: {tc:,}\n"
            f"- **AC (avg check)**: ${ac:,.2f}\n"
            f"- **Category revenue**: {cat_text}\n"
        )

        # Top 5 products yesterday
        if "product" in yd_sales.columns and "qty" in yd_sales.columns and not yd_sales.empty:
            top5 = yd_sales.groupby("product")["qty"].sum().nlargest(5)
            top_text = ", ".join(f"{p}({q})" for p, q in top5.items())
            parts.append(f"- **Top 5 products**: {top_text}\n")

    # ── Waste ─────────────────────────────────────────────────────────────────
    df_waste = data.get("waste", pd.DataFrame())
    if not df_waste.empty:
        waste_info = _calc_waste(df_waste, yesterday)
        waste_rate   = waste_info["waste_total"]  / yesterday_revenue if yesterday_revenue > 0 else 0
        sample_rate  = waste_info["samples"] / yesterday_revenue if yesterday_revenue > 0 else 0

        parts.append(
            f"### Yesterday Waste (source: waste)\n"
            f"- **Total waste**: ${waste_info['waste_total']:,.2f} "
            f"(fresh: ${waste_info['waste_fresh']:,.2f}, pastry: ${waste_info['waste_pastry']:,.2f})\n"
            f"- **Waste rate**: {waste_rate:.2%}\n"
            f"- **Sample cost**: ${waste_info['samples']:,.2f} ({sample_rate:.2%})\n"
        )

    # ── Membership recharge ───────────────────────────────────────────────────
    df_mem = data.get("mem_detail", pd.DataFrame())
    if not df_mem.empty and "recharge_time" in df_mem.columns:
        yd_mem = df_mem[df_mem["recharge_time"].dt.date == yesterday]
        if not yd_mem.empty:
            count  = yd_mem["order_id"].nunique() if "order_id" in yd_mem.columns else len(yd_mem)
            amount = yd_mem["recharge_amt"].sum() if "recharge_amt" in yd_mem.columns else 0
            parts.append(
                f"### Yesterday Membership Recharge (source: mem_detail)\n"
                f"- Transactions: {count}\n"
                f"- Recharge amount: ${amount:,.2f}\n"
            )

    # ── Target achievement ────────────────────────────────────────────────────
    target = _get_day_targets(yesterday)
    rev_rate = yesterday_revenue / target["revenue"] if target["revenue"] > 0 else 0
    tc_rate  = tc / target["orders"] if target["orders"] > 0 else 0

    parts.append(
        f"### Yesterday Target Achievement\n"
        f"- Revenue target: ${target['revenue']:,} | actual: ${yesterday_revenue:,.0f} | rate: {rev_rate:.1%}\n"
        f"- Order target: {target['orders']} | actual: {tc} | rate: {tc_rate:.1%}\n"
    )

    # ── Financial parameters ──────────────────────────────────────────────────
    parts.append(
        f"### Financial Parameters\n"
        f"- Fixed daily cost: ${financial_params.get('fixed_cost', 0):,.2f}\n"
        f"- COGS ratio: {financial_params.get('cogs_ratio', 0):.1%}\n"
        f"- Operating cost ratio: {financial_params.get('op_cost_ratio', 0):.1%}\n"
    )

    if available_months:
        parts.append(f"\n### Data Coverage\n- Available months: {', '.join(available_months)}\n")

    return "\n".join(parts)


def build_system_prompt(business_context: str) -> str:
    """
    Combine the daily_report skill content with the live business context
    to produce the full system prompt sent to the LLM.
    """
    from modules.skill_loader import SkillRegistry
    registry = SkillRegistry()
    skill = registry.get_skill_prompt("daily_report") or ""

    return (
        f"{skill}\n\n"
        f"## Live Business Data\n\n{business_context}\n\n"
        "## Important Notes\n"
        "- You have access to ALL historical months listed in 'Data Coverage'.\n"
        "- For multi-month questions, use the monthly summaries provided.\n"
        "- Be honest about data gaps.\n"
        "- Prefer concise display using 'K' or 'M' suffixes for large numbers.\n"
    )

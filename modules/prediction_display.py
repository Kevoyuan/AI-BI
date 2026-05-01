"""
Prediction Display Module
Renders the multi-model forecast results in Streamlit.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go


def display_prediction_results(results: dict) -> None:
    """Render profit forecast charts and model performance metrics."""
    st.subheader("🔮 Net Profit Forecast (Next 7 Days)")

    future_dates = results.get("future_dates", [])
    if not future_dates:
        st.info("No forecast data available.")
        return

    date_strs = [d.strftime("%m-%d") for d in future_dates]

    # ── Forecast comparison chart ──────────────────────────────────────────
    fig = go.Figure()

    # Historical actuals
    df = results.get("df", pd.DataFrame())
    if not df.empty:
        fig.add_trace(go.Scatter(
            x=[d.strftime("%m-%d") for d in df["ds"].tolist()],
            y=df["y"].tolist(),
            name="Historical",
            line=dict(color="#64748b"),
        ))

    colours = {
        "ensemble_predictions": ("#3b82f6", "Ensemble"),
        "prophet_predictions":  ("#10b981", "Prophet"),
        "sarima_predictions":   ("#f59e0b", "SARIMA"),
        "xgb_predictions":      ("#ef4444", "XGBoost"),
    }
    for key, (colour, label) in colours.items():
        preds = results.get(key)
        if preds:
            fig.add_trace(go.Scatter(
                x=date_strs, y=preds,
                name=label,
                line=dict(color=colour, dash="dash" if key != "ensemble_predictions" else "solid"),
            ))

    fig.update_layout(
        title="Net Profit Forecast",
        xaxis_title="Date",
        yaxis_title="Net Profit ($)",
        template="plotly_dark",
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Ensemble table ─────────────────────────────────────────────────────
    ensemble = results.get("ensemble_predictions", [])
    if ensemble:
        fc_df = pd.DataFrame({
            "Date":          date_strs,
            "Forecast ($)":  [f"${v:,.2f}" for v in ensemble],
        })
        st.dataframe(fc_df, hide_index=True)

    # ── Model weights ──────────────────────────────────────────────────────
    weights = results.get("model_weights", {})
    if weights:
        st.caption(
            "Ensemble weights — "
            + " | ".join(f"{k.title()}: {v:.0%}" for k, v in weights.items() if v > 0)
        )

    # ── Accuracy metrics ───────────────────────────────────────────────────
    mae  = results.get("mae")
    rmse = results.get("rmse")
    mape = results.get("mape")
    if any(v is not None for v in [mae, rmse, mape]):
        with st.expander("📐 Model Accuracy (cross-validation)"):
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("MAE",  f"${mae:,.2f}" if mae is not None else "N/A")
            with c2: st.metric("RMSE", f"${rmse:,.2f}" if rmse is not None else "N/A")
            with c3: st.metric("MAPE", f"{mape:.1%}" if mape is not None else "N/A")

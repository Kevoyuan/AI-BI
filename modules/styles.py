"""
Styles Module
Injects custom CSS into the Streamlit app for a polished look.
"""
import streamlit as st


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        /* ── Global ───────────────────────────────── */
        [data-testid="stAppViewContainer"] {
            background: #0f172a;
            color: #e2e8f0;
        }
        [data-testid="stSidebar"] {
            background: #1e293b;
        }

        /* ── Metric cards ─────────────────────────── */
        [data-testid="metric-container"] {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px 16px;
        }

        /* ── Chat messages ────────────────────────── */
        [data-testid="chat-message-container"] {
            border-radius: 8px;
            padding: 8px;
        }

        /* ── Headings ─────────────────────────────── */
        h1, h2, h3 { color: #f1f5f9; }
        </style>
        """,
        unsafe_allow_html=True,
    )

"""
AI Q&A Page

This page coordinates Streamlit UI, session/data loading, and rendering.
The chat workflow is delegated to application.chat_service, while agent
logic remains in reusable router and data-analysis modules.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, Any

from application.chat_service import ChatRequest, ChatService
from modules.config import Config
from modules.skill_loader import SkillRegistry
from modules.context_builder import build_business_context
from modules.data_loader import get_available_months
from modules.session_manager import (
    list_sessions, load_session, save_session,
    delete_session, new_session_id, auto_session_name,
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="AI Analytics Assistant", page_icon="🤖", layout="wide")

from modules.styles import inject_custom_css
inject_custom_css()


# ── Data loaders (deterministic) ──────────────────────────────────────────────

def load_all_data() -> Dict[str, pd.DataFrame]:
    """Load and concatenate all tables across available months."""
    from modules.data_loader import (
        load_sales_for_month, load_sales_detail_for_month,
        load_waste_for_month, load_memberships_for_month,
        load_generic_for_month,
    )

    months = get_available_months()
    collectors: Dict[str, list] = {k: [] for k in
        ["sales", "sales_detail", "waste", "memberships", "mem_detail", "weather"]}

    loaders = {
        "sales":        load_sales_for_month,
        "sales_detail": load_sales_detail_for_month,
        "waste":        load_waste_for_month,
        "memberships":  load_memberships_for_month,
        "mem_detail":   load_memberships_for_month,
        "weather":      lambda m: load_generic_for_month("weather", m),
    }

    for month in months:
        for key, fn in loaders.items():
            try:
                df = fn(month)
                if not df.empty:
                    collectors[key].append(df)
            except Exception:
                pass

    return {
        key: pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        for key, frames in collectors.items()
    }


def load_financial_params() -> Dict[str, float]:
    try:
        from modules.database import load_financial_data
        df = load_financial_data()
        if not df.empty:
            return {
                "fixed_cost":    float(df["fixed_cost"].iloc[-1]    if "fixed_cost"    in df else 0),
                "cogs_ratio":    float(df["cogs_ratio"].iloc[0]     if "cogs_ratio"    in df else 0.35),
                "op_cost_ratio": float(df["op_cost_ratio"].iloc[0]  if "op_cost_ratio" in df else 0.12),
            }
    except Exception:
        pass
    return {"fixed_cost": 0.0, "cogs_ratio": 0.35, "op_cost_ratio": 0.12}


# ── Session helpers ───────────────────────────────────────────────────────────

def _new_session():
    sid = new_session_id()
    st.session_state.session_id   = sid
    st.session_state.session_name = auto_session_name([])
    st.session_state.messages     = []
    st.session_state.data_loaded  = False
    save_session(sid, st.session_state.session_name, [])


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.header("💬 Sessions")

        sessions   = list_sessions()
        id_to_name = {s["id"]: s["name"] for s in sessions}
        all_ids    = list(id_to_name.keys())
        current_id = st.session_state.get("session_id", "")

        selected = st.selectbox(
            "Select session",
            options=all_ids + ["__new__"],
            format_func=lambda x: id_to_name.get(x, "+ New Session"),
            index=all_ids.index(current_id) if current_id in all_ids else len(all_ids),
            key="session_selector",
        )

        if selected == "__new__":
            _new_session()
            st.rerun()
        elif selected != current_id:
            data = load_session(selected)
            st.session_state.update({
                "session_id":   selected,
                "session_name": data["name"],
                "messages":     data["messages"],
            })
            st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑️ Delete", use_container_width=True):
                delete_session(st.session_state.get("session_id", ""))
                _new_session()
                st.rerun()
        with c2:
            if st.button("🆕 New", use_container_width=True):
                _new_session()
                st.rerun()

        st.divider()

        # ── System status ─────────────────────────────────────────────────
        st.header("⚙️ System")
        import os
        provider  = os.getenv("LLM_PROVIDER", "deepseek")
        api_ready = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("GEMINI_API_KEY"))

        if api_ready:
            model_var = "DEEPSEEK_MODEL" if provider == "deepseek" else "GEMINI_MODEL"
            model = os.getenv(model_var, Config.MODEL_NAME)
            st.success(f"✅ {provider.upper()}: {model}")
        else:
            st.error("❌ LLM API key not configured")
            st.info("Set DEEPSEEK_API_KEY or GEMINI_API_KEY in .env")
            st.stop()

        st.divider()

        # ── Data loading ──────────────────────────────────────────────────
        if st.button("🔄 Refresh Data", use_container_width=True) or not st.session_state.data_loaded:
            with st.spinner("Loading data…"):
                st.session_state.all_data = load_all_data()
                params = load_financial_params()
                st.session_state.business_context = build_business_context(
                    st.session_state.all_data, params
                )
                st.session_state.data_loaded = True
            st.success("Data loaded!")

        months = get_available_months()
        st.subheader("📊 Data Overview")
        if months:
            st.info(f"{len(months)} month(s) loaded")
            st.caption(f"{min(months)} → {max(months)}")

        for tbl, df in st.session_state.all_data.items():
            if not df.empty:
                st.caption(f"• {tbl}: {len(df):,} rows")

        st.divider()

        # ── Skill registry ────────────────────────────────────────────────
        st.subheader("🧠 Active Skills")
        registry = SkillRegistry()
        for name in registry.list_skills():
            skill = registry.get(name)
            st.caption(f"• **{name}** ({skill.skill_type}): {skill.description[:50]}…")

        st.divider()
        _render_quick_questions()
        st.divider()

        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            sid = st.session_state.get("session_id")
            if sid:
                save_session(sid, st.session_state.get("session_name", ""), [])
            st.rerun()


def _render_quick_questions():
    st.subheader("🎯 Quick Questions")
    categories = {
        "📊 Daily Ops": [
            "How did yesterday perform?",
            "Did we hit yesterday's targets?",
            "What is the current waste rate?",
        ],
        "📈 Sales": [
            "Show the 7-day sales trend.",
            "Which category sells best?",
            "What are the top products?",
        ],
        "💰 Profit": [
            "What was yesterday's gross profit?",
            "What is the sample cost percentage?",
        ],
        "🔬 Deep Analysis": [
            "Compare revenue on rainy vs sunny days.",
            "Find the 5 products with highest waste rate.",
            "Plot last month's sales trend.",
        ],
    }

    for cat, questions in categories.items():
        with st.expander(cat, expanded=(cat == "📊 Daily Ops")):
            for q in questions:
                if st.button(q, use_container_width=True, key=f"quick_{hash(q)}"):
                    st.session_state.messages.append({"role": "user", "content": q})
                    st.rerun()


# ── Core loop: Resolve → Execute → Render ─────────────────────────────────────

def handle_message(prompt: str):
    """
    Core Resolve → Execute → Render loop:
      1. Resolve: RouterAgent picks the best Skill.
      2. Execute: Run the skill (text chat or code generation).
      3. Render:  Display the result.
    """
    request = ChatRequest(
        prompt=prompt,
        business_context=st.session_state.business_context,
        history=st.session_state.messages,
        dataframes=st.session_state.all_data,
    )
    response = ChatService().handle_message(request)

    with st.chat_message("assistant"):
        with st.status("🤖 Analysing…", expanded=True) as status:

            st.write("🛣️ Routing to best skill…")
            st.markdown(
                f"**Skill**: `{response.skill}` (type=`{response.skill_type}`) | "
                f"{response.reason}"
            )

            answer = response.answer
            code = response.code

            if response.skill_type == "code":
                st.write("💻 Generating analysis code…")
                for log in response.execution_log:
                    st.caption(f"📋 {log}")
                if code:
                    with st.expander("📝 Generated code"):
                        st.code(code, language="python")
                if response.error:
                    st.error(f"Execution error: {response.error}")
                    status.update(label="❌ Error", state="error")
                else:
                    status.update(label="✅ Done", state="complete", expanded=False)
            else:
                st.write("📖 Fetching business context…")
                try:
                    answer = st.write_stream(response.answer_stream)
                    status.update(label="✅ Done", state="complete", expanded=False)
                except Exception as exc:
                    st.error(f"Chat error: {exc}")
                    status.update(label="❌ Error", state="error")
                    answer = f"Sorry: {exc}"

        # Step 3 — Render
        if answer and response.skill_type == "code":
            st.markdown(answer)

        if response.chart is not None:
            st.plotly_chart(response.chart, use_container_width=True,
                            key=f"chart_{int(datetime.now().timestamp()*1000)}")

        if isinstance(response.result_data, pd.DataFrame):
            with st.expander("📊 Result data"):
                st.dataframe(response.result_data, use_container_width=True)

        # Persist to session
        msg = {"role": "assistant", "content": answer, "skill": response.skill}
        if code:
            msg["code"] = code
        st.session_state.messages.append(msg)

        sid = st.session_state.get("session_id")
        if sid:
            name = st.session_state.get("session_name", "Untitled")
            if name in ("New Session", "Untitled"):
                name = auto_session_name(st.session_state.messages)
                st.session_state.session_name = name
            save_session(sid, name, st.session_state.messages)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("🤖 AI Analytics Assistant")
    st.markdown("### 💬 Skill-routed AI Analytics Assistant")

    # Initialise session state
    if "session_id" not in st.session_state:
        sessions = list_sessions()
        if sessions:
            data = load_session(sessions[0]["id"])
            st.session_state.update({
                "session_id":   sessions[0]["id"],
                "session_name": data["name"],
                "messages":     data["messages"],
            })
        else:
            _new_session()

    st.session_state.setdefault("data_loaded",        False)
    st.session_state.setdefault("business_context",   "")
    st.session_state.setdefault("all_data",           {})

    render_sidebar()

    # Render conversation history
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg.get("content") or "")
            if msg.get("code"):
                with st.expander("📝 Code", expanded=False):
                    st.code(msg["code"], language="python")

    # Handle new user input
    if prompt := st.chat_input("Ask a question about your business data…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        handle_message(prompt)

    # Handle quick-question re-runs
    elif (
        st.session_state.messages
        and st.session_state.messages[-1]["role"] == "user"
        and (len(st.session_state.messages) < 2
             or st.session_state.messages[-2].get("role") != "assistant")
    ):
        handle_message(st.session_state.messages[-1]["content"])


if __name__ == "__main__":
    main()

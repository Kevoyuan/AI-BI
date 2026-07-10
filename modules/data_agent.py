"""
Data Analysis Agent — Code Generation + Execution

Generates Python analysis code via an LLM, executes it in a controlled
execution namespace, and summarises the result in natural language.

The namespace is not an operating-system sandbox or a security boundary;
generated code runs in the application's Python process.

Key features:
- Skill-specific system prompts (routes to the appropriate SKILL.md)
- Schema caching (avoids redundant df.info() calls)
- Automatic retry with error context on first failure
"""
import io
import logging
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, Any, Optional

from modules.skill_loader import SkillRegistry
from modules.llm_provider import get_provider

logger = logging.getLogger(__name__)


class DataAnalysisAgent:
    """
    Generates and executes Python data analysis code.

    Architecture:
        1. Build a schema description of available DataFrames.
        2. Ask the LLM to write analysis code using the appropriate Skill prompt.
        3. Execute the code in a controlled namespace.
        4. On failure, retry once with the error message as additional context.
        5. Summarise the result in natural language.
    """

    MAX_RETRIES = 1

    def __init__(self):
        self._registry = SkillRegistry()
        self._schema_cache: Dict[str, str] = {}

    def run(
        self,
        query: str,
        dataframes: Dict[str, pd.DataFrame],
        history: list = None,
        skill_name: str = "deep_analysis",
        required_tables: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Entry point: generate, execute, and narrate analysis code.

        Args:
            query:           The user's analytical question.
            dataframes:      All available DataFrames keyed by table name.
            history:         Conversation history for context-aware generation.
            skill_name:      Skill to load as system-prompt context.
            required_tables: Restrict schema to these tables (None = all).

        Returns:
            dict with keys: answer, code, result, fig, error,
                            retry_count, execution_log
        """
        df_schema = self._build_schema(dataframes, required_tables)

        result: Dict[str, Any] = {
            "answer":        "",
            "code":          "",
            "result":        None,
            "fig":           None,
            "error":         None,
            "retry_count":   0,
            "execution_log": [],
        }

        provider = get_provider()
        error_ctx: Optional[dict] = None
        exec_result: dict = {}

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                code = self._generate_code(
                    provider, query, df_schema, history,
                    skill_name=skill_name, error_ctx=error_ctx,
                )
                result["code"] = code
                result["execution_log"].append(f"Code generated (attempt {attempt + 1})")

                exec_result = self._execute_code(code, dataframes)
                result["result"] = exec_result.get("result")
                result["fig"]    = exec_result.get("fig")
                result["execution_log"].append("Execution succeeded")
                result["retry_count"] = attempt
                error_ctx = None
                break

            except Exception as exc:
                msg = str(exc)
                result["execution_log"].append(f"Execution failed (attempt {attempt + 1}): {msg}")
                result["retry_count"] = attempt

                if attempt < self.MAX_RETRIES:
                    error_ctx = {"code": result["code"], "error": msg}
                    result["execution_log"].append("Retrying with error context…")
                else:
                    result["error"] = msg

        if error_ctx is None:
            result["answer"] = self._summarise(provider, query, result["code"], exec_result)
        else:
            result["answer"] = (
                "Sorry, the analysis could not complete after "
                f"{self.MAX_RETRIES + 1} attempt(s).\n\n"
                f"**Error**: {error_ctx['error']}\n\n"
                "Please rephrase your question or try a different approach."
            )

        return result

    # ── Schema builder ────────────────────────────────────────────────────────

    def _build_schema(
        self,
        dataframes: Dict[str, pd.DataFrame],
        required_tables: Optional[list],
    ) -> str:
        """Produce a compact schema description with sample rows."""
        tables = required_tables if required_tables else list(dataframes.keys())
        parts = ["## Available DataFrames\n"]

        for name in tables:
            df = dataframes.get(name, pd.DataFrame())
            if df.empty:
                continue

            # Cache key based on shape + dtypes (invalidates on data reload)
            cache_key = f"{name}:{len(df)}:{','.join(df.columns)}:{hash(str(df.dtypes.to_dict()))}"
            if cache_key in self._schema_cache:
                parts.append(self._schema_cache[cache_key])
                continue

            buf = io.StringIO()
            df.info(buf=buf, verbose=True, memory_usage=False)
            col_lines = [
                l for l in buf.getvalue().split("\n")
                if any(t in l for t in ["int", "float", "object", "datetime", "bool"])
            ]

            entry = "\n".join([
                f"### `dfs['{name}']` — {len(df):,} rows",
                "**Columns & types:**",
                "\n".join(col_lines[:20]),
                f"\n**First 3 rows:**\n```\n{df.head(3).to_string()}\n```\n",
            ])

            self._schema_cache[cache_key] = entry
            parts.append(entry)

        return "\n".join(parts)

    # ── Code generation ───────────────────────────────────────────────────────

    def _generate_code(
        self,
        provider,
        query: str,
        schema: str,
        history: Optional[list],
        skill_name: str,
        error_ctx: Optional[dict],
    ) -> str:
        """Ask the LLM to write Python analysis code."""
        skill_content = (
            self._registry.get_skill_prompt(skill_name)
            or self._registry.get_skill_prompt("deep_analysis")
            or ""
        )

        # Conversation context
        history_text = ""
        if history and len(history) > 1:
            history_text = "## Conversation context\n"
            for msg in history[-6:][:-1]:
                role = "User" if msg["role"] == "user" else "AI"
                history_text += f"- {role}: {msg.get('content', '')[:200]}\n"
            history_text += "\nIf the current question is a follow-up, infer intent from context.\n"

        # Error retry context
        error_text = ""
        if error_ctx:
            error_text = (
                "\n## ⚠️ Previous attempt failed\n\n"
                f"**Code:**\n```python\n{error_ctx['code']}\n```\n\n"
                f"**Error:** {error_ctx['error']}\n\n"
                "Please fix the error. Common causes:\n"
                "- Column name mismatch → check the schema\n"
                "- Date type issue → use pd.to_datetime()\n"
                "- Empty DataFrame → add `.empty` guard\n"
                "- Division by zero → add conditional check\n"
            )

        system_prompt = f"{skill_content}\n\n## Available data\n\n{schema}"
        user_prompt = (
            f"{history_text}{error_text}"
            f"Write Python code to answer this question:\n\n**{query}**\n\n"
            "Output ONLY the code. No explanation."
        )

        code = provider.generate(system_prompt, user_prompt)

        # Strip markdown fences
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1]) if len(lines) > 2 else code
        code = code.replace("```python", "").replace("```", "").strip()

        return code

    # ── Code execution ────────────────────────────────────────────────────────

    @staticmethod
    def _execute_code(
        code: str,
        dataframes: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """
        Execute generated code in a controlled execution namespace.
        The code may set `result` (scalar or DataFrame) and/or `fig` (Plotly figure).
        This is not an operating-system sandbox or a security boundary.
        """
        namespace = {
            "dfs":      dataframes,
            "pd":       pd,
            "np":       np,
            "px":       px,
            "go":       go,
            "datetime": __import__("datetime"),
            "timedelta": __import__("datetime").timedelta,
            "result":   None,
            "fig":      None,
        }
        exec(code, namespace)  # noqa: S102
        return {"result": namespace.get("result"), "fig": namespace.get("fig")}

    # ── Answer generation ─────────────────────────────────────────────────────

    @staticmethod
    def _summarise(provider, query: str, code: str, exec_result: dict) -> str:
        """Generate a concise natural-language summary of the analysis result."""
        value = exec_result.get("result")

        if isinstance(value, pd.DataFrame):
            result_str = f"DataFrame ({len(value)} rows):\n{value.to_string()}"
        elif isinstance(value, float):
            result_str = f"{value:,.2f}"
        elif isinstance(value, int):
            result_str = f"{value:,}"
        else:
            result_str = str(value)

        system = (
            "You are a business analyst. Summarise data analysis results clearly and concisely.\n"
            "Rules: highlight key numbers; keep it to 1–3 sentences; mention the chart if one was generated."
        )
        user = (
            f"User question: {query}\n\n"
            f"Analysis result: {result_str}\n\n"
            "Summarise the result in plain English."
        )

        try:
            return provider.generate(system, user)
        except Exception:
            return f"Analysis result: {result_str}"

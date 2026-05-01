"""
Router Agent — Skill-based intent resolver.

Reads skill metadata from the skills/ registry and uses an LLM to
dynamically route user queries to the most appropriate skill.
This eliminates hard-coded if/else routing logic: the routing table
IS the skill descriptions.
"""
import json
import logging
from typing import Dict, Any, List

from modules.skill_loader import SkillRegistry
from modules.llm_provider import get_provider

logger = logging.getLogger(__name__)

_VALID_TABLES = {
    "sales", "sales_detail", "waste",
    "memberships", "mem_detail",
    "weather", "financial", "opening_cost",
}


class RouterAgent:
    """
    Skill-based resolver: reads all skill descriptions from skills/,
    then asks an LLM to pick the best match for a given user query.

    Design principle: routing rules live in the skill definitions, not here.
    Adding a new skill automatically makes it available for routing.
    """

    def __init__(self):
        self.registry = SkillRegistry()

    def resolve(self, query: str, context_summary: str = "",
                history: list = None) -> Dict[str, Any]:
        """
        Route a user query to the most appropriate skill.

        Args:
            query:           The user's question.
            context_summary: Brief business context summary.
            history:         Conversation history [{role, content}, …].

        Returns:
            dict with keys: skill, skill_type, reason, required_tables
        """
        skills = self.registry._skills
        if not skills:
            return self._fallback("No skills registered.")

        skill_names = list(skills.keys())

        # Build routing table from skill metadata (dynamic, no hard-coding)
        entries = "\n".join(
            f"- **{name}** (type={s.skill_type}): {s.description}"
            for name, s in skills.items()
        )

        system_prompt = f"""You are an intent classifier. Route the user's question to the best skill.

## Available Skills
{entries}

## Routing Rules
1. Read each skill's description and pick the closest match.
2. `type=text` skills answer questions using pre-computed metrics.
3. `type=code` skills write and execute Python analysis code.
4. Prefer more specific skills over generic ones.
5. Default to `daily_report` when uncertain.

## Output Format
Return a JSON object (no markdown):
{{
  "skill": "<skill_name>",
  "reason": "<one-line explanation>",
  "required_tables": ["table1", "table2"] or null
}}
- `skill` must be one of {json.dumps(skill_names)}
- `required_tables`: tables needed to answer (null if not sure)
"""

        history_text = ""
        if history and len(history) > 1:
            history_text = "## Recent conversation\n"
            for msg in history[-6:][:-1]:
                role = "User" if msg["role"] == "user" else "AI"
                history_text += f"- {role}: {msg.get('content', '')[:200]}\n"

        user_prompt = (
            f'User question: "{query}"\n\n'
            f'{history_text}\n'
            f'Context summary:\n{context_summary[:800]}\n\n'
            f'Classify:'
        )

        try:
            provider = get_provider()
            raw = provider.generate(system_prompt, user_prompt, json_mode=True)
            result = json.loads(raw)

            skill_name = result.get("skill", "daily_report")
            if skill_name not in skill_names:
                skill_name = "daily_report"
                result["reason"] = result.get("reason", "") + " (fell back to default)"

            skill = skills.get(skill_name)

            required_tables = result.get("required_tables")
            if required_tables and isinstance(required_tables, list):
                required_tables = [t for t in required_tables if t in _VALID_TABLES]
            else:
                required_tables = None

            return {
                "skill":           skill_name,
                "skill_type":      skill.skill_type if skill else "text",
                "reason":          result.get("reason", ""),
                "required_tables": required_tables,
            }

        except Exception as exc:
            logger.warning("Routing failed: %s", exc)
            return self._fallback(str(exc))

    # ── Backwards-compatible helper ───────────────────────────────────────────

    def classify_intent(self, query: str, context_summary: str = "") -> Dict[str, Any]:
        """Thin wrapper for backwards compatibility. Delegates to resolve()."""
        result = self.resolve(query, context_summary)
        intent_map = {
            "daily_report":  "STANDARD_CHAT",
            "deep_analysis": "DATA_ANALYSIS",
            "visualization": "VISUALIZATION",
            "forecast":      "DATA_ANALYSIS",
            "profit_cost":   "DATA_ANALYSIS",
        }
        return {
            "intent": intent_map.get(result["skill"], "STANDARD_CHAT"),
            "skill":  result["skill"],
            "reason": result["reason"],
        }

    @staticmethod
    def _fallback(reason: str) -> Dict[str, Any]:
        return {
            "skill":           "daily_report",
            "skill_type":      "text",
            "reason":          f"Routing failed, using default: {reason}",
            "required_tables": None,
        }

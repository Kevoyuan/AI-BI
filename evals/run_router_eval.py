"""Evaluate RouterAgent decisions against a labelled local case set.

Mock mode checks the harness wiring only: the mock returns each case's label.
Live mode calls the configured LLM provider and is the only mode that measures
real router behavior.
"""
import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

import yaml

from modules.router_agent import RouterAgent

CASES_PATH = Path(__file__).with_name("router_cases.yaml")


def load_cases(path: Path = CASES_PATH) -> List[dict]:
    with path.open(encoding="utf-8") as handle:
        cases = yaml.safe_load(handle) or []
    if not isinstance(cases, list):
        raise ValueError("Router cases must be a YAML list.")
    required = {"query", "expected_skill"}
    if any(not required.issubset(case) for case in cases):
        raise ValueError("Every router case needs query and expected_skill.")
    return cases


def compute_report(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    correct = sum(row["expected"] == row["predicted"] for row in rows)
    per_skill = defaultdict(lambda: {"correct": 0, "total": 0})
    confusion = Counter()
    for row in rows:
        expected = row["expected"]
        predicted = row["predicted"]
        per_skill[expected]["total"] += 1
        per_skill[expected]["correct"] += expected == predicted
        confusion[(expected, predicted)] += 1
    return {
        "total": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows) if rows else 0.0,
        "per_skill": dict(per_skill),
        "confusion": dict(confusion),
        "failures": [row for row in rows if row["expected"] != row["predicted"]],
    }


class _MockRouterProvider:
    def __init__(self, labels: Dict[str, str]):
        self.labels = labels

    def generate(self, system_prompt, user_prompt, json_mode=False):
        query = user_prompt.split('User question: "', 1)[1].split('"', 1)[0]
        return json.dumps({
            "skill": self.labels[query],
            "reason": "mock label lookup; not a quality measurement",
        })


def _check_live_credentials() -> bool:
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    key = os.getenv("GEMINI_API_KEY" if provider == "gemini" else "DEEPSEEK_API_KEY")
    if not key:
        print(f"Live router evaluation unavailable: missing credentials for {provider}.")
        print("Set the provider API key or run with --mode mock.")
        return False
    return True


def run(mode: str, cases: List[dict]) -> dict:
    if mode == "live" and not _check_live_credentials():
        return {}

    rows = []
    if mode == "mock":
        labels = {case["query"]: case["expected_skill"] for case in cases}
        from unittest.mock import patch
        provider = _MockRouterProvider(labels)
        provider_context = patch("modules.router_agent.get_provider", return_value=provider)
    else:
        from contextlib import nullcontext
        provider_context = nullcontext()

    with provider_context:
        router = RouterAgent()
        for case in cases:
            result = router.resolve(case["query"])
            rows.append({
                "query": case["query"],
                "expected": case["expected_skill"],
                "predicted": result["skill"],
            })
    return compute_report(rows)


def print_report(report: dict, mode: str) -> None:
    print(f"Router evaluation ({mode} mode)")
    print(f"Total cases: {report['total']}")
    print(f"Correct: {report['correct']}")
    print(f"Accuracy: {report['accuracy']:.1%}")
    print("Per-skill accuracy:")
    for skill, values in sorted(report["per_skill"].items()):
        accuracy = values["correct"] / values["total"] if values["total"] else 0
        print(f"  {skill}: {values['correct']}/{values['total']} ({accuracy:.1%})")
    print("Confusion summary:")
    for (expected, predicted), count in sorted(report["confusion"].items()):
        print(f"  expected={expected}, predicted={predicted}: {count}")
    if report["failures"]:
        print("Failed cases:")
        for row in report["failures"]:
            print(f"  - {row['query']} (expected {row['expected']}, got {row['predicted']})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    args = parser.parse_args()
    cases = load_cases()
    report = run(args.mode, cases)
    if not report:
        return 2
    print_report(report, args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

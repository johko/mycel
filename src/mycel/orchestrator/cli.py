"""
Orchestrator CLI.

    mycel-ask "<question for the federation>"

Reads the node registry (``--registry``, default ``registry.yaml`` in the
current directory), then streams the graph's progress: the plan, each node's
policy decision, and the synthesized answer.
"""

import argparse
import asyncio

from dotenv import load_dotenv

from mycel.orchestrator.graph import build_graph
from mycel.orchestrator.planner import DEFAULT_MODEL
from mycel.orchestrator.registry import load_registry
from mycel.orchestrator.strategies import (
    DEFAULT_STRATEGY,
    STRATEGY_REGISTRY,
    make_strategy,
)

_RULE = "─" * 72


def _print_plan(plan) -> None:
    print(f"\n{_RULE}\nPLAN\n{_RULE}")
    for i, call in enumerate(plan, 1):
        print(f"{i}. {call.node_id}: {call.query}")
        if call.rationale:
            print(f"   rationale: {call.rationale}")


def _print_results(results) -> None:
    print(f"\n{_RULE}\nNODE RESPONSES\n{_RULE}")
    for result in results:
        call = result["call"]
        print(f"\n[{call.node_id}]")
        if result["error"] is not None:
            print(f"  ERROR: {result['error']}")
            continue
        response = result["response"]
        decision = response.policy_decision
        status = "ALLOWED" if decision.allowed else "BLOCKED"
        print(f"  policy: {status}")
        if decision.reason:
            print(f"  reason: {decision.reason}")
        for redaction in decision.redactions:
            print(f"  redacted: {redaction.record}.{redaction.field}")
        for violation in decision.violations:
            print(f"  violation: {violation.record}.{violation.field}")
        for obligation in decision.obligations:
            print(f"  obligation: {obligation}")
        if response.answer:
            print(f"  answer: {response.answer}")


async def ask(question: str, registry_path: str, model: str, strategy: str) -> None:
    registry = load_registry(registry_path)
    graph = build_graph(registry, model, make_strategy(strategy, model))

    async for update in graph.astream({"question": question}, stream_mode="updates"):
        if "plan" in update:
            _print_plan(update["plan"]["plan"])
        elif "execute" in update:
            _print_results(update["execute"]["results"])
        elif "synthesize" in update:
            print(f"\n{_RULE}\nFINAL ANSWER\n{_RULE}")
            print(update["synthesize"]["final_answer"])


def main() -> None:
    load_dotenv()  # HF_TOKEN etc.; the same .env docker compose uses
    parser = argparse.ArgumentParser(description="Ask the node federation a question.")
    parser.add_argument("question")
    parser.add_argument("--registry", default="registry.yaml")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY,
        choices=sorted(STRATEGY_REGISTRY),
        help="aggregation strategy for combining node responses",
    )
    args = parser.parse_args()
    asyncio.run(ask(args.question, args.registry, args.model, args.strategy))

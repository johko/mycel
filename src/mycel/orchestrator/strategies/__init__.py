"""
Aggregation strategies — pluggable, Flower-style.

`STRATEGY_REGISTRY` maps a user-facing name to a strategy class; every
strategy is constructed with the synthesis model. Select one via the
`--strategy` CLI flag, the `strategy=` query param, or `MYCEL_STRATEGY`.
"""

from mycel.llm import DEFAULT_MODEL
from mycel.orchestrator.strategies.base import (
    AggregatedResult,
    AggregationStrategy,
)
from mycel.orchestrator.strategies.judgment import JudgmentAggregationStrategy
from mycel.orchestrator.strategies.llm_synthesis import LLMSynthesisStrategy
from mycel.orchestrator.strategies.majority_judgment import MajorityJudgmentStrategy

STRATEGY_REGISTRY: dict[str, type] = {
    LLMSynthesisStrategy.name: LLMSynthesisStrategy,
    JudgmentAggregationStrategy.name: JudgmentAggregationStrategy,
    MajorityJudgmentStrategy.name: MajorityJudgmentStrategy,
}

DEFAULT_STRATEGY = LLMSynthesisStrategy.name


def make_strategy(
    name: str = DEFAULT_STRATEGY, model: str = DEFAULT_MODEL
) -> AggregationStrategy:
    try:
        cls = STRATEGY_REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(STRATEGY_REGISTRY))
        raise ValueError(f"unknown strategy {name!r}; available: {known}") from None
    return cls(model)


__all__ = [
    "AggregatedResult",
    "AggregationStrategy",
    "LLMSynthesisStrategy",
    "JudgmentAggregationStrategy",
    "MajorityJudgmentStrategy",
    "STRATEGY_REGISTRY",
    "DEFAULT_STRATEGY",
    "make_strategy",
]

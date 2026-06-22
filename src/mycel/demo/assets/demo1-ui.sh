#!/usr/bin/env bash
# Demo 1 (intro) — the three original, non-overlapping departments, locked to
# LLM synthesis (the strategy selector is hidden). Shows the core federation:
# plan → per-node egress policy → synthesis.
#
# Run after `docker compose up` (all five containers may run; this registry
# simply never routes to Estates/Bursar). Dashboard → http://localhost:7860
set -uo pipefail
cd "$(dirname "$0")"

export REGISTRY_PATH=registry.basic.yaml
export MYCEL_STRATEGIES=llm
exec uv run mycel-ui

#!/usr/bin/env bash
# Demo 2 (full) — all five departments, including the two overlapping nodes
# (Estates & Bursar), with the aggregation-strategy selector exposed
# (llm | judgment | median). Shows data overlap + computational social choice.
#
# Run after `docker compose up`. Dashboard → http://localhost:7860
set -uo pipefail
cd "$(dirname "$0")"

export REGISTRY_PATH=registry.yaml
unset MYCEL_STRATEGIES          # expose all registered strategies
exec uv run mycel-ui

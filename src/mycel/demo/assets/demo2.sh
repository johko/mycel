#!/usr/bin/env bash
# Demo 2 (full) — CLI walk-through of data overlap + computational social choice.
# Adds the two overlapping departments (Estates & Bursar) and exercises the
# aggregation strategies. Run after `docker compose up`.
set -uo pipefail
cd "$(dirname "$0")"

REGISTRY=registry.yaml

# run "<query>" [extra mycel-ask args, e.g. --strategy median]
run() {
  local query="$1"; shift
  echo
  echo "════════════════════════════════════════════════════════════════════"
  echo "QUERY: $query ${*:+[$*]}"
  echo "════════════════════════════════════════════════════════════════════"
  uv run mycel-ask "$query" --registry "$REGISTRY" "$@" || echo ">>> query failed, continuing"
}

# 1. The same campus-consumption figure lives in three departments. Under the
# default `llm` strategy the synthesizer reconciles them in prose...
run "What was total campus energy consumption over 2020-2024, in kWh?"

# 2. ...and under `median` (Majority Judgment) it returns a robust central
# value with the min–max spread across the three estimates.
run "What was total campus energy consumption over 2020-2024, in kWh?" --strategy median

# 3. OVERLAP + JUDGMENT — Energy, Estates and Bursar all assert lab expansion
# drove the growth; the judgment strategy accepts it by per-issue majority vote.
run "Did research lab expansion drive the rise in campus energy consumption?" --strategy judgment

# 4. Staffing headcount overlaps (Archivists vs Bursar); median reconciles the
# two figures into a confidence-weighted central value.
run "How many research staff did MICE have on average in 2020-2024?" --strategy median

# 5. The headline cross-node query, now spanning all five departments.
run "What is the relationship between energy consumption patterns and research output at MICE over the last decade?"

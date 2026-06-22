#!/usr/bin/env bash
# Demo 1 (intro) — CLI walk-through of the core federation: the three original,
# non-overlapping departments, all answers synthesized with the default `llm`
# strategy. Shows the three egress policy modes (deny / redact / oblige) and a
# cross-node synthesis. Run after `docker compose up`.
set -uo pipefail
cd "$(dirname "$0")"

REGISTRY=registry.basic.yaml

# run "<query>" [extra mycel-ask args] — always against the 3-node registry
run() {
  local query="$1"; shift
  echo
  echo "════════════════════════════════════════════════════════════════════"
  echo "QUERY: $query ${*:+[$*]}"
  echo "════════════════════════════════════════════════════════════════════"
  # keep going if a single query fails — don't let one hiccup end the demo
  uv run mycel-ask "$query" --registry "$REGISTRY" "$@" || echo ">>> query failed, continuing"
}

# 1. DENY — Energy Wizards block raw values.
# Via the orchestrator the planner softens the query, so the agent may
# self-censor (also correct). Hitting the node directly with a blunt
# question reliably shows OPA blocking the response.
echo
echo "════════════════════════════════════════════════════════════════════"
echo "DIRECT NODE CALL: ask Energy Wizards for a raw value"
echo "════════════════════════════════════════════════════════════════════"
curl -s -X POST http://localhost:8001/invoke \
  -H 'Content-Type: application/json' \
  -d '{"query": "What was Tower A energy consumption in 2024? Give me the exact kWh number."}' \
  | python3 -m json.tool || echo ">>> query failed, continuing"

run "What exactly was Tower A's energy consumption in 2024, in kWh?"

# 2. REDACT — Archivists strip names and birth dates
run "Who is the head of the Alchemy Lab and when were they born?"

# 3. OBLIGE — Commons Scholars require attribution
run "How many papers did MICE publish between 2020 and 2024?"

# 4. Cross-node synthesis — planner fans out, synthesizer combines
run "What is the relationship between energy consumption patterns and research output at MICE over the last decade?"

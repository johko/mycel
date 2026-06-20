#!/usr/bin/env bash
# MICE demo — run after `docker compose up --build`.
# Shows all three policy modes, the cross-node synthesis query, and the
# overlap-driven computational-social-choice aggregation strategies.
set -uo pipefail
cd "$(dirname "$0")/.."

# run "<query>" [extra mycel-ask args, e.g. --strategy median]
run() {
  local query="$1"; shift
  echo
  echo "════════════════════════════════════════════════════════════════════"
  echo "QUERY: $query ${*:+[$*]}"
  echo "════════════════════════════════════════════════════════════════════"
  # keep going if a single query fails — don't let one hiccup end the demo
  uv run mycel-ask "$query" "$@" || echo ">>> query failed, continuing"
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

# 4. The headline cross-node query
run "What is the relationship between energy consumption patterns and research output at MICE over the last decade?"

# 5. OVERLAP — three departments carry a 2020-2024 consumption figure; the
# median strategy aggregates them into a robust central value with a spread.
run "What was total campus energy consumption over 2020-2024, in kWh?" --strategy median

# 6. OVERLAP — Energy, Estates and Bursar all assert lab expansion drove the
# growth; the judgment strategy accepts it by majority vote.
run "Did research lab expansion drive the rise in campus energy consumption?" --strategy judgment

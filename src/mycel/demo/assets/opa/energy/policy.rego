# Energy Wizards egress policy — DENY mode.
#
# No raw measurement values leave this node. If the outgoing answer contains
# any value from a high-sensitivity record's measurement fields, the whole
# response is blocked. Aggregate records (sensitivity "low") flow freely.
#
# Matching runs against a digit-normalized copy of the answer (commas,
# underscores, and whitespace stripped) so LLM number formatting like
# "42,317" or "42 317" cannot evade the check. Unit-converted or rounded
# values ("~42.3 MWh") are a known limitation of substring policies.
#
# Input: {"answer": <outgoing text>, "records": {<id>: <record the agent touched>}}

package diplomat

default allow := false

# Fields that may legitimately appear in prose even for sensitive records.
context_fields := {"sensitivity", "label", "site", "year"}

normalized_answer := regex.replace(input.answer, `[,_\s]`, "")

leaks contains {"record": id, "field": field} if {
	some id, rec in input.records
	rec.sensitivity == "high"
	some field, value in rec
	not field in context_fields
	contains(normalized_answer, sprintf("%v", [value]))
}

allow if count(leaks) == 0

violations := [leak | some leak in leaks]

answer := input.answer if allow

answer := "" if not allow

reason := "blocked: answer contains raw values from sensitive records; only aggregates may leave the Energy Wizards node" if not allow

reason := null if allow

result := {
	"allow": allow,
	"answer": answer,
	"violations": violations,
	"reason": reason,
}

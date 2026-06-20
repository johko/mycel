# Archivists egress policy — REDACT mode.
#
# Staffing history and institutional events may be shared, but personal
# names and dates of birth never leave the node. Any PII value from a
# touched record is replaced with [REDACTED] in the outgoing answer.
#
# Names are matched token-wise so partial mentions are caught. Dates of
# birth are expanded into the raw value, the year, and the spelled-out
# month name, so an LLM rewriting "1971-03-14" as "14 March 1971" cannot
# leak the identifying parts. Bare day/month numbers are not redacted
# (too collision-prone) — a residual "-03-14" fragment is a known
# limitation of substring redaction.
#
# Input: {"answer": <outgoing text>, "records": {<id>: <record the agent touched>}}

package diplomat

month_names := {
	"01": "January", "02": "February", "03": "March", "04": "April",
	"05": "May", "06": "June", "07": "July", "08": "August",
	"09": "September", "10": "October", "11": "November", "12": "December",
}

# Tokens worth redacting for a given PII field value.
pii_tokens(field, value) := tokens if {
	field == "name"
	tokens := {t | some t in split(value, " "); count(t) > 3}
}

pii_tokens(field, value) := tokens if {
	field == "date_of_birth"
	parts := split(value, "-")
	count(parts) == 3
	tokens := {value, parts[0], month_names[parts[1]]}
}

leaked contains {"record": id, "field": field, "token": token} if {
	some id, rec in input.records
	some field in {"name", "date_of_birth"}
	some token in pii_tokens(field, rec[field])
	contains(input.answer, token)
}

replacements := {leak.token: "[REDACTED]" | some leak in leaked}

safe_answer := strings.replace_n(replacements, input.answer)

redactions := [entry |
	some entry in {{"record": leak.record, "field": leak.field} | some leak in leaked}
]

result := {
	"allow": true,
	"answer": safe_answer,
	"redactions": redactions,
}

# Estates & Facilities egress policy — OBLIGE mode.
#
# Facilities data is open, but anything derived from it carries an
# attribution obligation listing the sources of every record the
# agent consulted. The orchestrator must honor obligations downstream.
#
# Input: {"answer": <outgoing text>, "records": {<id>: <record the agent touched>}}

package diplomat

sources contains src if {
	some _, rec in input.records
	src := rec.source
}

obligations := [msg] if {
	count(sources) > 0
	msg := sprintf("Attribution required. Cite: %s", [concat("; ", sort(sources))])
}

obligations := [] if count(sources) == 0

result := {
	"allow": true,
	"answer": input.answer,
	"obligations": obligations,
}

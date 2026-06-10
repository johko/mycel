package diplomat_test

import data.diplomat

paper_records := {
	"P-2022-FLUX": {
		"title": "Flux-Stabilized Mana Grids: A Field Study",
		"year": 2022,
		"source": "Journal of Applied Thaumaturgy 14(2)",
	},
	"PUB-STATS-2020-2024": {
		"papers_published": 118,
		"source": "MICE Commons Annual Reports 2020-2024",
	},
}

test_allow_with_attribution_obligation if {
	r := diplomat.result with input as {
		"answer": "118 papers were published 2020-2024.",
		"records": paper_records,
	}
	r.allow == true
	r.answer == "118 papers were published 2020-2024."
	count(r.obligations) == 1
	contains(r.obligations[0], "Journal of Applied Thaumaturgy 14(2)")
	contains(r.obligations[0], "MICE Commons Annual Reports 2020-2024")
}

test_no_obligation_without_records if {
	r := diplomat.result with input as {"answer": "Nothing consulted.", "records": {}}
	r.allow == true
	count(r.obligations) == 0
}

package diplomat_test

import data.diplomat

estates_records := {
	"EST-CONSUMPTION-2020-2024": {
		"total_kwh": 3050000,
		"source": "MICE Estates Meter Logs 2020-2024",
	},
	"EST-FLOORSPACE": {
		"research_floorspace_m2_2024": 14200,
		"source": "MICE Estates Space Register",
	},
}

test_allow_with_attribution_obligation if {
	r := diplomat.result with input as {
		"answer": "Metered consumption was 3,050,000 kWh over 2020-2024.",
		"records": estates_records,
	}
	r.allow == true
	count(r.obligations) == 1
	contains(r.obligations[0], "MICE Estates Meter Logs 2020-2024")
	contains(r.obligations[0], "MICE Estates Space Register")
}

test_no_obligation_without_records if {
	r := diplomat.result with input as {"answer": "Nothing consulted.", "records": {}}
	r.allow == true
	count(r.obligations) == 0
}

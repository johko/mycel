package diplomat_test

import data.diplomat

bursar_records := {
	"BUR-STAFF-2020-2024": {
		"avg_research_staff": 64,
		"source": "MICE Bursar Payroll Summary 2020-2024",
	},
	"BUR-ENERGY-SPEND-2020-2024": {
		"estimated_total_kwh": 3200000,
		"source": "MICE Bursar Energy Accounts 2020-2024",
	},
}

test_allow_with_attribution_obligation if {
	r := diplomat.result with input as {
		"answer": "Funded research staff averaged 64; estimated consumption 3,200,000 kWh.",
		"records": bursar_records,
	}
	r.allow == true
	count(r.obligations) == 1
	contains(r.obligations[0], "MICE Bursar Payroll Summary 2020-2024")
	contains(r.obligations[0], "MICE Bursar Energy Accounts 2020-2024")
}

test_no_obligation_without_records if {
	r := diplomat.result with input as {"answer": "Nothing consulted.", "records": {}}
	r.allow == true
	count(r.obligations) == 0
}

package diplomat_test

import data.diplomat

sensitive_record := {
	"E-TOWER-A-2024": {
		"label": "Tower A consumption 2024 (raw, sensitive)",
		"site": "Tower A",
		"year": 2024,
		"consumption_kwh": 42317,
		"peak_load_kw": 311,
		"sensitivity": "high",
	},
}

aggregate_record := {
	"AGG-2020-2024": {
		"label": "Campus aggregate 2020-2024",
		"period": "2020-2024",
		"avg_annual_kwh": 628000,
		"trend": "rising",
		"sensitivity": "low",
	},
}

test_deny_raw_value_leak if {
	r := diplomat.result with input as {
		"answer": "Tower A consumed 42317 kWh in 2024.",
		"records": sensitive_record,
	}
	r.allow == false
	r.answer == ""
	count(r.violations) == 1
}

test_allow_aggregate_values if {
	r := diplomat.result with input as {
		"answer": "Average annual consumption 2020-2024 was 628000 kWh, trend rising.",
		"records": aggregate_record,
	}
	r.allow == true
	r.answer != ""
	count(r.violations) == 0
}

test_deny_comma_formatted_leak if {
	# LLMs often format numbers with separators — must still be caught
	r := diplomat.result with input as {
		"answer": "Tower A consumed **42,317 kWh** in 2024.",
		"records": sensitive_record,
	}
	r.allow == false
	count(r.violations) == 1
}

test_deny_space_formatted_leak if {
	r := diplomat.result with input as {
		"answer": "Tower A: 42 317 kWh.",
		"records": sensitive_record,
	}
	r.allow == false
}

test_allow_sensitive_record_without_leak if {
	r := diplomat.result with input as {
		"answer": "Tower A data exists for 2024 but raw values cannot be shared.",
		"records": sensitive_record,
	}
	r.allow == true
}

test_allow_no_records if {
	r := diplomat.result with input as {"answer": "No data consulted.", "records": {}}
	r.allow == true
}

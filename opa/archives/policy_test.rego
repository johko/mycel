package diplomat_test

import data.diplomat

personnel_record := {
	"PERS-0042": {
		"label": "Personnel file: head of Alchemy Lab",
		"name": "Morgana Hexenmeister",
		"date_of_birth": "1971-03-14",
		"role": "Head of Alchemy Lab",
		"hired": 2009,
	},
}

test_redact_full_name if {
	r := diplomat.result with input as {
		"answer": "The lab is led by Morgana Hexenmeister since 2009.",
		"records": personnel_record,
	}
	r.allow == true
	r.answer == "The lab is led by [REDACTED] [REDACTED] since 2009."
	count(r.redactions) > 0
}

test_redact_partial_name if {
	r := diplomat.result with input as {
		"answer": "Ask Morgana about the expansion.",
		"records": personnel_record,
	}
	r.answer == "Ask [REDACTED] about the expansion."
}

test_redact_date_of_birth if {
	r := diplomat.result with input as {
		"answer": "Born 1971-03-14, she joined in 2009.",
		"records": personnel_record,
	}
	not contains(r.answer, "1971")
	contains(r.answer, "[REDACTED]")
}

test_redact_reformatted_date_of_birth if {
	# LLMs rewrite dates — "14 March 1971" must not leak year or month
	r := diplomat.result with input as {
		"answer": "She was born on 14 March 1971.",
		"records": personnel_record,
	}
	not contains(r.answer, "1971")
	not contains(r.answer, "March")
	count(r.redactions) > 0
}

test_redactions_deduplicated if {
	r := diplomat.result with input as {
		"answer": "Morgana Hexenmeister, born 14 March 1971.",
		"records": personnel_record,
	}
	count(r.redactions) == 2 # one entry per (record, field), not per token
}

test_clean_answer_untouched if {
	r := diplomat.result with input as {
		"answer": "Research staff nearly doubled after 2021.",
		"records": personnel_record,
	}
	r.allow == true
	r.answer == "Research staff nearly doubled after 2021."
	count(r.redactions) == 0
}

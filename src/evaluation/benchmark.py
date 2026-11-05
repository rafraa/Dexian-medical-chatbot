import json
from pathlib import Path
from typing import TypedDict


class Criterion(TypedDict):
	description: str
	match_any: list[str]


class CaseReference(TypedDict):
	source: str
	page: int
	jurisdiction: str


class EvaluationCase(TypedDict):
	id: str
	topic_area: str
	topic: str
	jurisdiction: str
	case: str
	question: str
	expected_diagnosis: str
	diagnosis_terms: list[str]
	diagnosis_criteria: list[Criterion]
	treatment_plan_criteria: list[Criterion]
	avoid_terms: list[str]
	references: list[CaseReference]
	reviewed: bool


def load_cases(path: Path) -> list[EvaluationCase]:
	"""Load and validate a benchmark JSON file."""
	try:
		data = json.loads(path.read_text(encoding="utf-8"))
	except json.JSONDecodeError as exc:
		raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
	if not isinstance(data, dict) or data.get("schema_version") != 1:
		raise ValueError("Benchmark file must have schema_version 1.")
	cases = data.get("cases")
	if not isinstance(cases, list) or not cases:
		raise ValueError("Benchmark file must contain at least one case.")
	seen_ids: set[str] = set()
	validated: list[EvaluationCase] = []
	for index, case in enumerate(cases, start=1):
		validated.append(_validate_case(case, index, seen_ids))
	return validated


def _validate_case(
	value: object,
	index: int,
	seen_ids: set[str],
) -> EvaluationCase:
	if not isinstance(value, dict):
		raise ValueError(f"Case {index} must be an object.")
	required_strings = (
		"id",
		"topic_area",
		"topic",
		"jurisdiction",
		"case",
		"question",
		"expected_diagnosis",
	)
	for key in required_strings:
		if not isinstance(value.get(key), str) or not value[key].strip():
			raise ValueError(f"Case {index} must have a non-empty {key}.")
	case_id = value["id"]
	if case_id in seen_ids:
		raise ValueError(f"Duplicate case id: {case_id}")
	seen_ids.add(case_id)
	if value["jurisdiction"] not in {"EG", "EU", "US", "UNSPECIFIED"}:
		raise ValueError(f"Case {case_id} has an invalid jurisdiction.")
	diagnosis_terms = _string_list(value.get("diagnosis_terms"), case_id, "diagnosis_terms")
	if not diagnosis_terms:
		raise ValueError(f"Case {case_id} needs at least one diagnosis term.")
	diagnosis_criteria = _criteria_list(
		value.get("diagnosis_criteria"), case_id, "diagnosis_criteria"
	)
	treatment_criteria = _criteria_list(
		value.get("treatment_plan_criteria"), case_id, "treatment_plan_criteria"
	)
	if not diagnosis_criteria or not treatment_criteria:
		raise ValueError(
			f"Case {case_id} needs diagnosis and treatment-plan criteria."
		)
	avoid_terms = _string_list(value.get("avoid_terms", []), case_id, "avoid_terms")
	references_value = value.get("references")
	if not isinstance(references_value, list) or not references_value:
		raise ValueError(f"Case {case_id} needs at least one guideline reference.")
	references: list[CaseReference] = []
	for reference in references_value:
		if not isinstance(reference, dict):
			raise ValueError(f"Case {case_id} has an invalid reference.")
		source = reference.get("source")
		page = reference.get("page")
		jurisdiction = reference.get("jurisdiction")
		if (
			not isinstance(source, str)
			or not source.strip()
			or type(page) is not int
			or not isinstance(jurisdiction, str)
			or not jurisdiction.strip()
		):
			raise ValueError(f"Case {case_id} has incomplete reference metadata.")
		references.append(
			{"source": source, "page": page, "jurisdiction": jurisdiction}
		)
	reviewed = value.get("reviewed", False)
	if not isinstance(reviewed, bool):
		raise ValueError(f"Case {case_id} reviewed must be true or false.")
	return {
		"id": case_id,
		"topic_area": value["topic_area"],
		"topic": value["topic"],
		"jurisdiction": value["jurisdiction"],
		"case": value["case"],
		"question": value["question"],
		"expected_diagnosis": value["expected_diagnosis"],
		"diagnosis_terms": diagnosis_terms,
		"diagnosis_criteria": diagnosis_criteria,
		"treatment_plan_criteria": treatment_criteria,
		"avoid_terms": avoid_terms,
		"references": references,
		"reviewed": reviewed,
	}


def validate_case(value: object) -> EvaluationCase:
	"""Validate one newly generated or hand-authored case."""
	return _validate_case(value, 1, set())


def _string_list(value: object, case_id: str, name: str) -> list[str]:
	if not isinstance(value, list) or any(
		not isinstance(item, str) or not item.strip() for item in value
	):
		raise ValueError(f"Case {case_id} {name} must be a list of non-empty strings.")
	return value


def _criteria_list(value: object, case_id: str, name: str) -> list[Criterion]:
	if not isinstance(value, list):
		raise ValueError(f"Case {case_id} {name} must be a list.")
	criteria: list[Criterion] = []
	for criterion in value:
		if not isinstance(criterion, dict):
			raise ValueError(f"Case {case_id} contains an invalid {name} item.")
		description = criterion.get("description")
		raw_match_any = criterion.get("match_any")
		if isinstance(raw_match_any, str):
			raw_match_any = [raw_match_any]
		match_any = _string_list(raw_match_any, case_id, name)
		if not isinstance(description, str) or not description.strip() or not match_any:
			raise ValueError(f"Case {case_id} contains an incomplete {name} item.")
		criteria.append({"description": description, "match_any": match_any})
	return criteria


def matching_terms(answer: str, terms: list[str]) -> list[str]:
	answer_lower = answer.casefold()
	return [term for term in terms if term.casefold() in answer_lower]


def build_report(
	model: str,
	created_at: str,
	results: list[dict[str, object]],
) -> str:
	"""Build a self-contained Markdown report with every tested case."""
	case_sections: list[str] = []
	diagnosis_checks = 0
	diagnosis_matches = 0
	treatment_checks = 0
	treatment_matches = 0
	retrieval_checks = 0
	retrieval_matches = 0
	case_scores: list[float] = []
	for result in results:
		case = result["case"]
		if not isinstance(case, dict):
			raise ValueError("Report result has an invalid case.")
		answer = str(result["answer"])
		passages = result["passages"]
		diagnosis_result = matching_terms(answer, case["diagnosis_terms"])
		reasoning_matches = sum(
			bool(matching_terms(answer, criterion["match_any"]))
			for criterion in case["diagnosis_criteria"]
		)
		treatment_matches_for_case = sum(
			bool(matching_terms(answer, criterion["match_any"]))
			for criterion in case["treatment_plan_criteria"]
		)
		reasoning_total = len(case["diagnosis_criteria"])
		treatment_total = len(case["treatment_plan_criteria"])
		case_score = (
			(4.0 if diagnosis_result else 0.0)
			+ 3.0 * reasoning_matches / reasoning_total
			+ 3.0 * treatment_matches_for_case / treatment_total
		)
		case_scores.append(case_score)
		case_sections.extend(
			[
				f"## {case['id']} — {case['topic']}",
				"",
				f"- **Topic area:** {case['topic_area']}",
				f"- **Review status:** {'Reviewed' if case['reviewed'] else 'DRAFT — not reviewed'}",
				f"- **Jurisdiction:** {case['jurisdiction']}",
				f"- **Case score:** {case_score:.1f}/10",
				"",
				"### Case",
				"",
				str(case["case"]),
				"",
				"### Question",
				"",
				str(case["question"]),
				"",
				"### Expected diagnosis criteria",
				"",
				f"**Expected leading diagnosis:** {case['expected_diagnosis']}",
				"",
			]
		)
		diagnosis_checks += 1
		diagnosis_matches += bool(diagnosis_result)
		case_sections.append(
			f"- {'MATCH' if diagnosis_result else 'MISSING'} — accepted terms: "
			f"{', '.join(case['diagnosis_terms'])}"
		)
		_append_criteria(
			case_sections,
			"Reasoning",
			case["diagnosis_criteria"],
			answer,
		)
		diagnosis_checks += len(case["diagnosis_criteria"])
		diagnosis_matches += reasoning_matches
		_append_criteria(
			case_sections,
			"Treatment-plan criteria",
			case["treatment_plan_criteria"],
			answer,
		)
		treatment_checks += len(case["treatment_plan_criteria"])
		treatment_matches += treatment_matches_for_case
		retrieved_references = set()
		if isinstance(passages, list):
			retrieved_references = {
				(
					str(passage["source"]).casefold(),
					passage["page"],
					str(passage["jurisdiction"]).upper(),
				)
				for passage in passages
			}
		case_sections.extend(["", "### Expected source retrieval", ""])
		for reference in case["references"]:
			retrieval_checks += 1
			reference_key = (
				reference["source"].casefold(),
				reference["page"],
				reference["jurisdiction"].upper(),
			)
			found = reference_key in retrieved_references
			retrieval_matches += found
			case_sections.append(
				f"- {'MATCH' if found else 'MISSING'} — {reference['source']} "
				f"(p. {reference['page']}, {reference['jurisdiction']})"
			)
		avoid_hits = matching_terms(answer, case["avoid_terms"])
		case_sections.extend(
			[
				"",
				"### Terms to review",
				"",
				(
					f"- **Flagged terms present:** {', '.join(avoid_hits)}"
					if avoid_hits
					else "- No configured terms to review were detected."
				),
				"",
				"### Retrieved guideline references",
				"",
			]
		)
		if isinstance(passages, list) and passages:
			for passage in passages:
				case_sections.append(
					"- "
					+ f"{passage['source']} (p. {passage['page']}, "
					+ f"{passage['jurisdiction']}; score {passage['score']:.3f})"
				)
		else:
			case_sections.append("- No passages retrieved.")
		case_sections.extend(["", "### Model answer", "", answer, ""])
	header = [
		"# Guideline case evaluation",
		"",
		f"- **Run time:** {created_at}",
		f"- **Generation model:** `{model}`",
		f"- **Cases evaluated:** {len(results)}",
		f"- **Overall score:** {sum(case_scores) / len(case_scores):.1f}/10",
		f"- **Expected source retrieval:** {retrieval_matches}/{retrieval_checks}",
		f"- **Diagnosis phrase checks:** {diagnosis_matches}/{diagnosis_checks}",
		f"- **Treatment-plan phrase checks:** {treatment_matches}/{treatment_checks}",
		"- **Score formula:** leading diagnosis = 4 points; diagnostic reasoning = 3 "
		"points; treatment plan = 3 points. Each criterion category is proportionally "
		"scored using case-insensitive phrase matches. Overall score is the mean case "
		"score. This is a rough text-matching heuristic, not a clinical judgment.",
		"- **Retrieval score:** source/page/jurisdiction matches are reported separately "
		"and do not contribute to the answer score.",
		"",
	]
	return "\n".join(header + case_sections).rstrip() + "\n"


def _append_criteria(
	lines: list[str],
	heading: str,
	criteria: list[Criterion],
	answer: str,
) -> None:
	lines.extend(["", f"### {heading} criteria", ""])
	for criterion in criteria:
		matches = matching_terms(answer, criterion["match_any"])
		lines.append(
			f"- {'MATCH' if matches else 'MISSING'} — {criterion['description']} "
			f"(matched: {', '.join(matches) if matches else 'none'})"
		)

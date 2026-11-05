import json
from pathlib import Path

import pytest

import scripts.run_guideline_evaluation as runner
from src.evaluation.benchmark import (
	build_report,
	load_cases,
	matching_terms,
	validate_case,
)
from src.rag.retriever import GuidelinePassage


def case_data() -> dict[str, object]:
	return {
		"id": "sample-001",
		"topic_area": "Cardiovascular",
		"topic": "sample topic",
		"jurisdiction": "US",
		"case": "A fictional case with relevant findings.",
		"question": "What is the leading diagnosis and management plan?",
		"expected_diagnosis": "Expected condition",
		"diagnosis_terms": ["expected condition", "alternate name"],
		"diagnosis_criteria": [
			{
				"description": "Explain a supporting finding.",
				"match_any": ["supporting finding"],
			}
		],
		"treatment_plan_criteria": [
			{
				"description": "Include the guideline-supported plan.",
				"match_any": ["recommended management"],
			}
		],
		"avoid_terms": ["unsupported therapy"],
		"references": [
			{"source": "guide.pdf", "page": 4, "jurisdiction": "US"}
		],
		"reviewed": True,
	}


def test_load_cases_validates_diagnosis_and_treatment_criteria(tmp_path: Path) -> None:
	path = tmp_path / "cases.json"
	path.write_text(
		json.dumps({"schema_version": 1, "cases": [case_data()]}),
		encoding="utf-8",
	)

	cases = load_cases(path)

	assert len(cases) == 1
	assert cases[0]["reviewed"] is True
	assert cases[0]["treatment_plan_criteria"][0]["match_any"] == [
		"recommended management"
	]


def test_validate_case_requires_treatment_criteria() -> None:
	data = case_data()
	data["treatment_plan_criteria"] = []

	with pytest.raises(ValueError, match="diagnosis and treatment-plan criteria"):
		validate_case(data)


def test_validate_case_accepts_single_string_criterion_phrase() -> None:
	data = case_data()
	data["treatment_plan_criteria"] = [
		{
			"description": "Include the guideline-supported plan.",
			"match_any": "recommended management",
		}
	]

	case = validate_case(data)

	assert case["treatment_plan_criteria"][0]["match_any"] == [
		"recommended management"
	]


def test_matching_terms_is_case_insensitive() -> None:
	assert matching_terms(
		"Recommended Management is appropriate.",
		["recommended management"],
	) == ["recommended management"]


def test_report_includes_full_case_answer_and_all_criteria() -> None:
	case = case_data()
	report = build_report(
		"qwen3:8b",
		"2026-10-25T12:00:00+03:00",
		[
			{
				"case": case,
				"passages": [
					{
						"source": "guide.pdf",
						"page": 4,
						"jurisdiction": "US",
						"score": 0.91,
					}
				],
				"answer": (
					"The expected condition fits the supporting finding. "
					"Recommended management is appropriate."
				),
			}
		],
	)

	assert "A fictional case with relevant findings." in report
	assert "The expected condition fits" in report
	assert "Expected condition" in report
	assert "Include the guideline-supported plan" in report
	assert "Diagnosis phrase checks:** 2/2" in report
	assert "Treatment-plan phrase checks:** 1/1" in report
	assert "Overall score:** 10.0/10" in report
	assert "Case score:** 10.0/10" in report
	assert "Expected source retrieval:** 1/1" in report
	assert "guide.pdf (p. 4, US; score 0.910)" in report
	assert "not a clinical judgment" in report


def test_report_score_is_out_of_ten_and_averages_matched_categories() -> None:
	case = case_data()
	report = build_report(
		"qwen3:8b",
		"2026-10-25T12:00:00+03:00",
		[
			{
				"case": case,
				"passages": [],
				"answer": "The expected condition is the leading diagnosis.",
			}
		],
	)

	assert "Overall score:** 4.0/10" in report
	assert "Case score:** 4.0/10" in report


def test_generated_case_uses_passage_metadata_and_starts_unreviewed() -> None:
	passages: list[GuidelinePassage] = [
		{
			"text": "Guideline excerpt",
			"source": "guide.pdf",
			"page": 4,
			"jurisdiction": "US",
			"score": 0.9,
		}
	]
	generated = {
		"topic_area": "Cardiovascular",
		"case": "A fictional case.",
		"question": "Provide a diagnosis and plan.",
		"expected_diagnosis": "Expected condition",
		"diagnosis_terms": ["expected condition"],
		"diagnosis_criteria": [
			{"description": "Reasoning point", "match_any": ["supporting feature"]}
		],
		"treatment_plan_criteria": [
			{"description": "Plan point", "match_any": ["recommended management"]}
		],
		"passage_indices": [1],
	}

	case = runner._to_case(generated, "sample-001", "sample topic", passages)

	assert case["reviewed"] is False
	assert case["jurisdiction"] == "UNSPECIFIED"
	assert case["references"] == [
		{"source": "guide.pdf", "page": 4, "jurisdiction": "US"}
	]


def test_generated_case_preserves_unspecified_source_jurisdiction() -> None:
	passages: list[GuidelinePassage] = [
		{
			"text": "Guideline excerpt",
			"source": "guide.pdf",
			"page": 4,
			"jurisdiction": "UNSPECIFIED",
			"score": 0.9,
		}
	]
	generated = {
		"passage_indices": [1],
		"case": "A fictional case.",
		"question": "What is the likely diagnosis?",
		"expected_diagnosis": "Expected condition",
		"diagnosis_terms": ["expected condition"],
		"diagnosis_criteria": [
			{"description": "Finding", "match_any": ["supporting feature"]}
		],
		"treatment_plan_criteria": [
			{"description": "Plan", "match_any": ["recommended care"]}
		],
	}

	case = runner._to_case(generated, "sample-001", "sample topic", passages)

	assert case["jurisdiction"] == "UNSPECIFIED"
	assert case["references"][0]["jurisdiction"] == "UNSPECIFIED"


def test_evaluate_case_does_not_send_expected_diagnosis_to_model(monkeypatch) -> None:
	case = validate_case(case_data())
	passages = [
		{
			"text": "Retrieved evidence.",
			"source": "guide.pdf",
			"page": 4,
			"jurisdiction": "US",
			"score": 0.9,
		}
	]
	retrieval_calls = []
	generation_calls = []
	monkeypatch.setattr(
		runner,
		"retrieve_guidelines",
		lambda query, **kwargs: retrieval_calls.append((query, kwargs)) or passages,
	)
	monkeypatch.setattr(
		runner,
		"generate_grounded_answer",
		lambda question, retrieved, **kwargs: generation_calls.append(
			(question, retrieved, kwargs)
		)
		or "Answer",
	)

	result = runner.evaluate_case(case, limit=5)

	assert "A fictional case" in retrieval_calls[0][0]
	assert "Expected condition" not in retrieval_calls[0][0]
	assert retrieval_calls[0][1] == {"limit": 5}
	assert generation_calls[0][2] == {"include_sources": True}
	assert result["answer"] == "Answer"


def test_evaluate_case_accepts_unspecified_case_without_filter(monkeypatch) -> None:
	case = validate_case(case_data())
	case["jurisdiction"] = "UNSPECIFIED"
	retrieval_calls = []
	monkeypatch.setattr(
		runner,
		"retrieve_guidelines",
		lambda query, **kwargs: retrieval_calls.append(kwargs) or [],
	)

	runner.evaluate_case(case, limit=5)

	assert retrieval_calls == [{"limit": 5}]


def test_run_evaluation_generates_and_evaluates_cases(monkeypatch) -> None:
	source_passages: list[GuidelinePassage] = [
		{
			"text": "Source guideline.",
			"source": "guide.pdf",
			"page": 4,
			"jurisdiction": "US",
			"score": 0.9,
		}
	]
	retrieval_calls = []
	generated = {
		"topic_area": "Cardiovascular",
		"topic": "sample topic",
		"case": "A fictional case.",
		"question": "Give a diagnosis and plan.",
		"expected_diagnosis": "Expected condition",
		"diagnosis_terms": ["expected condition"],
		"diagnosis_criteria": [
			{"description": "Reasoning", "match_any": ["supporting feature"]}
		],
		"treatment_plan_criteria": [
			{"description": "Plan", "match_any": ["recommended management"]}
		],
		"passage_indices": [1],
	}
	monkeypatch.setattr(
		runner,
		"retrieve_guidelines",
		lambda query, **kwargs: retrieval_calls.append((query, kwargs))
		or source_passages,
	)
	monkeypatch.setattr(runner, "_request_case", lambda *args: generated)
	monkeypatch.setattr(
		runner,
		"evaluate_case",
		lambda case, limit: {"case": case, "passages": [], "answer": "Answer"},
	)

	results = runner.run_evaluation(1, 6, 5)

	assert len(results) == 1
	assert results[0]["case"]["reviewed"] is False
	assert retrieval_calls == [
		(
			"cardiovascular heart disease diagnosis management",
			{"limit": 6},
		)
	]


def test_run_evaluation_requests_distinct_clinical_areas(monkeypatch) -> None:
	source_passages: list[GuidelinePassage] = [
		{
			"text": "Source guideline.",
			"source": "guide.pdf",
			"page": 4,
			"jurisdiction": "US",
			"score": 0.9,
		}
	]
	retrieval_calls = []
	areas = ["Cardiovascular", "Respiratory", "Infectious disease"]
	generated_cases = [
		{
			"topic_area": area,
			"topic": f"{area} condition",
			"case": f"Fictional {area.lower()} case.",
			"question": "Give a diagnosis and plan.",
			"expected_diagnosis": "Expected condition",
			"diagnosis_terms": ["expected condition"],
			"diagnosis_criteria": [
				{"description": "Reasoning", "match_any": ["supporting feature"]}
			],
			"treatment_plan_criteria": [
				{"description": "Plan", "match_any": ["recommended management"]}
			],
			"passage_indices": [1],
		}
		for index, area in enumerate(areas, start=1)
	]
	monkeypatch.setattr(
		runner,
		"retrieve_guidelines",
		lambda query, **kwargs: retrieval_calls.append(query) or source_passages,
	)
	generated_by_area = {
		case["topic_area"]: case for case in generated_cases
	}
	monkeypatch.setattr(
		runner,
		"_request_case",
		lambda area, _: generated_by_area[area],
	)
	monkeypatch.setattr(
		runner,
		"evaluate_case",
		lambda case, limit: {"case": case, "passages": [], "answer": "Answer"},
	)

	results = runner.run_evaluation(3, 2, 2)

	assert [result["case"]["topic_area"] for result in results] == areas
	assert retrieval_calls == [query for _, query in runner.TOPIC_AREAS[:3]]


def test_single_cli_generates_cases_and_writes_report(
	monkeypatch,
	tmp_path: Path,
) -> None:
	report_path = tmp_path / "reports" / "report.md"
	case = validate_case(case_data())
	monkeypatch.setattr(
		runner,
		"run_evaluation",
		lambda *args, **kwargs: [
			{"case": case, "passages": [], "answer": "Model answer."}
		],
	)
	monkeypatch.setattr(
		"sys.argv",
		[
			"run_guideline_evaluation.py",
			"--count",
			"1",
			"--output",
			str(report_path),
		],
	)

	runner.main()

	report = report_path.read_text(encoding="utf-8")
	assert "A fictional case with relevant findings." in report
	assert "Model answer." in report

import argparse
import json
from pathlib import Path

import pytest

import scripts.generate_case_report as case_report
from src.rag.retriever import GuidelinePassage


def sample_passage() -> GuidelinePassage:
	return {
		"text": "Relevant US guideline excerpt.",
		"source": "guideline.pdf",
		"page": 3,
		"jurisdiction": "US",
		"score": 0.8,
	}


def test_request_case_parses_case_without_answer_key(monkeypatch) -> None:
	response_data = {
		"message": {
			"content": json.dumps(
				{
					"case": {
						"topic_area": "Cardiovascular",
						"topic": "A fictional cardiac condition",
						"case": "A fictional patient has relevant findings.",
						"question": "What is the likely diagnosis and management?",
					}
				}
			)
		}
	}

	class MockResponse:
		def __enter__(self):
			return self

		def __exit__(self, *_args):
			return None

		def read(self):
			return json.dumps(response_data).encode("utf-8")

	monkeypatch.setattr(case_report, "urlopen", lambda *_args, **_kwargs: MockResponse())

	case = case_report._request_case("Cardiovascular", [sample_passage()])

	assert case["topic_area"] == "Cardiovascular"
	assert set(case) == {"topic_area", "topic", "case", "question"}


@pytest.mark.parametrize(
	"content",
	[
		{
			"topic_area": "Cardiovascular",
			"topic": "A fictional cardiac condition",
			"case": "A fictional patient has relevant findings.",
			"question": "What is the likely diagnosis and management?",
		},
		{
			"cases": [
				{
					"topic_area": "Cardiovascular",
					"topic": "A fictional cardiac condition",
					"case": "A fictional patient has relevant findings.",
					"question": "What is the likely diagnosis and management?",
				}
			]
		},
	],
)
def test_request_case_accepts_direct_or_single_case_array_response(
	monkeypatch,
	content: dict[str, object],
) -> None:
	response_data = {"message": {"content": json.dumps(content)}}

	class MockResponse:
		def __enter__(self):
			return self

		def __exit__(self, *_args):
			return None

		def read(self):
			return json.dumps(response_data).encode("utf-8")

	monkeypatch.setattr(case_report, "urlopen", lambda *_args, **_kwargs: MockResponse())

	case = case_report._request_case("Cardiovascular", [sample_passage()])

	assert case["topic_area"] == "Cardiovascular"
	assert case["topic"] == "A fictional cardiac condition"


def test_request_case_fills_missing_area_and_topic(monkeypatch) -> None:
	response_data = {
		"message": {
			"content": json.dumps(
				{
					"case": "A fictional patient has respiratory symptoms.",
					"question": "What is the likely diagnosis and management?",
				}
			)
		}
	}

	class MockResponse:
		def __enter__(self):
			return self

		def __exit__(self, *_args):
			return None

		def read(self):
			return json.dumps(response_data).encode("utf-8")

	monkeypatch.setattr(case_report, "urlopen", lambda *_args, **_kwargs: MockResponse())

	case = case_report._request_case("Respiratory", [sample_passage()])

	assert case == {
		"topic_area": "Respiratory",
		"topic": "Respiratory",
		"case": "A fictional patient has respiratory symptoms.",
		"question": "What is the likely diagnosis and management?",
	}


def test_request_case_rejects_wrong_topic_area(monkeypatch) -> None:
	response_data = {
		"message": {
			"content": json.dumps(
				{
					"case": {
						"topic_area": "Respiratory",
						"topic": "Topic",
						"case": "Case text",
						"question": "Question",
					}
				}
			)
		}
	}

	class MockResponse:
		def __enter__(self):
			return self

		def __exit__(self, *_args):
			return None

		def read(self):
			return json.dumps(response_data).encode("utf-8")

	monkeypatch.setattr(case_report, "urlopen", lambda *_args, **_kwargs: MockResponse())

	with pytest.raises(RuntimeError, match="does not match"):
		case_report._request_case("Cardiovascular", [sample_passage()])


def test_run_cases_writes_report_without_scores_or_retrieval_metrics(
	monkeypatch,
	tmp_path: Path,
) -> None:
	report_path = tmp_path / "report.md"
	passage = sample_passage()
	retrieve_calls: list[tuple[str, int, dict[str, object]]] = []
	monkeypatch.setattr(
		case_report,
		"retrieve_guidelines",
		lambda query, limit, **kwargs: (
			retrieve_calls.append((query, limit, kwargs)) or [passage]
		),
	)
	monkeypatch.setattr(
		case_report,
		"_request_case",
		lambda area, _passages: {
			"topic_area": area,
			"topic": "Fictional topic",
			"case": "Fictional case details.",
			"question": "What is the likely diagnosis?",
		},
	)
	monkeypatch.setattr(
		case_report,
		"generate_grounded_answer",
		lambda query, passages, include_sources: "Model answer [S1].",
	)

	results = case_report.run_cases(
		1, 4, 3, report_path, "2026-10-26T00:00:00+03:00"
	)
	report = report_path.read_text(encoding="utf-8")

	assert len(results) == 1
	assert len(retrieve_calls) == 2
	assert all(call[2] == {} for call in retrieve_calls)
	assert "Fictional case details." in report
	assert "Model answer [S1]." in report
	assert "[S1] guideline.pdf (p. 3)" in report
	assert "score" not in report.lower()
	assert "retrieval" not in report.lower()


def test_run_cases_cycles_all_clinical_areas_before_repeating(
	monkeypatch,
	tmp_path: Path,
) -> None:
	areas: list[str] = []
	passage = sample_passage()
	monkeypatch.setattr(
		case_report,
		"retrieve_guidelines",
		lambda _query, **_kwargs: [passage],
	)

	def request_case(area: str, _passages: list[GuidelinePassage]) -> dict[str, str]:
		areas.append(area)
		return {
			"topic_area": area,
			"topic": f"Fictional {area} topic",
			"case": "Fictional case details.",
			"question": "What is the likely diagnosis?",
		}

	monkeypatch.setattr(case_report, "_request_case", request_case)
	monkeypatch.setattr(
		case_report,
		"generate_grounded_answer",
		lambda *_args, **_kwargs: "Model answer.",
	)

	results = case_report.run_cases(
		len(case_report.TOPIC_AREAS) + 1,
		4,
		3,
		tmp_path / "report.md",
		"2026-10-26T00:00:00+03:00",
	)

	assert len(results) == len(case_report.TOPIC_AREAS) + 1
	expected_areas = [area for area, _query in case_report.TOPIC_AREAS]
	assert len(expected_areas) >= 50
	assert len(set(expected_areas)) == len(expected_areas)
	assert areas[: len(expected_areas)] == expected_areas
	assert areas[len(expected_areas)] == expected_areas[0]
	assert case_report._case_count("1000") == 1000
	with pytest.raises(argparse.ArgumentTypeError, match="between 1 and 1000"):
		case_report._case_count("1001")

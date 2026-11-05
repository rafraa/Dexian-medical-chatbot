import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import GENERATION_MODEL, OLLAMA_BASE_URL
from src.evaluation.benchmark import (
	EvaluationCase,
	build_report,
	validate_case,
)
from src.rag.generator import generate_grounded_answer
from src.rag.retriever import GuidelinePassage, retrieve_guidelines


EVALUATION_JURISDICTION = "UNSPECIFIED"
TOPIC_AREAS = (
	("Cardiovascular", "cardiovascular heart disease diagnosis management"),
	("Respiratory", "respiratory lung disease diagnosis management"),
	("Infectious disease", "infectious diseases diagnosis management"),
	("Endocrine", "endocrine diabetes metabolic disease diagnosis management"),
	("Gastrointestinal", "gastrointestinal digestive disease diagnosis management"),
	("Neurology", "neurological nervous system disease diagnosis management"),
	("Renal and urinary", "renal kidney urinary disease diagnosis management"),
	("Hematology", "hematology blood disorders diagnosis management"),
	("Musculoskeletal", "musculoskeletal rheumatology disease diagnosis management"),
	("Dermatology", "dermatology skin disease diagnosis management"),
)

CASE_GENERATION_PROMPT = """Create draft, entirely fictional clinical reasoning benchmark cases using
only the provided medical-reference excerpts. Do not copy an existing real patient story or include
identifying details. Do not add diagnoses or management steps that are not supported by the
excerpts. Create exactly one case for the requested topic area; do not change its area.
If the excerpts do not support a useful case with a diagnosis and treatment-plan rubric, do not
invent unsupported facts. Return JSON only, with a top-level "cases" array containing one case.
The case must include "topic_area", "topic", "case", "question", "expected_diagnosis",
"diagnosis_terms" (an array of short phrases that may appear in a correct answer),
"diagnosis_criteria" (an array of objects with "description" and "match_any" phrase array),
"treatment_plan_criteria" (same object shape), "avoid_terms" (array of risky or contrary phrases
to flag for human review), and "passage_indices" (1-based excerpt indexes that support this case).
Use short phrases for match terms. Each criterion should test one important idea. Avoid
specifying medication doses unless the excerpts explicitly state them. These are unreviewed
drafts and must not be represented as validated clinical cases."""


def _request_case(
	topic_area: str,
	passages: list[GuidelinePassage],
) -> dict[str, object]:
	excerpts = "\n\n".join(
		f"[P{index}] Source: {passage['source']}; page: {passage['page']}; "
		f"source type: {passage.get('source_type', 'unknown')}; "
		f"guideline status: {passage.get('guideline_status', 'not_verified')}\n"
		f"{passage['text']}"
		for index, passage in enumerate(passages, start=1)
	)
	user_prompt = (
		f"Create one fictional case in the topic area {topic_area}. Set topic_area to "
		f"exactly {json.dumps(topic_area)}. Use only the supplied passages and their P "
		"numbers as supporting evidence. Do not include the expected answer in the case "
		f"or question.\n\nMedical-reference excerpts:\n{excerpts}"
	)
	body = json.dumps(
		{
			"model": GENERATION_MODEL,
			"stream": False,
			"format": "json",
			"messages": [
				{"role": "system", "content": CASE_GENERATION_PROMPT},
				{"role": "user", "content": user_prompt},
			],
		}
	).encode("utf-8")
	request = Request(
		f"{OLLAMA_BASE_URL}/api/chat",
		data=body,
		headers={"Content-Type": "application/json"},
		method="POST",
	)
	try:
		with urlopen(request, timeout=180) as response:
			result = json.loads(response.read().decode("utf-8"))
	except HTTPError as exc:
		detail = exc.read(1000).decode("utf-8", errors="replace").strip()
		raise RuntimeError(
			f"Ollama failed to generate the {topic_area} case "
			f"(HTTP {exc.code}): {detail or exc.reason}"
		) from exc
	message = result.get("message") if isinstance(result, dict) else None
	content = message.get("content") if isinstance(message, dict) else None
	if not isinstance(content, str) or not content.strip():
		raise RuntimeError(f"Ollama returned an empty {topic_area} case response.")
	try:
		data = json.loads(content)
	except json.JSONDecodeError as exc:
		raise RuntimeError(
			f"Model did not return valid JSON for {topic_area}: {exc}"
		) from exc
	if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
		raise RuntimeError('Model response must be JSON with a "cases" array.')
	if len(data["cases"]) != 1 or not isinstance(data["cases"][0], dict):
		raise RuntimeError(f"Model must return exactly one {topic_area} case.")
	return data["cases"][0]


def _to_case(
	generated: dict[str, object],
	case_id: str,
	topic_area: str,
	passages: list[GuidelinePassage],
) -> EvaluationCase:
	indices = generated.get("passage_indices")
	if (
		not isinstance(indices, list)
		or not indices
		or any(
			type(index) is not int or not 1 <= index <= len(passages)
			for index in indices
		)
	):
		raise RuntimeError("Generated case contains invalid supporting passage_indices.")
	unique_indices = list(dict.fromkeys(indices))
	return validate_case(
		{
			"id": case_id,
			"topic_area": topic_area,
			"topic": generated.get("topic", topic_area),
			"jurisdiction": EVALUATION_JURISDICTION,
			"case": generated.get("case", ""),
			"question": generated.get("question", ""),
			"expected_diagnosis": generated.get("expected_diagnosis", ""),
			"diagnosis_terms": generated.get("diagnosis_terms", []),
			"diagnosis_criteria": generated.get("diagnosis_criteria", []),
			"treatment_plan_criteria": generated.get("treatment_plan_criteria", []),
			"avoid_terms": generated.get("avoid_terms", []),
			"references": [
				{
					"source": passages[index - 1]["source"],
					"page": passages[index - 1]["page"],
					"jurisdiction": passages[index - 1]["jurisdiction"],
				}
				for index in unique_indices
			],
			"reviewed": False,
		}
	)


def evaluate_case(
	case: EvaluationCase,
	limit: int,
) -> dict[str, object]:
	query = f"{case['case']}\n\n{case['question']}"
	passages = retrieve_guidelines(
		query,
		limit=limit,
	)
	if not passages:
		answer = "No relevant medical-reference passages were retrieved; generation was skipped."
	else:
		answer = generate_grounded_answer(
			query,
			passages,
			include_sources=True,
		)
	return {"case": case, "passages": passages, "answer": answer}


def run_evaluation(
	count: int,
	generation_limit: int,
	evaluation_limit: int,
	report_path: Path | None = None,
	created_at: str | None = None,
) -> list[dict[str, object]]:
	selected_areas = TOPIC_AREAS[:count]
	created_at = created_at or datetime.now().astimezone().isoformat(timespec="seconds")
	results: list[dict[str, object]] = []
	for index, (area, query) in enumerate(selected_areas, start=1):
		print(f"[{index}/{count}] Retrieving reference passages for {area}...", flush=True)
		area_passages = retrieve_guidelines(
			query,
			limit=generation_limit,
		)
		if not area_passages:
			raise RuntimeError(
				f"No medical-reference passages were retrieved for the {area} topic area."
			)
		print(f"[{index}/{count}] Generating {area} case...", flush=True)
		generated = _request_case(area, area_passages)
		case = _to_case(
			generated,
			f"mixed-us-guidelines-{index:03d}",
			area,
			area_passages,
		)
		print(f"[{index}/{count}] Evaluating {area} case...", flush=True)
		results.append(evaluate_case(case, evaluation_limit))
		if report_path is not None:
			report_path.parent.mkdir(parents=True, exist_ok=True)
			report_path.write_text(
				build_report(GENERATION_MODEL, created_at, results),
				encoding="utf-8",
			)
	return results


def main() -> None:
	parser = argparse.ArgumentParser(
		description=(
			"Generate cases across clinical areas, evaluate them, and save a report."
		)
	)
	parser.add_argument("--count", type=int, default=3, choices=range(1, 11))
	parser.add_argument("--generation-limit", type=int, default=6, choices=range(1, 11))
	parser.add_argument("--evaluation-limit", type=int, default=5, choices=range(1, 11))
	parser.add_argument(
		"--output",
		type=Path,
		help="Report path (defaults to a timestamped file under evaluation/reports)",
	)
	args = parser.parse_args()

	created_at = datetime.now().astimezone().isoformat(timespec="seconds")
	output = args.output or Path(
		f"evaluation/reports/report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
	)
	results = run_evaluation(
		args.count,
		args.generation_limit,
		args.evaluation_limit,
		report_path=output,
		created_at=created_at,
	)
	report = build_report(GENERATION_MODEL, created_at, results)
	output.parent.mkdir(parents=True, exist_ok=True)
	output.write_text(report, encoding="utf-8")
	print(f"Generated and evaluated {len(results)} case(s) with {GENERATION_MODEL}.")
	print("Cases and model answers are unreviewed; inspect the report carefully.")
	print(f"Report saved to {output}")


if __name__ == "__main__":
	main()

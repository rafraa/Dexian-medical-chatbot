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
from src.rag.generator import generate_grounded_answer
from src.rag.retriever import GuidelinePassage, retrieve_guidelines


MAX_CASES = 1000
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
	("Allergy and immunology", "allergy immunology immune disorders diagnosis management"),
	("Anesthesiology", "anesthesiology perioperative anesthesia pain management"),
	("Critical care", "critical care intensive care diagnosis management"),
	("Emergency medicine", "emergency medicine acute illness injury management"),
	("Family medicine", "family medicine primary care prevention diagnosis management"),
	("Internal medicine", "internal medicine adult diagnosis management"),
	("Medical genetics", "medical genetics inherited disorders diagnosis management"),
	("Nuclear medicine", "nuclear medicine imaging diagnosis management"),
	("Occupational medicine", "occupational medicine workplace health injury management"),
	("Pathology", "pathology laboratory diagnosis disease management"),
	("Pediatrics", "pediatrics childhood diagnosis management"),
	("Physical medicine and rehabilitation", "physical medicine rehabilitation disability recovery"),
	("Preventive medicine and public health", "preventive medicine public health screening prevention"),
	("Psychiatry", "psychiatry mental health diagnosis treatment"),
	("Radiology", "radiology imaging diagnosis management"),
	("Rheumatology", "rheumatology autoimmune inflammatory joint disease"),
	("Sleep medicine", "sleep medicine sleep disorders diagnosis management"),
	("Sports medicine", "sports medicine exercise injury diagnosis management"),
	("Surgery", "general surgery surgical conditions diagnosis management"),
	("Urology", "urology urinary bladder prostate disorders management"),
	("Obstetrics and gynecology", "obstetrics gynecology pregnancy reproductive health"),
	("Maternal-fetal medicine", "maternal fetal medicine high risk pregnancy management"),
	("Reproductive endocrinology and infertility", "reproductive endocrinology infertility fertility treatment"),
	("Neonatology", "neonatology newborn premature infant care"),
	("Adolescent medicine", "adolescent medicine teen health diagnosis management"),
	("Geriatrics", "geriatrics older adults frailty diagnosis management"),
	("Cardiology", "cardiology heart rhythm heart failure cardiovascular treatment"),
	("Cardiothoracic surgery", "cardiothoracic surgery heart lung surgical care"),
	("Vascular surgery", "vascular surgery arterial venous disease management"),
	("Pulmonology", "pulmonology lung respiratory disease diagnosis management"),
	("Hepatology", "hepatology liver disease diagnosis treatment"),
	("Gastroenterology", "gastroenterology digestive bowel disease management"),
	("Nephrology", "nephrology kidney disease dialysis diagnosis management"),
	("Medical oncology", "medical oncology cancer diagnosis systemic treatment"),
	("Radiation oncology", "radiation oncology cancer radiotherapy management"),
	("Surgical oncology", "surgical oncology cancer surgery management"),
	("Palliative care", "palliative care symptom management serious illness"),
	("Pain medicine", "pain medicine chronic acute pain diagnosis management"),
	("Addiction medicine", "addiction medicine substance use disorder treatment"),
	("Child and adolescent psychiatry", "child adolescent psychiatry behavioral mental health"),
	("Ophthalmology", "ophthalmology eye vision disease diagnosis management"),
	("Otolaryngology", "otolaryngology ear nose throat head neck disorders"),
	("Neurosurgery", "neurosurgery brain spine neurological surgical care"),
	("Orthopedic surgery", "orthopedic surgery bone joint injury management"),
	("Plastic surgery", "plastic reconstructive surgery wound burn care"),
	("Colorectal surgery", "colorectal surgery colon rectal disease management"),
	("Transplant medicine", "transplant medicine organ transplant complications management"),
	("Infectious diseases and HIV medicine", "infectious disease HIV antimicrobial treatment"),
	("Clinical pharmacology and toxicology", "clinical pharmacology medication safety toxicology poisoning"),
	("Wound care", "wound care ulcers pressure injury burns management"),
	("Dentistry and oral medicine", "oral medicine dentistry dental conditions management"),
	("Osteopathic medicine", "osteopathic medicine primary care diagnosis management"),
	("Hematology-oncology", "hematology oncology blood cancer diagnosis treatment"),
)

CASE_GENERATION_PROMPT = """Create one draft, entirely fictional clinical case for review by a
physician. Use only the supplied medical-reference excerpts as clinical support. Do not copy an existing
patient story or include identifying details. The case should contain enough relevant information
to invite clinical reasoning without stating its intended diagnosis or answer. Ask what the likely
diagnosis is, what findings support it, and what initial management is appropriate based on the
available information. Do not invent facts unsupported by the excerpts. Return JSON only with a
top-level "case" object containing exactly these string fields: "topic_area", "topic", "case",
and "question". Do not include an answer key, diagnosis, rubric, or scoring criteria. These are
unreviewed drafts, not validated clinical cases."""


def _request_case(
	topic_area: str,
	passages: list[GuidelinePassage],
) -> dict[str, str]:
	excerpts = "\n\n".join(
		f"[P{index}] {passage['text']}"
		for index, passage in enumerate(passages, start=1)
	)
	user_prompt = (
		f"Create one fictional case for topic area {json.dumps(topic_area)}. "
		f"Set topic_area to exactly {json.dumps(topic_area)}.\n\n"
		f"Guideline excerpts:\n{excerpts}"
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
	required = ("case", "question")
	case: object = None
	if isinstance(data, dict):
		wrapped_case = data.get("case")
		cases = data.get("cases")
		if isinstance(wrapped_case, dict):
			case = wrapped_case
		elif isinstance(cases, list) and len(cases) == 1:
			case = cases[0]
		elif all(key in data for key in required):
			case = data
	if not isinstance(case, dict):
		keys = ", ".join(data.keys()) if isinstance(data, dict) else type(data).__name__
		raise RuntimeError(
			"Model response must be a case object, an object containing a 'case' "
			f"object, or an object containing one case in 'cases'; received keys: {keys}."
		)
	if any(not isinstance(case.get(key), str) or not case[key].strip() for key in required):
		raise RuntimeError(
			f"Generated {topic_area} case must contain non-empty string fields: "
			+ ", ".join(required)
		)
	response_area = case.get("topic_area", topic_area)
	if not isinstance(response_area, str) or response_area != topic_area:
		raise RuntimeError(
			f"Generated case area {response_area!r} does not match {topic_area!r}."
		)
	topic = case.get("topic", topic_area)
	if not isinstance(topic, str) or not topic.strip():
		topic = topic_area
	return {
		"topic_area": topic_area,
		"topic": topic.strip(),
		"case": case["case"].strip(),
		"question": case["question"].strip(),
	}


def build_report(
	created_at: str,
	results: list[dict[str, object]],
) -> str:
	lines = _report_header(created_at, len(results))
	lines.extend(
		_format_case_section(index, result)
		for index, result in enumerate(results, start=1)
	)
	return "\n".join(lines) + "\n"


def _report_header(created_at: str, case_count: int) -> list[str]:
	return [
		"# Clinical case and model answer report",
		"",
		f"- **Run time:** {created_at}",
		f"- **Model:** `{GENERATION_MODEL}`",
		f"- **Cases requested:** {case_count}",
		"",
		"> Cases and answers are AI-generated drafts for physician review, not clinical "
		"validation or medical advice.",
	]


def _format_case_section(index: int, result: dict[str, object]) -> str:
	case = result["case"]
	passages = result["passages"]
	lines = [
		"",
		f"## Case {index}: {case['topic']}",
		"",
		f"- **Topic area:** {case['topic_area']}",
		"",
		"### Case",
		"",
		case["case"],
		"",
		"### Question",
		"",
		case["question"],
		"",
		"### Model answer",
		"",
		str(result["answer"]),
		"",
		"### Guideline sources used",
		"",
	]
	for source_index, passage in enumerate(passages, start=1):
		lines.append(f"- [S{source_index}] {passage['source']} (p. {passage['page']})")
	return "\n".join(lines) + "\n"


def run_cases(
	count: int,
	generation_limit: int,
	answer_limit: int,
	report_path: Path,
	created_at: str,
) -> list[dict[str, object]]:
	results: list[dict[str, object]] = []
	report_path.parent.mkdir(parents=True, exist_ok=True)
	report_path.write_text(
		"\n".join(_report_header(created_at, count)) + "\n",
		encoding="utf-8",
	)
	for index in range(1, count + 1):
		area, query = TOPIC_AREAS[(index - 1) % len(TOPIC_AREAS)]
		print(f"[{index}/{count}] Retrieving reference passages for {area}...", flush=True)
		generation_passages = retrieve_guidelines(
			query,
			limit=generation_limit,
		)
		if not generation_passages:
			raise RuntimeError(f"No medical-reference passages were retrieved for {area}.")
		print(f"[{index}/{count}] Generating {area} case...", flush=True)
		case = _request_case(area, generation_passages)
		print(f"[{index}/{count}] Generating model answer...", flush=True)
		answer_query = f"{case['case']}\n\n{case['question']}"
		answer_passages = retrieve_guidelines(
			answer_query,
			limit=answer_limit,
		)
		if not answer_passages:
			raise RuntimeError(
				f"No medical-reference passages were retrieved to answer case {index} ({area})."
			)
		answer = generate_grounded_answer(
			answer_query,
			answer_passages,
			include_sources=True,
		)
		results.append(
			{"case": case, "answer": answer, "passages": answer_passages}
		)
		with report_path.open("a", encoding="utf-8") as report_file:
			report_file.write(_format_case_section(index, results[-1]))
	return results


def _case_count(value: str) -> int:
	try:
		count = int(value)
	except ValueError as exc:
		raise argparse.ArgumentTypeError("must be a whole number") from exc
	if not 1 <= count <= MAX_CASES:
		raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_CASES}")
	return count


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Generate fictional clinical cases, answer them with the model, and save a report."
	)
	parser.add_argument(
		"--count",
		type=_case_count,
		default=3,
		metavar="1-1000",
		help=f"number of cases to generate (cycles through {len(TOPIC_AREAS)} clinical areas)",
	)
	parser.add_argument("--generation-limit", type=int, default=6, choices=range(1, 11))
	parser.add_argument("--answer-limit", type=int, default=5, choices=range(1, 11))
	parser.add_argument(
		"--output",
		type=Path,
		help="Report path (defaults to a timestamped file under evaluation/reports)",
	)
	args = parser.parse_args()

	created_at = datetime.now().astimezone().isoformat(timespec="seconds")
	output = args.output or Path(
		f"evaluation/reports/cases-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
	)
	results = run_cases(
		args.count,
		args.generation_limit,
		args.answer_limit,
		output,
		created_at,
	)
	print(f"Generated and answered {len(results)} case(s) with {GENERATION_MODEL}.")
	print(f"Report saved to {output}")


if __name__ == "__main__":
	main()

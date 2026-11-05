from typing import NotRequired, TypedDict

from src.vector_db.indexer import search_chunks


class GuidelinePassage(TypedDict):
	text: str
	source: str
	page: int
	jurisdiction: str
	score: float
	title: NotRequired[str]
	publisher: NotRequired[str]
	publication_year: NotRequired[str]
	document_type: NotRequired[str]
	source_type: NotRequired[str]
	guideline_status: NotRequired[str]


def retrieve_guidelines(
	question: str,
	limit: int = 5,
	jurisdiction: str | None = None,
) -> list[GuidelinePassage]:
	"""Retrieve source passages with the provenance needed for citations."""
	results = search_chunks(question, limit=limit, jurisdiction=jurisdiction)
	passages: list[GuidelinePassage] = []
	for result in results:
		payload = result.get("payload")
		if not isinstance(payload, dict):
			raise RuntimeError("A retrieved guideline has an invalid payload.")

		text = payload.get("text")
		source = payload.get("source")
		page = payload.get("page")
		result_jurisdiction = payload.get("jurisdiction")
		score = result.get("score")
		if (
			not isinstance(text, str)
			or not text.strip()
			or not isinstance(source, str)
			or type(page) is not int
			or not isinstance(result_jurisdiction, str)
			or not isinstance(score, (int, float))
		):
			raise RuntimeError("A retrieved guideline is missing citation metadata.")

		passages.append(
			{
				"text": text,
				"source": source,
				"page": page,
				"jurisdiction": result_jurisdiction,
				"score": float(score),
				"title": str(payload.get("title") or source.rsplit("\\", maxsplit=1)[-1]),
				"publisher": str(payload.get("publisher") or ""),
				"publication_year": str(payload.get("publication_year") or ""),
				"document_type": str(payload.get("document_type") or ""),
				"source_type": str(payload.get("source_type") or "unknown"),
				"guideline_status": str(payload.get("guideline_status") or "not_verified"),
			}
		)
	return passages
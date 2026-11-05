import pytest

import src.rag.retriever as retriever


def test_retrieve_guidelines_preserves_provenance(monkeypatch) -> None:
	search_calls = []
	monkeypatch.setattr(
		retriever,
		"search_chunks",
		lambda query, limit, jurisdiction: search_calls.append(
			(query, limit, jurisdiction)
		)
		or [
			{
				"score": 0.88,
				"payload": {
					"text": "Guideline passage",
					"source": "guideline.pdf",
					"page": 3,
					"jurisdiction": "EU",
				},
			}
		],
	)

	passages = retriever.retrieve_guidelines("question", jurisdiction="EU")

	assert passages == [
		{
			"text": "Guideline passage",
			"source": "guideline.pdf",
			"page": 3,
			"jurisdiction": "EU",
			"score": 0.88,
			"title": "guideline.pdf",
			"publisher": "",
			"publication_year": "",
			"document_type": "",
			"source_type": "unknown",
			"guideline_status": "not_verified",
		}
	]
	assert search_calls == [("question", 5, "EU")]


def test_retrieve_guidelines_supports_unfiltered_patient_search(monkeypatch) -> None:
	search_calls = []
	monkeypatch.setattr(
		retriever,
		"search_chunks",
		lambda query, limit, jurisdiction: search_calls.append(
			(query, limit, jurisdiction)
		)
		or [
			{
				"score": 0.8,
				"payload": {
					"text": "Reference excerpt.",
					"source": r"references\chapter.nxml",
					"page": 1,
					"jurisdiction": "UNSPECIFIED",
					"title": "A Reference Chapter",
					"publisher": "StatPearls Publishing",
					"publication_year": "2024",
					"document_type": "book chapter",
					"source_type": "reference_chapter",
					"guideline_status": "not_verified",
				},
			}
		],
	)

	passages = retriever.retrieve_guidelines("question")

	assert search_calls == [("question", 5, None)]
	assert passages[0]["jurisdiction"] == "UNSPECIFIED"
	assert passages[0]["title"] == "A Reference Chapter"
	assert passages[0]["source_type"] == "reference_chapter"
	assert passages[0]["guideline_status"] == "not_verified"


def test_retrieve_guidelines_rejects_missing_citation_metadata(monkeypatch) -> None:
	monkeypatch.setattr(
		retriever,
		"search_chunks",
		lambda *args, **kwargs: [{"score": 0.8, "payload": {"text": "No source"}}],
	)

	with pytest.raises(RuntimeError, match="missing citation metadata"):
		retriever.retrieve_guidelines("question")
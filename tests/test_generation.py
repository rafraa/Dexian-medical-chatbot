import json
from io import BytesIO

import pytest

import src.rag.generator as generator


def test_generate_grounded_answer_sends_labeled_sources(monkeypatch) -> None:
	requests = []
	response = BytesIO(
		json.dumps({"message": {"content": "A source-grounded answer [S1]."}}).encode()
	)
	monkeypatch.setattr(
		generator,
		"urlopen",
		lambda request, timeout: requests.append((request, timeout)) or response,
	)
	passages = [
		{
			"text": "Relevant guideline text.",
			"source": "guideline.pdf",
			"page": 2,
			"jurisdiction": "US",
			"score": 0.95,
		}
	]

	answer = generator.generate_grounded_answer(
		"Question?",
		passages,
		include_sources=True,
	)

	request, timeout = requests[0]
	body = json.loads(request.data.decode())
	assert answer == "A source-grounded answer [S1]."
	assert request.full_url.endswith("/api/chat")
	assert timeout == 120
	assert body["stream"] is False
	assert body["keep_alive"] == generator.OLLAMA_KEEP_ALIVE
	assert "guideline.pdf" in body["messages"][1]["content"]
	assert "[S1]" in body["messages"][1]["content"]


def test_generate_grounded_answer_rejects_empty_passages() -> None:
	with pytest.raises(ValueError, match="At least one passage"):
		generator.generate_grounded_answer("Question?", [])


def test_generate_grounded_answer_uses_thread_context_without_exposing_citations(
	monkeypatch,
) -> None:
	requests = []
	response = BytesIO(json.dumps({"message": {"content": "A concise answer."}}).encode())
	monkeypatch.setattr(
		generator,
		"urlopen",
		lambda request, timeout: requests.append(request) or response,
	)
	passages = [
		{
			"text": "Relevant guideline text.",
			"source": "guideline.pdf",
			"page": 2,
			"jurisdiction": "EG",
			"score": 0.91,
		}
	]

	generator.generate_grounded_answer(
		"Has it worsened?",
		passages,
		history=[{"role": "user", "content": "My shoulder has hurt since yesterday."}],
		conversation_summary="Pain is in the left shoulder.",
	)

	body = json.loads(requests[0].data.decode())
	encoded_messages = json.dumps(body["messages"])
	assert "My shoulder has hurt since yesterday." in encoded_messages
	assert "Pain is in the left shoulder." in encoded_messages
	assert "Do not use source labels or citations unless the user explicitly asks" in body[
		"messages"
	][0]["content"]
	assert "usually 1-3 short sentences" in body["messages"][0]["content"]
	assert "Do not begin with phrases like" in body["messages"][0]["content"]
	assert "leading working diagnosis or ranked" in body["messages"][0]["content"]
	assert "than forcing everything into 1-3 sentences" in body["messages"][0]["content"]
	assert "guideline.pdf" not in encoded_messages


def test_summarize_conversation_compacts_older_context(monkeypatch) -> None:
	requests = []
	response = BytesIO(
		json.dumps({"message": {"content": "User reports pain since yesterday."}}).encode()
	)
	monkeypatch.setattr(
		generator,
		"urlopen",
		lambda request, timeout: requests.append(request) or response,
	)

	summary = generator.summarize_conversation(
		"",
		[{"role": "user", "content": "My left shoulder started hurting yesterday."}],
	)

	body = json.loads(requests[0].data.decode())
	assert summary == "User reports pain since yesterday."
	assert "My left shoulder started hurting yesterday." in body["messages"][1]["content"]

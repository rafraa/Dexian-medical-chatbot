import asyncio

from httpx import ASGITransport, AsyncClient

import src.api.routes as routes
from src.api.app import app
from src.conversations.store import ConversationStore


def send_request(method: str, path: str, payload: dict[str, object] | None = None):
	async def send_request():
		async with AsyncClient(
			transport=ASGITransport(app=app),
			base_url="http://test",
		) as client:
			return await client.request(method, path, json=payload)

	return asyncio.run(send_request())


def post_ask(payload: dict[str, object]):
	return send_request("POST", "/api/ask", payload)


def test_ask_returns_grounded_answer_and_source_citations(monkeypatch) -> None:
	passages = [
		{
			"text": "The reference recommends follow-up within two weeks.",
			"source": "reference.nxml",
			"page": 1,
			"jurisdiction": "UNSPECIFIED",
			"score": 0.91,
			"title": "Example Reference",
			"publisher": "StatPearls Publishing",
			"publication_year": "2024",
			"document_type": "book chapter",
			"source_type": "reference_chapter",
			"guideline_status": "not_verified",
		}
	]
	retrieval_calls = []
	monkeypatch.setattr(
		routes,
		"retrieve_guidelines",
		lambda *args, **kwargs: retrieval_calls.append((args, kwargs)) or passages,
	)
	monkeypatch.setattr(
		routes,
		"generate_grounded_answer",
		lambda question, retrieved, **kwargs: "Follow-up is recommended within two weeks [S1].",
	)

	response = post_ask({"question": "When is follow-up?"})

	assert response.status_code == 200
	assert retrieval_calls == [(("When is follow-up?",), {"limit": 5})]
	assert response.json() == {
		"answer": "Follow-up is recommended within two weeks [S1].",
		"sources": [
			{
				"id": "S1",
				"text": "The reference recommends follow-up within two weeks.",
				"source": "reference.nxml",
				"page": 1,
				"jurisdiction": "UNSPECIFIED",
				"score": 0.91,
				"title": "Example Reference",
				"publisher": "StatPearls Publishing",
				"publication_year": "2024",
				"document_type": "book chapter",
				"source_type": "reference_chapter",
				"guideline_status": "not_verified",
			}
		],
	}


def test_ask_does_not_generate_when_no_passages_are_found(monkeypatch) -> None:
	monkeypatch.setattr(routes, "retrieve_guidelines", lambda *args, **kwargs: [])

	def unexpected_generation(*args, **kwargs):
		raise AssertionError("Generation must not run without evidence.")

	monkeypatch.setattr(routes, "generate_grounded_answer", unexpected_generation)

	response = post_ask({"question": "Unindexed question"})

	assert response.status_code == 200
	assert response.json()["sources"] == []
	assert "can't provide a source-grounded answer" in response.json()["answer"]


def test_ask_ignores_removed_jurisdiction_and_validates_limits(monkeypatch) -> None:
	retrieval_calls = []
	monkeypatch.setattr(
		routes,
		"retrieve_guidelines",
		lambda *args, **kwargs: retrieval_calls.append((args, kwargs)) or [],
	)
	removed_jurisdiction = post_ask(
		{"question": "Question", "jurisdiction": "CA"}
	)
	invalid_limit = post_ask({"question": "Question", "limit": 11})

	assert removed_jurisdiction.status_code == 200
	assert retrieval_calls == [(("Question",), {"limit": 5})]
	assert invalid_limit.status_code == 422


def test_chat_history_is_persistent_and_isolated_per_conversation(
	monkeypatch,
	tmp_path,
) -> None:
	store = ConversationStore(tmp_path / "chat_history.sqlite3")
	monkeypatch.setattr(routes, "get_conversation_store", lambda: store)
	retrieval_queries = []
	generation_calls = []
	monkeypatch.setattr(
		routes,
		"retrieve_guidelines",
		lambda query, **kwargs: retrieval_queries.append(query)
		or [
			{
				"text": "A guideline passage.",
				"source": "guideline.pdf",
				"page": 7,
				"jurisdiction": "EG",
				"score": 0.9,
			}
		],
	)

	def generate(question, passages, **kwargs):
		generation_calls.append({"question": question, **kwargs})
		return f"Answer to: {question}"

	monkeypatch.setattr(routes, "generate_grounded_answer", generate)
	first = send_request("POST", "/api/conversations", {"title": "New chat"})
	second = send_request("POST", "/api/conversations", {"title": "Another chat"})
	first_id = first.json()["id"]
	second_id = second.json()["id"]

	send_request(
		"POST",
		f"/api/conversations/{first_id}/messages",
		{"question": "My shoulder hurts."},
	)
	send_request(
		"POST",
		f"/api/conversations/{second_id}/messages",
		{"question": "My knee hurts."},
	)
	follow_up = send_request(
		"POST",
		f"/api/conversations/{first_id}/messages",
		{"question": "It started yesterday."},
	)

	assert first.status_code == 201
	assert second.status_code == 201
	assert follow_up.status_code == 200
	assert "My shoulder hurts." in retrieval_queries[-1]
	assert "My knee hurts." not in retrieval_queries[-1]
	assert generation_calls[-1]["history"] == [
		{"role": "user", "content": "My shoulder hurts."},
		{"role": "assistant", "content": "Answer to: My shoulder hurts."},
	]
	assert follow_up.json()["assistant_message"]["sources"] == []

	persisted = send_request("GET", f"/api/conversations/{first_id}")
	other = send_request("GET", f"/api/conversations/{second_id}")
	assert [message["content"] for message in persisted.json()["messages"]] == [
		"My shoulder hurts.",
		"Answer to: My shoulder hurts.",
		"It started yesterday.",
		"Answer to: It started yesterday.",
	]
	assert len(other.json()["messages"]) == 2


def test_listing_empty_conversation_does_not_break_its_first_message(
	monkeypatch,
	tmp_path,
) -> None:
	store = ConversationStore(tmp_path / "chat_history.sqlite3")
	empty = store.create_conversation("Empty draft")
	used = store.create_conversation("Used chat")
	store.append_exchange(
		used["id"],
		"My shoulder hurts.",
		"Where exactly?",
		[],
		False,
		"",
		0,
	)
	monkeypatch.setattr(routes, "get_conversation_store", lambda: store)
	monkeypatch.setattr(routes, "retrieve_guidelines", lambda *args, **kwargs: [])
	monkeypatch.setattr(
		routes,
		"generate_grounded_answer",
		lambda *args, **kwargs: "A grounded answer.",
	)

	response = send_request("GET", "/api/conversations")

	assert response.status_code == 200
	assert {conversation["id"] for conversation in response.json()} == {
		empty["id"],
		used["id"],
	}
	first_message = send_request(
		"POST",
		f"/api/conversations/{empty['id']}/messages",
		{"question": "Can I start this chat?"},
	)
	assert first_message.status_code == 200
	assert store.get_conversation(empty["id"])["messages"][0]["content"] == (
		"Can I start this chat?"
	)
	assert store.get_conversation(used["id"]) is not None


def test_chat_sources_are_shown_only_when_requested(monkeypatch, tmp_path) -> None:
	store = ConversationStore(tmp_path / "chat_history.sqlite3")
	monkeypatch.setattr(routes, "get_conversation_store", lambda: store)
	monkeypatch.setattr(
		routes,
		"retrieve_guidelines",
		lambda *args, **kwargs: [
			{
				"text": "Supporting text.",
				"source": "guide.pdf",
				"page": 2,
				"jurisdiction": "EG",
				"score": 0.8,
			}
		],
	)
	generation_options = []
	monkeypatch.setattr(
		routes,
		"generate_grounded_answer",
		lambda *args, **kwargs: generation_options.append(kwargs)
		or "Grounded answer.",
	)
	conversation = send_request("POST", "/api/conversations", {}).json()

	hidden = send_request(
		"POST",
		f"/api/conversations/{conversation['id']}/messages",
		{"question": "Question"},
	)
	shown = send_request(
		"POST",
		f"/api/conversations/{conversation['id']}/messages",
		{"question": "Question", "include_sources": True},
	)

	assert hidden.status_code == shown.status_code == 200
	assert hidden.json()["assistant_message"]["sources"] == []
	assert shown.json()["assistant_message"]["sources"][0]["source"] == "guide.pdf"
	assert generation_options[0]["include_sources"] is False
	assert generation_options[1]["include_sources"] is True


def test_conversation_can_be_deleted_and_missing_conversation_is_not_found(
	monkeypatch,
	tmp_path,
) -> None:
	store = ConversationStore(tmp_path / "chat_history.sqlite3")
	monkeypatch.setattr(routes, "get_conversation_store", lambda: store)
	conversation = send_request("POST", "/api/conversations", {}).json()

	deleted = send_request("DELETE", f"/api/conversations/{conversation['id']}")
	missing = send_request("GET", f"/api/conversations/{conversation['id']}")

	assert deleted.status_code == 204
	assert missing.status_code == 404


def test_editing_a_message_replaces_its_reply_and_discards_later_turns(
	monkeypatch,
	tmp_path,
) -> None:
	store = ConversationStore(tmp_path / "chat_history.sqlite3")
	monkeypatch.setattr(routes, "get_conversation_store", lambda: store)
	conversation = store.create_conversation("New chat")
	first_exchange = store.append_exchange(
		conversation["id"], "Old question", "Old answer", [], False, "", 0
	)
	store.append_exchange(
		conversation["id"], "Later question", "Later answer", [], False, "", 0
	)
	message_id = first_exchange["user_message"]["id"]
	retrieval_queries = []
	generation_calls = []
	monkeypatch.setattr(
		routes,
		"retrieve_guidelines",
		lambda query, **kwargs: retrieval_queries.append(query)
		or [
			{
				"text": "Relevant guideline passage.",
				"source": "guide.pdf",
				"page": 3,
				"jurisdiction": "EG",
				"score": 0.9,
			}
		],
	)
	monkeypatch.setattr(
		routes,
		"generate_grounded_answer",
		lambda question, passages, **kwargs: generation_calls.append(
			{"question": question, **kwargs}
		)
		or "New answer",
	)

	response = send_request(
		"POST",
		f"/api/conversations/{conversation['id']}/messages/{message_id}/edit",
		{"question": "Edited question"},
	)

	assert response.status_code == 200
	assert response.json()["user_message"]["content"] == "Edited question"
	assert response.json()["assistant_message"]["content"] == "New answer"
	assert response.json()["user_message"]["id"] == message_id
	assert "Old question" not in retrieval_queries[0]
	assert "Later question" not in retrieval_queries[0]
	assert generation_calls[0]["history"] == []
	persisted = store.get_conversation(conversation["id"])
	assert [message["content"] for message in persisted["messages"]] == [
		"Edited question",
		"New answer",
	]


def test_long_chat_summarizes_old_turns_before_reusing_context(
	monkeypatch,
	tmp_path,
) -> None:
	store = ConversationStore(tmp_path / "chat_history.sqlite3")
	monkeypatch.setattr(routes, "get_conversation_store", lambda: store)
	conversation = store.create_conversation("Long chat")
	for index in range(7):
		store.append_exchange(
			conversation["id"],
			f"User detail {index}",
			f"Assistant reply {index}",
			[],
			False,
			"",
			0,
		)
	summarized = []
	monkeypatch.setattr(
		routes,
		"summarize_conversation",
		lambda existing, older: summarized.append((existing, older))
		or "Earlier context summary.",
	)
	generation = []
	monkeypatch.setattr(
		routes,
		"retrieve_guidelines",
		lambda *args, **kwargs: [
			{
				"text": "Supporting passage.",
				"source": "guide.pdf",
				"page": 1,
				"jurisdiction": "EG",
				"score": 0.8,
			}
		],
	)
	monkeypatch.setattr(
		routes,
		"generate_grounded_answer",
		lambda question, passages, **kwargs: generation.append(kwargs)
		or "A grounded answer.",
	)

	response = send_request(
		"POST",
		f"/api/conversations/{conversation['id']}/messages",
		{"question": "A new question"},
	)

	assert response.status_code == 200
	assert summarized[0][0] == ""
	assert summarized[0][1] == [
		{"role": "user", "content": "User detail 0"},
		{"role": "assistant", "content": "Assistant reply 0"},
	]
	assert generation[0]["conversation_summary"] == "Earlier context summary."
	state = store.get_context_state(conversation["id"])
	assert state["summary"] == "Earlier context summary."
	assert state["summarized_through_message_id"] == 2


def test_root_serves_local_chat_interface() -> None:
	response = send_request("GET", "/")

	assert response.status_code == 200
	assert "text/html" in response.headers["content-type"]
	assert "Dexian Medical Doctor" in response.text
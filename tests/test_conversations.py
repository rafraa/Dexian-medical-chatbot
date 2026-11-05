from src.conversations.context import (
	MAX_RECENT_MESSAGES,
	build_retrieval_query,
	prepare_conversation_context,
)
from src.conversations.store import ConversationStore


def test_context_keeps_recent_messages_and_selects_older_messages_for_summary() -> None:
	messages = [
		{"id": index, "role": "user", "content": f"Message {index}"}
		for index in range(1, MAX_RECENT_MESSAGES + 4)
	]

	context = prepare_conversation_context(messages, "", 0)

	assert len(context["history"]) == MAX_RECENT_MESSAGES
	assert context["history"][0]["content"] == "Message 4"
	assert [message["content"] for message in context["older_messages"]] == [
		"Message 1",
		"Message 2",
		"Message 3",
	]
	assert context["summarized_through_message_id"] == 3


def test_retrieval_query_includes_only_the_supplied_conversation_context() -> None:
	query = build_retrieval_query(
		"What changed?",
		"Pain started yesterday.",
		[
			{"role": "user", "content": "My left shoulder hurts."},
			{"role": "assistant", "content": "Where is the pain?"},
		],
	)

	assert "Pain started yesterday." in query
	assert "My left shoulder hurts." in query
	assert "What changed?" in query


def test_conversation_store_persists_messages_and_cascades_deletion(tmp_path) -> None:
	path = tmp_path / "nested" / "chats.sqlite3"
	store = ConversationStore(path)
	conversation = store.create_conversation()
	store.append_exchange(
		conversation["id"],
		"My shoulder hurts.",
		"Where exactly?",
		[],
		False,
		"",
		0,
	)

	reopened = ConversationStore(path).get_conversation(conversation["id"])
	assert reopened is not None
	assert reopened["title"] == "My shoulder hurts."
	assert [message["role"] for message in reopened["messages"]] == [
		"user",
		"assistant",
	]
	assert ConversationStore(path).delete_conversation(conversation["id"])
	assert ConversationStore(path).get_conversation(conversation["id"]) is None

from typing import Any


MAX_RECENT_MESSAGES = 12


def prepare_conversation_context(
	messages: list[dict[str, Any]],
	summary: str,
	summarized_through_message_id: int,
) -> dict[str, Any]:
	"""Keep recent turns verbatim and identify older turns needing a summary."""
	recent_messages = messages[-MAX_RECENT_MESSAGES:]
	cutoff_message_id = (
		recent_messages[0]["id"] - 1 if recent_messages else summarized_through_message_id
	)
	older_messages = [
		{"role": message["role"], "content": message["content"]}
		for message in messages
		if summarized_through_message_id < message["id"] <= cutoff_message_id
	]
	return {
		"summary": summary,
		"history": [
			{"role": message["role"], "content": message["content"]}
			for message in recent_messages
		],
		"older_messages": older_messages,
		"summarized_through_message_id": (
			cutoff_message_id if older_messages else summarized_through_message_id
		),
	}


def build_retrieval_query(
	question: str,
	summary: str,
	history: list[dict[str, str]],
) -> str:
	"""Include bounded same-thread context when searching for relevant passages."""
	parts = [f"Current question: {question}"]
	if summary:
		parts.insert(0, f"Earlier conversation context: {summary}")
	recent_user_details = [
		message["content"]
		for message in history[-6:]
		if message["role"] == "user"
	]
	if recent_user_details:
		parts.insert(0, "Recent details from this conversation: " + "\n".join(recent_user_details))
	return "\n\n".join(parts)

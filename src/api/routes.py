from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

from config.settings import CHAT_DB_PATH
from src.api.schemas import (
	AnswerResponse,
	ConversationDetail,
	ConversationMessage,
	ConversationMessageRequest,
	ConversationSummary,
	ConversationTurnResponse,
	CreateConversationRequest,
	QuestionRequest,
	SourceCitation,
)
from src.conversations.context import build_retrieval_query, prepare_conversation_context
from src.conversations.store import ConversationStore
from src.rag.generator import generate_grounded_answer, summarize_conversation
from src.rag.retriever import retrieve_guidelines


router = APIRouter(prefix="/api")


def get_conversation_store() -> ConversationStore:
	return ConversationStore(CHAT_DB_PATH)


@router.post("/ask", response_model=AnswerResponse)
def ask_question(request: QuestionRequest) -> AnswerResponse:
	if not request.question.strip():
		raise HTTPException(status_code=422, detail="Question must not be blank.")

	passages = retrieve_guidelines(
		request.question.strip(),
		limit=request.limit,
	)
	sources = [
		SourceCitation(id=f"S{index}", **passage)
		for index, passage in enumerate(passages, start=1)
	]
	if not passages:
		return AnswerResponse(
			answer=(
				"No relevant indexed medical-reference passages were found, so I can't provide "
				"a source-grounded answer."
			),
			sources=[],
		)

	answer = generate_grounded_answer(
		request.question.strip(),
		passages,
		include_sources=True,
	)
	return AnswerResponse(answer=answer, sources=sources)


@router.post(
	"/conversations",
	response_model=ConversationSummary,
	status_code=status.HTTP_201_CREATED,
)
def create_conversation(
	request: CreateConversationRequest,
) -> ConversationSummary:
	conversation = get_conversation_store().create_conversation(request.title)
	return ConversationSummary(**conversation)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations() -> list[ConversationSummary]:
	store = get_conversation_store()
	return [
		ConversationSummary(**conversation)
		for conversation in store.list_conversations()
	]


@router.get(
	"/conversations/{conversation_id}",
	response_model=ConversationDetail,
)
def read_conversation(conversation_id: str) -> ConversationDetail:
	conversation = get_conversation_store().get_conversation(conversation_id)
	if conversation is None:
		raise HTTPException(status_code=404, detail="Conversation not found.")
	return ConversationDetail(
		id=conversation["id"],
		title=conversation["title"],
		created_at=conversation["created_at"],
		updated_at=conversation["updated_at"],
		messages=conversation["messages"],
	)


@router.delete(
	"/conversations/{conversation_id}",
	status_code=status.HTTP_204_NO_CONTENT,
)
def remove_conversation(conversation_id: str) -> Response:
	if not get_conversation_store().delete_conversation(conversation_id):
		raise HTTPException(status_code=404, detail="Conversation not found.")
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
	"/conversations/{conversation_id}/messages",
	response_model=ConversationTurnResponse,
)
def send_conversation_message(
	conversation_id: str,
	request: ConversationMessageRequest,
) -> ConversationTurnResponse:
	store = get_conversation_store()
	state = store.get_context_state(conversation_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Conversation not found.")

	question = request.question.strip()
	context = prepare_conversation_context(
		state["messages"],
		state["summary"],
		state["summarized_through_message_id"],
	)
	summary = context["summary"]
	if context["older_messages"]:
		summary = summarize_conversation(summary, context["older_messages"])

	retrieval_query = build_retrieval_query(
		question,
		summary,
		context["history"],
	)
	passages = retrieve_guidelines(
		retrieval_query,
		limit=request.limit,
	)
	sources = [
		SourceCitation(id=f"S{index}", **passage)
		for index, passage in enumerate(passages, start=1)
	]
	if passages:
		answer = generate_grounded_answer(
			question,
			passages,
			history=context["history"],
			conversation_summary=summary,
			include_sources=request.include_sources,
		)
	else:
		answer = (
			"I couldn't find a relevant passage in the indexed medical references, so I can't "
			"give a source-grounded answer. Could you add a little more detail?"
		)

	try:
		messages: dict[str, dict[str, Any]] = store.append_exchange(
			conversation_id=conversation_id,
			question=question,
			answer=answer,
			sources=[source.model_dump() for source in sources],
			sources_visible=request.include_sources,
			context_summary=summary,
			summarized_through_message_id=context[
				"summarized_through_message_id"
			],
		)
	except KeyError as exc:
		raise HTTPException(status_code=404, detail="Conversation not found.") from exc

	if not request.include_sources:
		messages["assistant_message"]["sources"] = []
	updated = store.get_conversation(conversation_id)
	if updated is None:
		raise HTTPException(status_code=404, detail="Conversation not found.")
	return ConversationTurnResponse(
		conversation=ConversationSummary(
			id=updated["id"],
			title=updated["title"],
			created_at=updated["created_at"],
			updated_at=updated["updated_at"],
		),
		user_message=ConversationMessage(**messages["user_message"]),
		assistant_message=ConversationMessage(**messages["assistant_message"]),
	)


@router.post(
	"/conversations/{conversation_id}/messages/{message_id}/edit",
	response_model=ConversationTurnResponse,
)
def edit_conversation_message(
	conversation_id: str,
	message_id: int,
	request: ConversationMessageRequest,
) -> ConversationTurnResponse:
	store = get_conversation_store()
	state = store.get_context_state(conversation_id)
	if state is None:
		raise HTTPException(status_code=404, detail="Conversation not found.")

	target = next(
		(message for message in state["messages"] if message["id"] == message_id),
		None,
	)
	if target is None or target["role"] != "user":
		raise HTTPException(status_code=404, detail="User message not found.")

	question = request.question.strip()
	if not question:
		raise HTTPException(status_code=422, detail="Question must not be blank.")
	previous_messages = [
		message for message in state["messages"] if message["id"] < message_id
	]
	context = prepare_conversation_context(previous_messages, "", 0)
	summary = context["summary"]
	if context["older_messages"]:
		summary = summarize_conversation(summary, context["older_messages"])

	retrieval_query = build_retrieval_query(
		question,
		summary,
		context["history"],
	)
	passages = retrieve_guidelines(
		retrieval_query,
		limit=request.limit,
	)
	sources = [
		SourceCitation(id=f"S{index}", **passage)
		for index, passage in enumerate(passages, start=1)
	]
	if passages:
		answer = generate_grounded_answer(
			question,
			passages,
			history=context["history"],
			conversation_summary=summary,
			include_sources=request.include_sources,
		)
	else:
		answer = (
			"I couldn't find a relevant passage in the indexed medical references, so I can't "
			"give a source-grounded answer. Could you add a little more detail?"
		)

	try:
		messages = store.replace_exchange(
			conversation_id=conversation_id,
			message_id=message_id,
			question=question,
			answer=answer,
			sources=[source.model_dump() for source in sources],
			sources_visible=request.include_sources,
			context_summary=summary,
			summarized_through_message_id=context[
				"summarized_through_message_id"
			],
		)
	except KeyError as exc:
		raise HTTPException(status_code=404, detail="User message not found.") from exc

	if not request.include_sources:
		messages["assistant_message"]["sources"] = []
	updated = store.get_conversation(conversation_id)
	if updated is None:
		raise HTTPException(status_code=404, detail="Conversation not found.")
	return ConversationTurnResponse(
		conversation=ConversationSummary(
			id=updated["id"],
			title=updated["title"],
			created_at=updated["created_at"],
			updated_at=updated["updated_at"],
		),
		user_message=ConversationMessage(**messages["user_message"]),
		assistant_message=ConversationMessage(**messages["assistant_message"]),
	)
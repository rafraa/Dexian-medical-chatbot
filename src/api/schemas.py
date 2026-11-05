from typing import Literal

from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
	question: str = Field(min_length=1, max_length=2000)
	limit: int = Field(default=5, ge=1, le=10)


class SourceCitation(BaseModel):
	id: str
	text: str
	source: str
	page: int
	jurisdiction: str
	score: float
	title: str | None = None
	publisher: str | None = None
	publication_year: str | None = None
	document_type: str | None = None
	source_type: str | None = None
	guideline_status: str | None = None


class AnswerResponse(BaseModel):
	answer: str
	sources: list[SourceCitation]


class CreateConversationRequest(BaseModel):
	title: str = Field(default="New chat", min_length=1, max_length=120)


class ConversationSummary(BaseModel):
	id: str
	title: str
	created_at: str
	updated_at: str


class ConversationMessageRequest(BaseModel):
	question: str = Field(min_length=1, max_length=2000)
	limit: int = Field(default=5, ge=1, le=10)
	include_sources: bool = False


class ConversationMessage(BaseModel):
	id: int
	role: Literal["user", "assistant"]
	content: str
	sources: list[SourceCitation] = Field(default_factory=list)
	created_at: str


class ConversationDetail(ConversationSummary):
	messages: list[ConversationMessage]


class ConversationTurnResponse(BaseModel):
	conversation: ConversationSummary
	user_message: ConversationMessage
	assistant_message: ConversationMessage
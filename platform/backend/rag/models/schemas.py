from typing import Any
from pydantic import BaseModel


class ChatRequest(BaseModel):
    conversation_id: int | None = None
    external_user_id: str
    session_id: str
    question: str
    filters: dict[str, Any] | None = None


class IngestRequest(BaseModel):
    root_path: str = "."


class ReindexRequest(BaseModel):
    root_path: str = "."
    reset_conversations: bool = False


class FeedbackRequest(BaseModel):
    message_id: int
    rating: int
    comment: str | None = None
    external_user_id: str | None = None

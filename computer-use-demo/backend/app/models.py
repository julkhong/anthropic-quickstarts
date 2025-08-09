from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MessageBlock(BaseModel):
    type: Literal["text", "tool_use", "tool_result", "thinking"]
    text: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    tool_use_id: str | None = None
    is_error: bool | None = None


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "tool"]
    content: list[MessageBlock] | str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SessionCreateRequest(BaseModel):
    model: str = Field(default="claude-sonnet-4-20250514")
    tool_version: Literal[
        "computer_use_20241022", "computer_use_20250124"
    ] = "computer_use_20250124"
    system_prompt_suffix: str = ""


class Session(BaseModel):
    id: str
    model: str
    tool_version: str
    system_prompt_suffix: str
    created_at: datetime
    updated_at: datetime


class SendMessageRequest(BaseModel):
    content: str


class SessionSummary(BaseModel):
    id: str
    model: str
    created_at: datetime
    updated_at: datetime



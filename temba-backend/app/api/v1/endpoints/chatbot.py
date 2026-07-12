"""
Chatbot API endpoint — Temba Water AI Assistant.
POST /api/v1/chatbot/chat
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.chatbot.chatbot_service import chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    action: dict[str, Any] | None = None
    language: str = "en"


@router.post("/chat", response_model=ChatResponse)
async def chatbot_chat(request: Request, body: ChatRequest):
    """
    Send a message to the Temba Water AI Assistant.

    Supports full conversation history for multi-turn dialogue.
    Returns the assistant's reply plus an optional platform action to trigger
    (file_report, book_appointment, request_service).
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Determine API base for provider lookup
    base_url = str(request.base_url).rstrip("/")

    try:
        result = await chat(
            message=body.message.strip(),
            history=[m.model_dump() for m in body.history],
            api_base=base_url,
        )
        return ChatResponse(**result)

    except ValueError as exc:
        # ANTHROPIC_API_KEY not set
        logger.error("Chatbot config error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="AI assistant is not configured. Please contact support.",
        )
    except Exception as exc:
        logger.exception("Chatbot error for message: %r", body.message[:100])
        raise HTTPException(
            status_code=500,
            detail="The AI assistant encountered an error. Please try again.",
        )

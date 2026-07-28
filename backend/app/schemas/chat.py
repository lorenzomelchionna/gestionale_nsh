from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat import MessageDirection, MessageStatus


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    direction: MessageDirection
    body: str
    status: MessageStatus
    error: Optional[str] = None
    sent_by_user_id: Optional[int] = None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    client_id: Optional[int] = None
    contact_name: Optional[str] = None
    last_message_at: Optional[datetime] = None
    last_inbound_at: Optional[datetime] = None
    unread_count: int
    is_archived: bool

    # Resolved for display; the client record wins over the WhatsApp profile name.
    display_name: str = ""
    last_message_preview: Optional[str] = None
    # Meta's customer service window: free text is only allowed while open.
    can_reply_freely: bool = False
    window_expires_at: Optional[datetime] = None


class ConversationDetail(ConversationOut):
    messages: List[ChatMessageOut] = []


class ReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)

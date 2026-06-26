from pydantic import BaseModel
from datetime import datetime


class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    id: int
    contract_id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

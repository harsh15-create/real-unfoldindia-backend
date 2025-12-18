from pydantic import BaseModel, Field
from typing import Optional, List

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., description="Conversation history")

class ChatResponse(BaseModel):
    reply: str = Field(..., description="AI's response text")
    status: str = Field("success", description="Response status")

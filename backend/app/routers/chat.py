from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.groq_service import get_groq_response

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Chat endpoint for Travel AI.
    Accepts a message and returns an AI-generated response.
    """
    response = await get_groq_response(request.messages)
    return response

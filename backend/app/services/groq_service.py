import httpx
from app.core.config import get_settings
from app.schemas.chat import ChatResponse

settings = get_settings()

SYSTEM_PROMPT = """Role: Kira, expert Indian Travel Guide for 'Unfold India'.

GUIDELINES (Pro Guide Persona):
1. **ACCURACY FIRST**: Use real names, correct locations, and actual prices (in INR).
2. **BE A GUIDE, NOT A ROBOT**:
   - **General Chat**: **ULTRA-CONCISE** (Max 60 words).
   - Structure: **Direct Answer** (1-2 sentences) + **ONE Pro Tip**.
   - **BANNED HEADERS**: NO "Additional Insights", "Overview", "Security", "Opening Hours" (unless asked).
   - **NO UNPROMPTED ITINERARIES**: Do NOT generate day-wise plans unless explicitly asked.
3. **STRUCTURED UI**:
   - Use **Bold** for key terms.
   - Use Bullet Points for lists.
4. **ITINERARIES (EXCEPTION)**: 
   - **IGNORE ALL LENGTH LIMITS** ONLY when asked for an "Itinerary" or "Plan".
   - Create the **BEST, MOST DETAILED** itinerary possible.
   - Structure: **Morning** (Activity + Location) | **Lunch** (Specific Restaurant + Dish) | **Afternoon** (Hidden Gems) | **Evening** (Vibe).
5. **SCOPE**: Strict India Focus. Polities redirect others.
6. **Emoji Use**: Minimal & Tasteful (🇮🇳, ✨, 🍛).

Example Output (General Chat):
**Early Morning is perfect!** cleaner air and no crowds.
**Pro Tip**: The lighting is best at 6 AM for photos. Grab chai at a nearby stall! ☕"""

from typing import List, Dict
from app.schemas.chat import ChatResponse, Message

async def get_groq_response(messages: List[Message]) -> ChatResponse:
    if not settings.GROQ_API_KEY:
        return ChatResponse(reply="Server Config Error: Groq API Key missing.", status="error")

    api_url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # Convert Pydantic models to dict
    # OPTIMIZATION: Keep only last 6 messages to save input tokens (User constraint: 6k/min)
    conversation = [{"role": m.role, "content": m.content} for m in messages[-6:]]
    
    # Prepend System Prompt
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": full_messages,
        "temperature": 0.7,
        "max_tokens": 4096 
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(api_url, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return ChatResponse(reply=content)
        except httpx.HTTPStatusError as e:
            return ChatResponse(reply=f"API Error: {e.response.status_code}", status="error")
        except Exception as e:
            return ChatResponse(reply=f"Connection Error: {str(e)}", status="error")

"""FastAPI application for the Governor Chatbot Service."""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import create_jwt, verify_jwt, verify_payload
from .config import settings
from .context import get_system_prompt, refresh_system_prompt
from .governor_registry import refresh_cache as refresh_governor_cache, load_governors
from .kimi_client import KimiClient, KimiClientError, get_tool_schemas

app = FastAPI(
    title="TrueSight DAO Governor Chatbot",
    description="Conversational AI interface for DAO governors with full workspace context.",
    version="0.1.0",
)

# CORS — restrict to DApp origin in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store (replace with Redis in production)
_sessions: dict[str, list[dict[str, str]]] = {}


@app.get("/health")
async def health():
    gov_data = load_governors()
    return {
        "status": "ok",
        "version": "0.1.0",
        "governors_count": len(gov_data.get("governors", [])),
        "governors_updated_at": gov_data.get("updated_at", ""),
        "governors_source": gov_data.get("source", ""),
    }


@app.post("/auth/challenge")
async def auth_challenge(request: Request) -> JSONResponse:
    """Step 1: client sends signed payload; server verifies and returns JWT."""
    body = await request.json()
    payload = body.get("payload")
    signature = body.get("signature")
    public_key = request.headers.get("X-Public-Key", "")

    if not payload or not signature or not public_key:
        raise HTTPException(status_code=400, detail="payload, signature, and X-Public-Key required.")

    verify_payload(payload, signature, public_key)
    token = create_jwt(public_key)

    response = JSONResponse({"token": token, "expires_in": settings.jwt_expiry_minutes * 60})
    response.set_cookie(
        key="governor_chat_session",
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=settings.jwt_expiry_minutes * 60,
    )
    return response


@app.post("/chat")
async def chat(request: Request) -> JSONResponse:
    """Main chat endpoint. Receives signed message or JWT-authenticated message."""
    body = await request.json()
    payload = body.get("payload")
    signature = body.get("signature")
    public_key = request.headers.get("X-Public-Key", "")

    # Auth path A: signed payload (every message)
    if payload and signature and public_key:
        verify_payload(payload, signature, public_key)
        user_message = payload.get("message", "")
    else:
        # Auth path B: JWT session
        public_key = verify_jwt(request)
        # For JWT path, message is in a simpler wrapper
        user_message = body.get("message", "")
        if not user_message:
            raise HTTPException(status_code=400, detail="message is required.")

    # Session history
    session_id = public_key
    history = _sessions.get(session_id, [])
    history.append({"role": "user", "content": user_message})

    # Call Kimi
    system_prompt = get_system_prompt()
    client = KimiClient()

    try:
        # Phase 1: no tools. Phase 2: pass tools=get_tool_schemas()
        completion = client.chat(system_prompt, history)
        assistant_text = client.extract_response_text(completion)
    except KimiClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # Parse embedded proposal JSON if present
    proposal = None
    try:
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", assistant_text, re.DOTALL)
        if json_match:
            embedded = json.loads(json_match.group(1))
            if "proposal" in embedded:
                proposal = embedded["proposal"]
                # Strip the JSON block from display text
                assistant_text = re.sub(r"```json\s*\{.*?\}\s*```", "", assistant_text, flags=re.DOTALL).strip()
    except Exception:
        pass

    history.append({"role": "assistant", "content": assistant_text})
    _sessions[session_id] = history

    response_data: dict[str, Any] = {"response": assistant_text}
    if proposal:
        response_data["proposal"] = proposal

    return JSONResponse(response_data)


@app.post("/refresh-context")
async def refresh_context(request: Request) -> JSONResponse:
    """Admin endpoint to rebuild the system prompt cache."""
    verify_jwt(request)
    new_prompt = refresh_system_prompt()
    return JSONResponse({
        "status": "refreshed",
        "prompt_length": len(new_prompt),
    })


@app.get("/governors")
async def list_governors(request: Request) -> JSONResponse:
    """List registered governors (public keys redacted for security)."""
    verify_jwt(request)
    data = load_governors()
    governors = data.get("governors", [])
    return JSONResponse({
        "count": len(governors),
        "updated_at": data.get("updated_at", ""),
        "source": data.get("source", ""),
        "governors": [
            {"name": g.get("name"), "email": g.get("email"), "status": g.get("status")}
            for g in governors
        ],
    })


@app.post("/governors/refresh")
async def force_refresh_governors(request: Request) -> JSONResponse:
    """Force a fresh fetch of governors.json from GitHub."""
    verify_jwt(request)
    data = refresh_governor_cache()
    return JSONResponse({
        "status": "refreshed",
        "count": len(data.get("governors", [])),
        "updated_at": data.get("updated_at", ""),
    })


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)

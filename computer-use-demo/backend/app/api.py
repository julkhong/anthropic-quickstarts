from __future__ import annotations

import os
import uuid
from datetime import datetime
import asyncio
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from computer_use_demo.tools import ToolVersion

from .agent_runner import AgentSession
from .db import create_session, get_messages, get_session, list_sessions, init_engine
from .models import (
    ChatMessage,
    SendMessageRequest,
    Session,
    SessionCreateRequest,
    SessionSummary,
)


def get_api_key() -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return api_key


app = FastAPI(title="Computer Use Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory sessions runtime map (id -> AgentSession). Persistence is in SQLite.
SESSIONS: dict[str, AgentSession] = {}


@app.on_event("startup")
async def on_startup():
    await init_engine()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/sessions", response_model=Session)
async def create_new_session(body: SessionCreateRequest, api_key: Annotated[str, Depends(get_api_key)]):
    session_id = str(uuid.uuid4())
    await create_session(session_id, body.model, body.tool_version, body.system_prompt_suffix)

    runner = AgentSession(
        session_id=session_id,
        model=body.model,
        tool_version=body.tool_version,  # type: ignore[arg-type]
        api_key=api_key,
        system_prompt_suffix=body.system_prompt_suffix,
    )
    SESSIONS[session_id] = runner
    row = await get_session(session_id)
    if not row:
        raise HTTPException(500, "Session creation failed")
    return Session(
        id=row["id"],
        model=row["model"],
        tool_version=row["tool_version"],
        system_prompt_suffix=row["system_prompt_suffix"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@app.get("/sessions", response_model=list[SessionSummary])
async def list_all_sessions():
    rows = await list_sessions()
    return [
        SessionSummary(
            id=row["id"],
            model=row["model"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@app.get("/sessions/{session_id}", response_model=Session)
async def get_session_by_id(session_id: str):
    row = await get_session(session_id)
    if not row:
        raise HTTPException(404, "Session not found")
    return Session(
        id=row["id"],
        model=row["model"],
        tool_version=row["tool_version"],
        system_prompt_suffix=row["system_prompt_suffix"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@app.get("/sessions/{session_id}/messages", response_model=list[ChatMessage])
async def get_session_messages(session_id: str):
    rows = await get_messages(session_id)
    return [
        ChatMessage(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@app.get("/sessions/{session_id}/events")
async def session_events(session_id: str, request: Request):
    runner = SESSIONS.get(session_id)
    if not runner:
        raise HTTPException(404, "Session not active")

    async def event_stream():
        async for payload in runner.sse_iter():
            # Client disconnect handling
            if await request.is_disconnected():
                break
            yield payload

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: SendMessageRequest):
    runner = SESSIONS.get(session_id)
    if not runner:
        raise HTTPException(404, "Session not active")
    await runner.add_user_message(body.content)
    # Kick off one assistant turn, do not block the request
    asyncio.create_task(runner.run_once())
    return JSONResponse({"status": "queued"})


# Minimal static test page (no frameworks)
@app.get("/test", response_class=HTMLResponse)
def test_page():
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Computer Use Backend Test</title>
    <style>
      body { font-family: -apple-system, system-ui, sans-serif; margin: 2rem; }
      pre { background: #111; color: #eee; padding: 1rem; border-radius: 8px; height: 240px; overflow: auto; }
    </style>
  </head>
  <body>
    <button id="new">New Session</button>
    <input id="msg" placeholder="Type message" style="width: 300px;"/>
    <button id="send">Send</button>
    <div><code id="sid"></code></div>
    <pre id="log"></pre>
    <script>
      const log = (x) => { const el = document.getElementById('log'); el.textContent += x + "\n"; el.scrollTop = el.scrollHeight; };
      let sessionId = null;
      let evtSource = null;
      document.getElementById('new').onclick = async () => {
        const res = await fetch('/sessions', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({})});
        const ses = await res.json();
        sessionId = ses.id; document.getElementById('sid').textContent = 'Session: ' + sessionId;
        if (evtSource) evtSource.close();
        evtSource = new EventSource(`/sessions/${sessionId}/events`);
        evtSource.addEventListener('message', ev => log(`[message] ${ev.data}`));
        evtSource.addEventListener('assistant_chunk', ev => log(`[assistant_chunk] ${ev.data}`));
        evtSource.addEventListener('http_exchange', ev => log(`[http] ${ev.data}`));
      };
      document.getElementById('send').onclick = async () => {
        if (!sessionId) return;
        const content = document.getElementById('msg').value;
        await fetch(`/sessions/${sessionId}/messages`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({content})});
      };
    </script>
  </body>
</html>
    """



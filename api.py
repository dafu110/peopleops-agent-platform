from typing import List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.auth import Principal, allowed_permissions, authenticate_with_password, require_permission
from core.config import get_settings
from core.database import init_db, list_interview_actions
from core.workflow import agent_app


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.2.0")


class ChatRequest(BaseModel):
    message: str
    jd_text: str = ""
    resume_text: str = ""
    history: List[dict] = Field(default_factory=list)
    thread_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    intent: str
    thread_id: str


def current_principal(x_access_password: Optional[str] = Header(default=None)) -> Principal:
    if not settings.access_password:
        return Principal(username="local-admin", role="admin")
    principal = authenticate_with_password(x_access_password or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid access password")
    return principal


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "tool_execution_mode": settings.tool_execution_mode,
        "db_path": str(settings.db_path),
    }


@app.get("/me")
def me(principal: Principal = Depends(current_principal)) -> dict:
    return {
        "username": principal.username,
        "role": principal.role,
        "permissions": list(allowed_permissions(principal.role)),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, principal: Principal = Depends(current_principal)) -> ChatResponse:
    require_permission(principal, "chat")
    thread_id = request.thread_id or f"api_session_{uuid4().hex[:8]}"
    inputs = {
        "input_text": request.message,
        "resume_text": request.resume_text,
        "jd_text": request.jd_text,
        "intent": "",
        "reply": "",
        "history": request.history,
    }
    output = agent_app.invoke(inputs, {"configurable": {"thread_id": thread_id}})
    return ChatResponse(
        reply=output.get("reply", ""),
        intent=output.get("intent", ""),
        thread_id=thread_id,
    )


@app.get("/interviews")
def interviews(
    limit: int = 20,
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    require_permission(principal, "tool")
    return list_interview_actions(limit=limit)

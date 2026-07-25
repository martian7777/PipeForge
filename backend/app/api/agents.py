"""Agentic AI endpoints: sessions (advise/chat), the decision trace, and per-agent
model config. Copilot/autopilot modes are added in later phases.

All routes require ``current_user`` and are per-user isolated. Agent runs are gated
behind a configured provider (``PIPEFORGE_LLM_PROVIDER``); when off, the classic
pipeline is unaffected and these endpoints report 503.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents import providers
from ..agents import session as agent_session
from ..agents.providers import AGENT_LABELS, ROLE_BY_AGENT, ProviderError
from ..db import get_db
from ..models import AgentConfig, AgentSession, Dataset, Run, User
from ..ratelimit import limiter
from ..schemas import (
    AgentConfigItem,
    AgentConfigOut,
    AgentConfigUpdate,
    AgentMessageOut,
    AgentSessionCreate,
    AgentSessionDetail,
    ChatMessageIn,
)
from ..security import current_user

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _require_enabled() -> None:
    if not providers.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="The agent layer is disabled. Configure PIPEFORGE_LLM_PROVIDER.",
        )


def _owned_run(db: Session, run_id: int, user: User) -> Run:
    run = db.get(Run, run_id)
    ds = db.get(Dataset, run.dataset_id) if run else None
    if run is None or ds is None or ds.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _owned_dataset(db: Session, dataset_id: int, user: User) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None or ds.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


def _owned_session(db: Session, session_id: int, user: User) -> AgentSession:
    s = db.get(AgentSession, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent session not found")
    return s


@router.post("/sessions", response_model=AgentSessionDetail, status_code=201)
async def create_session(
    body: AgentSessionCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> AgentSession:
    _require_enabled()
    run_id = body.run_id
    dataset_id = body.dataset_id
    if run_id is not None:
        run = _owned_run(db, run_id, user)
        dataset_id = run.dataset_id
    else:
        _owned_dataset(db, dataset_id, user)

    session = AgentSession(
        user_id=user.id, run_id=run_id, dataset_id=dataset_id, mode=body.mode.value, status="running"
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if body.mode.value == "advise":
        try:
            await agent_session.run_advise(db, session)
        except ProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif body.mode.value == "chat":
        session.status = "done"  # ready for messages
        db.commit()
    else:
        # copilot / autopilot land in Phases 2 & 3.
        raise HTTPException(status_code=501, detail=f"Mode '{body.mode.value}' is not available yet")

    db.refresh(session)
    return session


@router.get("/sessions/{session_id}", response_model=AgentSessionDetail)
def get_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> AgentSession:
    return _owned_session(db, session_id, user)


@router.post("/sessions/{session_id}/messages", response_model=list[AgentMessageOut])
@limiter.limit("30/minute")
async def send_message(
    request: Request,
    session_id: int,
    body: ChatMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list:
    _require_enabled()
    session = _owned_session(db, session_id, user)
    if session.mode != "chat":
        raise HTTPException(status_code=409, detail="This session is not a chat session")
    try:
        await agent_session.run_chat_turn(db, session, body.content)
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - already recorded on the session; report it
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}") from exc
    db.refresh(session)
    return list(session.messages)


@router.get("/config", response_model=AgentConfigOut)
def get_config(db: Session = Depends(get_db), user: User = Depends(current_user)) -> AgentConfigOut:
    overrides = {
        c.agent_name: c
        for c in db.scalars(select(AgentConfig).where(AgentConfig.user_id == user.id))
    }
    items: list[AgentConfigItem] = []
    for name in ROLE_BY_AGENT:
        o = overrides.get(name)
        items.append(
            AgentConfigItem(
                agent_name=name,
                label=AGENT_LABELS.get(name, name),
                provider=(o.provider if o else None),
                model=(o.model if o else None),
                enabled=(o.enabled if o else True),
                max_steps=(o.max_steps if o else None),
            )
        )
    from ..config import settings

    return AgentConfigOut(
        provider=settings.llm_provider,
        enabled=providers.is_enabled(),
        available_models=providers.available_models(),
        agents=items,
    )


@router.put("/config", response_model=AgentConfigOut)
def update_config(
    body: AgentConfigUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> AgentConfigOut:
    valid = set(ROLE_BY_AGENT)
    for item in body.agents:
        if item.agent_name not in valid:
            raise HTTPException(status_code=422, detail=f"Unknown agent: {item.agent_name}")
        cfg = (
            db.query(AgentConfig)
            .filter(AgentConfig.user_id == user.id, AgentConfig.agent_name == item.agent_name)
            .one_or_none()
        )
        if cfg is None:
            cfg = AgentConfig(user_id=user.id, agent_name=item.agent_name)
            db.add(cfg)
        cfg.provider = item.provider
        cfg.model = item.model
        cfg.enabled = item.enabled
        cfg.max_steps = item.max_steps
    db.commit()
    return get_config(db=db, user=user)

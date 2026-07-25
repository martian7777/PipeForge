"""Session lifecycle: run an agent, persist the decision trace, surface errors.

Phase 1 covers the two read-only modes:
- ``run_advise``  — the EDA Analyst produces an ``EdaNarrative`` attached to the run.
- ``run_chat_turn`` — one conversational turn over the run's data and results.

Each model turn and tool call is written as an ``AgentMessage`` so the frontend timeline
and the live agent board can render from the DB. Later phases add copilot park/resume and
the autopilot orchestrator here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import AgentMessage, AgentSession, Dataset, Run, User
from . import providers
from .deps import AgentDeps
from .specialists import build_chat_agent, build_eda_analyst


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _add_message(db: Session, session: AgentSession, **kw: Any) -> AgentMessage:
    msg = AgentMessage(session_id=session.id, **kw)
    db.add(msg)
    db.commit()
    return msg


def _record_tool_steps(db: Session, session: AgentSession, agent_name: str, result: Any) -> None:
    """Best-effort extraction of tool calls from a PydanticAI result into the trace."""
    try:
        messages = result.all_messages()
    except Exception:  # noqa: BLE001 - version-tolerant; the final answer is recorded regardless
        return
    for m in messages:
        for part in getattr(m, "parts", []) or []:
            if getattr(part, "part_kind", "") == "tool-call":
                _add_message(
                    db,
                    session,
                    role="tool",
                    agent_name=agent_name,
                    tool_name=getattr(part, "tool_name", None),
                    status="done",
                )


def _deps(db: Session, session: AgentSession) -> AgentDeps:
    user = db.get(User, session.user_id)
    run = db.get(Run, session.run_id) if session.run_id else None
    dataset = None
    if run is not None:
        dataset = db.get(Dataset, run.dataset_id)
    elif session.dataset_id:
        dataset = db.get(Dataset, session.dataset_id)
    if dataset is None:
        raise ValueError("Agent session has no resolvable dataset")
    return AgentDeps(db=db, user=user, dataset=dataset, run=run)


async def run_advise(db: Session, session: AgentSession) -> None:
    """Run the EDA Analyst and store its narrative. Sets session status done/error."""
    session.current_agent = "eda_analyst"
    session.status = "running"
    db.commit()
    try:
        deps = _deps(db, session)
        model = providers.get_model("eda_analyst", deps.user, db)
        agent = build_eda_analyst(model)
        result = await agent.run(
            "Analyse this dataset and its EDA. Report insights, risks, and hypotheses.",
            deps=deps,
        )
        _record_tool_steps(db, session, "eda_analyst", result)
        _add_message(
            db,
            session,
            role="assistant",
            agent_name="eda_analyst",
            content=result.output.summary,
            tool_result_json=result.output.model_dump(),
        )
        session.status = "done"
        session.current_agent = None
        db.commit()
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI, don't crash
        _fail(db, session, "eda_analyst", exc)


async def run_chat_turn(db: Session, session: AgentSession, user_message: str) -> str:
    """Append a user turn, run the chat agent, store and return the reply."""
    _add_message(db, session, role="user", content=user_message)
    session.current_agent = "chat"
    session.status = "running"
    db.commit()
    try:
        deps = _deps(db, session)
        model = providers.get_model("chat", deps.user, db)
        agent = build_chat_agent(model)

        # Version-proof memory: replay prior turns as a short preamble.
        prior = [
            m
            for m in session.messages
            if m.role in ("user", "assistant") and m.content and m.id != session.messages[-1].id
        ]
        history = "\n".join(f"{m.role}: {m.content}" for m in prior[-10:])
        prompt = f"Conversation so far:\n{history}\n\nUser: {user_message}" if history else user_message

        result = await agent.run(prompt, deps=deps)
        _record_tool_steps(db, session, "chat", result)
        reply = result.output
        _add_message(db, session, role="assistant", agent_name="chat", content=reply)
        session.status = "done"
        session.current_agent = None
        db.commit()
        return reply
    except Exception as exc:  # noqa: BLE001
        _fail(db, session, "chat", exc)
        raise


def _fail(db: Session, session: AgentSession, agent_name: str, exc: Exception) -> None:
    db.rollback()
    session.status = "error"
    session.current_agent = None
    session.error_json = {"agent": agent_name, "message": str(exc)}
    db.add(AgentMessage(session_id=session.id, role="error", agent_name=agent_name, content=str(exc), status="error"))
    db.commit()

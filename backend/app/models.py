from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4
from sqlalchemy import Column, JSON, String
from sqlmodel import Field, SQLModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class CaseStatus(str, Enum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    WAITING = "WAITING"
    NEEDS_INFO = "NEEDS_INFO"
    ESCALATED = "ESCALATED"
    AWAITING_RECEIPT = "AWAITING_RECEIPT"
    RESOLVED = "RESOLVED"


class Level(str, Enum):
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class Case(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    title: str
    company_id: str | None = None
    status: CaseStatus = CaseStatus.DRAFT
    level: Level = Level.L2
    facts_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    strength_score: int = Field(default=0, ge=0, le=100)
    strength_label: str | None = None
    demand: str | None = None
    amount_inr: float | None = None
    created_at: datetime = Field(default_factory=now_utc)
    resolved_at: datetime | None = None
    recovered_inr: float = 0


class Evidence(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    case_id: str = Field(foreign_key="case.id", index=True)
    kind: str
    path: str | None = None
    transcript: str | None = None
    extracted_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class Message(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    case_id: str = Field(foreign_key="case.id", index=True)
    direction: str
    level: Level = Level.L2
    to: str
    from_: str = Field(sa_column=Column("from", String, nullable=False))
    subject: str
    body_text: str
    message_id: str | None = Field(default=None, index=True)
    in_reply_to: str | None = None
    sent_at: datetime = Field(default_factory=now_utc)
    classification_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class Event(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    case_id: str = Field(foreign_key="case.id", index=True)
    at: datetime = Field(default_factory=now_utc)
    actor: str
    type: str
    title: str
    reason: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class Deadline(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    case_id: str = Field(foreign_key="case.id", index=True)
    kind: str
    due_at: datetime
    status: str = "running"


class LlmCall(SQLModel, table=True):
    __tablename__ = "llm_calls"
    id: str = Field(default_factory=new_id, primary_key=True)
    task: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost_usd: float = 0
    latency_ms: float = 0
    cached: bool = False
    at: datetime = Field(default_factory=now_utc)


class Settings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    demo_clock_offset_seconds: int = 0
    autopilot: bool = False

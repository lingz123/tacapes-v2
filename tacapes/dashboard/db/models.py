"""SQLAlchemy models for the dashboard's three tables (spec §4)."""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MissionStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    budget_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    max_positions: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_position_pct: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False
    )  # stored as a fraction (0.400 = 40%), not a whole-number percentage
    horizon_months: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sectors_excluded: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    allow_shorts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[MissionStatus] = mapped_column(
        Enum(MissionStatus, name="mission_status"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    decomposition_json: Mapped[dict | None] = mapped_column(JSONB)
    assessments_json: Mapped[dict | None] = mapped_column(JSONB)
    shortlist_json: Mapped[dict | None] = mapped_column(JSONB)
    ta_outputs_json: Mapped[dict | None] = mapped_column(JSONB)
    memos_json: Mapped[dict | None] = mapped_column(JSONB)
    portfolio_json: Mapped[dict | None] = mapped_column(JSONB)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    positions: Mapped[list["Position"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_missions_status_created_at", "status", "created_at"),
        Index("ix_missions_created_at", "created_at"),
    )


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    weight_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    notional_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_short: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    entry_price_date: Mapped[date | None] = mapped_column(Date)

    mission: Mapped[Mission] = relationship(back_populates="positions")

    __table_args__ = (Index("ix_positions_ticker", "ticker"),)


class PriceQuote(Base):
    __tablename__ = "price_quotes"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

"""
Pydantic schemas for tacapes-v2.

Mission is the spine: every downstream object carries `mission_id`,
memos additionally carry `subtheme_id`. This makes every position
traceable: position → memo → subtheme → mission.
"""
from .common import (
    Catalyst,
    CorrelationCluster,
    Driver,
    KeyNumber,
    NewsItem,
    Risk,
    Source,
    SourceKind,
    Strict,
    Valuation,
    ValuationScenario,
    WebResult,
)
from .memo import (
    VAGUE_BREAKER_PATTERNS,
    InvestmentMemo,
    ThesisAlignment,
    is_falsifiable_breaker,
)
from .fund import (
    Fund,
    Holding,
    MissionRef,
    ProposedAction,
    ProposedChange,
    RebalanceProposal,
)
from .mission import Mission, MissionConstraints
from .portfolio import (
    ConstructorMode,
    PortfolioAllocation,
    PortfolioState,
    Position,
)
from .shortlist import Shortlist
from .subtheme import (
    CandidateTicker,
    SubTheme,
    SubThemeAssessment,
    ThesisDecomposition,
)
from .ta_output import PortfolioRating, TradingAgentsOutput

__all__ = [
    # mission spine
    "Mission",
    "MissionConstraints",
    # decomposition + research
    "SubTheme",
    "ThesisDecomposition",
    "CandidateTicker",
    "SubThemeAssessment",
    # shortlist
    "Shortlist",
    # ta output (raw)
    "TradingAgentsOutput",
    "PortfolioRating",
    # memo
    "InvestmentMemo",
    "ThesisAlignment",
    "VAGUE_BREAKER_PATTERNS",
    "is_falsifiable_breaker",
    # portfolio
    "Position",
    "PortfolioAllocation",
    "PortfolioState",
    "ConstructorMode",
    # fund (v2.1 persistent book)
    "Fund",
    "Holding",
    "MissionRef",
    "ProposedAction",
    "ProposedChange",
    "RebalanceProposal",
    # supporting
    "Source",
    "SourceKind",
    "KeyNumber",
    "Driver",
    "Risk",
    "Catalyst",
    "ValuationScenario",
    "Valuation",
    "CorrelationCluster",
    "WebResult",
    "NewsItem",
    "Strict",
]

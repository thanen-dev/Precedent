"""
Data models for Precedent leader profiles and the extraction pipeline.

Two separate concerns live here:
  1. Extraction types  — SourceMeta, DocField — used by claude_client.py when
     pulling evidence from a single document.
  2. Profile types     — LeaderMeta, Dimensions, Synthesis, LeaderProfile —
     used to validate and load the master JSON profiles in data/leaders/.

All profile models use extra="forbid". Unknown top-level keys and misspelled
dimension names will raise ValidationError. If a field is genuinely optional,
declare it explicitly; do not rely on extra="allow" as a catch-all.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ── 1. Extraction types ───────────────────────────────────────────────────────


class SourceMeta(BaseModel):
    """Provenance record attached to every extracted claim."""

    url: HttpUrl
    date: date
    quote: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class DocField(BaseModel):
    """A single mental-model field extracted from one document."""

    value: str = Field(min_length=1)
    source: SourceMeta


# ── 2. Profile types ──────────────────────────────────────────────────────────

#: The 7 analytical dimensions that every leader profile must cover.
DIMENSION_KEYS: tuple[str, ...] = (
    "growth_theory",
    "risk_tolerance",
    "time_horizon",
    "dependency_assumptions",
    "institution_vs_relationship",
    "global_positioning_logic",
    "consistency_score",
)


class Dimensions(BaseModel):
    """
    Container for the 7 analytical dimensions.

    extra="forbid" means a misspelled key (e.g. 'growth_theori') raises a
    ValidationError rather than silently passing. Each field is optional so
    partial profiles (leaders still being researched) are valid.
    """

    model_config = ConfigDict(extra="forbid")

    growth_theory: dict[str, Any] | None = None
    risk_tolerance: dict[str, Any] | None = None
    time_horizon: dict[str, Any] | None = None
    dependency_assumptions: dict[str, Any] | None = None
    institution_vs_relationship: dict[str, Any] | None = None
    global_positioning_logic: dict[str, Any] | None = None
    consistency_score: dict[str, Any] | None = None


class LeaderMeta(BaseModel):
    """Administrative metadata block — the 'leader' key in the profile."""

    model_config = ConfigDict(extra="forbid")

    name: str
    position: str
    in_office_since: str
    compiled: str
    purpose: str
    based_on: list[str] = Field(default_factory=list)


class Synthesis(BaseModel):
    """The 'synthesis' block — predictive principles, anchor quote, sources."""

    model_config = ConfigDict(extra="forbid")

    guiding_principles: list[dict[str, Any]]
    key_external_analysis_quote: dict[str, Any]
    sources: list[str]


class LeaderProfile(BaseModel):
    """
    Master profile for a single decision-maker.

    extra="forbid" — unknown top-level keys raise ValidationError.
    The Dimensions model enforces the closed set of 7 dimension names.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    full_name: str
    title: str
    updated: date
    leader: LeaderMeta
    dimensions: Dimensions
    synthesis: Synthesis

    @property
    def populated_dimensions(self) -> list[str]:
        return [k for k in DIMENSION_KEYS if getattr(self.dimensions, k) is not None]

    @property
    def completeness(self) -> float:
        return len(self.populated_dimensions) / len(DIMENSION_KEYS)


# ── 3. Helpers ────────────────────────────────────────────────────────────────

ConfidenceTier = Literal["high", "medium", "low"]


def confidence_tier(score: float) -> ConfidenceTier:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"

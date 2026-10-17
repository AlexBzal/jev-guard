"""Carga de política (config/policy.yaml) y contexto de negocio (data/context.yaml)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from .models import Tier

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = ROOT / "config" / "policy.yaml"
DEFAULT_CONTEXT = ROOT / "data" / "context.yaml"


class TierPolicy(BaseModel):
    block: float
    review: float
    min_certainty: float
    on_uncertain: Literal["llm", "human"]
    on_jev_error: Literal["allow", "hold"]


class JevConfig(BaseModel):
    model: str = "jev-latest"
    timeout_s: float = 1.5
    price_per_million_input: float = 0.042
    max_context_tokens: int = 32000


class LlmConfig(BaseModel):
    enabled: bool = True
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    timeout_s: float = 20
    price_per_million_input: float = 4.0
    price_per_million_output: float = 20.0
    est_output_tokens: int = 200


class Limits(BaseModel):
    email_send_max_recipients: int = 50
    frequency_cap_7d: int = 3
    frequency_cap_share_bulk: float = 0.10
    audience_overshoot_review: float = 1.5
    audience_overshoot_block: float = 3.0
    bulk_two_keys_from: int = 5000
    quiet_hours: tuple[int, int] = (20, 8)
    crm_review_records: int = 2000
    crm_delete_review_records: int = 100
    deal_amount_change_review: float = 0.5
    hashtags_max: int = 5


class AgentPolicy(BaseModel):
    description: str = ""
    allowed: list[str]
    max_tier: Tier


class Policy(BaseModel):
    timezone: str = "America/Bogota"
    tiers: dict[Tier, TierPolicy]
    risk_floor: float = 0.20
    critical_block: float = 0.70
    strong_signal_weight: float = 0.80
    uncertain_band: tuple[float, float] = (0.30, 0.70)
    uncertain_min_weight: float = 0.5
    jev: JevConfig = Field(default_factory=JevConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    limits: Limits = Field(default_factory=Limits)
    protected_crm_fields: list[str] = Field(default_factory=list)
    platform_max_chars: dict[str, int] = Field(default_factory=dict)
    agents: dict[str, AgentPolicy] = Field(default_factory=dict)


class SendRecord(BaseModel):
    email: str
    days_ago: float
    subject: str = ""


class BusinessContext(BaseModel):
    brand: dict[str, Any]
    offer_catalog: list[dict[str, str]]
    allowed_link_domains: list[str]
    link_shorteners: list[str] = Field(default_factory=list)
    suppression_list: list[str] = Field(default_factory=list)
    confidential_entities: list[str] = Field(default_factory=list)
    send_history: list[SendRecord] = Field(default_factory=list)

    def for_jev(self) -> dict[str, Any]:
        """La parte del contexto que JEV necesita para juzgar (sin listas operativas)."""
        return {
            "brand": self.brand,
            "offer_catalog": self.offer_catalog,
            "confidential_entities": self.confidential_entities,
        }


def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_policy(path: str | Path | None = None) -> Policy:
    path = Path(path or os.environ.get("JEV_GUARD_POLICY", DEFAULT_POLICY))
    return Policy.model_validate(_read_yaml(path))


def load_context(path: str | Path | None = None) -> BusinessContext:
    path = Path(path or os.environ.get("JEV_GUARD_CONTEXT", DEFAULT_CONTEXT))
    return BusinessContext.model_validate(_read_yaml(path))


@lru_cache(maxsize=1)
def default_policy() -> Policy:
    return load_policy()


@lru_cache(maxsize=1)
def default_context() -> BusinessContext:
    return load_context()

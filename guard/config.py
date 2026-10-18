"""Configuración: valores por defecto del motor + perfil de la empresa.

    config/defaults.yaml              motor: umbrales, límites, precios (común a todas)
    profiles/<perfil>/policy.yaml     la empresa: agentes, acciones propias, ajustes
    profiles/<perfil>/context.yaml    el negocio: marca, oferta, políticas, listas
    profiles/<perfil>/scenarios*.yaml casos etiquetados para evaluar

El perfil se elige con JEV_GUARD_PROFILE (por defecto "demo"). Las claves del perfil
se combinan con las de defaults.yaml: los diccionarios se mezclan y el resto se reemplaza.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .models import Tier

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = ROOT / "config" / "defaults.yaml"
PROFILES_DIR = ROOT / "profiles"
DEFAULT_PROFILE = "demo"

BUILTIN_ACTIONS = ["email.send", "email.bulk", "crm.update", "crm.delete", "content.publish"]


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
    name: str = ""
    description: str = ""
    allowed: list[str]
    max_tier: Tier


# -- preguntas y acciones personalizadas ------------------------------------------------

class QuestionSpec(BaseModel):
    """Una pregunta tipada a JEV declarada en YAML por la empresa."""

    qid: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: Literal["noul", "score", "choice"]
    instructions: str
    label: str = Field(description="Frase de riesgo que ve una persona cuando la señal se activa")
    short: str = Field(default="", description="La pregunta en lenguaje claro, para la interfaz")
    weight: float = Field(default=0.6, ge=0, le=1)
    critical: bool = False
    # noul: qué respuesta es la riesgosa
    risk: Literal["yes_is_bad", "yes_is_good"] | None = None
    # score: niveles ordenados de menos a más riesgo; choice: opción -> descripción
    criteria: list[str] | dict[str, str] | None = None
    # choice: riesgo de cada opción (0-1); las que falten valen 0,5
    risk_by_option: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "QuestionSpec":
        if self.type == "noul" and self.risk is None:
            raise ValueError(f"{self.qid}: una pregunta noul necesita `risk: yes_is_bad | yes_is_good`")
        if self.type == "score" and not isinstance(self.criteria, list):
            raise ValueError(f"{self.qid}: una pregunta score necesita `criteria` como lista ordenada")
        if self.type == "choice":
            if not isinstance(self.criteria, dict):
                raise ValueError(f"{self.qid}: una pregunta choice necesita `criteria` como diccionario")
            if "other" not in self.criteria:
                raise ValueError(f"{self.qid}: toda pregunta choice debe incluir la opción `other`")
        return self


class FieldSpec(BaseModel):
    name: str
    label: str = ""
    kind: Literal["text", "textarea", "number", "list"] = "text"


class ScopeSpec(BaseModel):
    """Cuántas personas o registros afecta la acción: un valor fijo, o un campo del contenido."""

    fixed: int | None = None
    field: str | None = None

    @model_validator(mode="after")
    def _one(self) -> "ScopeSpec":
        if (self.fixed is None) == (self.field is None):
            raise ValueError("scope necesita exactamente uno de `fixed` o `field`")
        return self


class CustomActionSpec(BaseModel):
    label: str
    description: str = ""
    summary_field: str | None = None
    fields: list[FieldSpec] = Field(default_factory=list)
    reversible: bool = False
    scope: ScopeSpec = Field(default_factory=lambda: ScopeSpec(fixed=1))
    # Alcance máximo de cada tier; por encima del de `high` la acción es crítica.
    tier_by_scope: dict[Literal["low", "medium", "high"], int] = Field(
        default_factory=lambda: {"low": 5, "medium": 200, "high": 2000})
    common_questions: list[str] = Field(default_factory=lambda: ["goal_alignment", "injection_signs"])
    questions: list[QuestionSpec] = Field(default_factory=list)


class Policy(BaseModel):
    profile: str = DEFAULT_PROFILE
    timezone: str = "UTC"
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
    custom_actions: dict[str, CustomActionSpec] = Field(default_factory=dict)
    extra_questions: dict[str, list[QuestionSpec]] = Field(default_factory=dict)

    @field_validator("custom_actions")
    @classmethod
    def _no_builtin_names(cls, v: dict[str, CustomActionSpec]) -> dict[str, CustomActionSpec]:
        clash = set(v) & set(BUILTIN_ACTIONS)
        if clash:
            raise ValueError(f"Las acciones personalizadas no pueden llamarse como las estándar: {sorted(clash)}")
        return v

    @property
    def action_types(self) -> list[str]:
        return BUILTIN_ACTIONS + list(self.custom_actions)


# -- contexto de negocio ------------------------------------------------------------------

class Company(BaseModel):
    name: str
    description: str = ""


class EmailPurpose(BaseModel):
    label: str
    marketing: bool = False           # exige opción de baja en envíos masivos
    quiet_hours_exempt: bool = False  # puede enviarse fuera del horario permitido


class SendRecord(BaseModel):
    email: str
    days_ago: float
    subject: str = ""


class BusinessContext(BaseModel):
    company: Company
    email_purposes: dict[str, EmailPurpose] = Field(default_factory=lambda: {
        "follow_up": EmailPurpose(label="Seguimiento comercial", marketing=True),
        "newsletter": EmailPurpose(label="Contenido editorial o boletín", marketing=True),
        "transactional": EmailPurpose(label="Mensaje operativo", quiet_hours_exempt=True),
    })
    policies: list[str] = Field(default_factory=list)
    brand: dict[str, Any] = Field(default_factory=dict)
    offer_catalog: list[dict[str, str]] = Field(default_factory=list)
    allowed_link_domains: list[str] = Field(default_factory=list)
    link_shorteners: list[str] = Field(default_factory=list)
    suppression_list: list[str] = Field(default_factory=list)
    confidential_entities: list[str] = Field(default_factory=list)
    send_history: list[SendRecord] = Field(default_factory=list)

    def for_jev(self) -> dict[str, Any]:
        """La parte del contexto que JEV necesita para juzgar (sin listas operativas)."""
        return {
            "company": self.company.model_dump(),
            "brand": self.brand,
            "offer_catalog": self.offer_catalog,
            "policies": self.policies,
            "confidential_entities": self.confidential_entities,
        }


# -- carga ------------------------------------------------------------------------------------

def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def profile_name() -> str:
    return os.environ.get("JEV_GUARD_PROFILE", DEFAULT_PROFILE)


def profile_dir(name: str | None = None) -> Path:
    path = PROFILES_DIR / (name or profile_name())
    if not path.is_dir():
        available = sorted(p.name for p in PROFILES_DIR.iterdir() if p.is_dir())
        raise FileNotFoundError(f"No existe el perfil '{path.name}'. Perfiles disponibles: {available}")
    return path


def load_policy(path: str | Path | None = None, profile: str | None = None) -> Policy:
    """Combina defaults.yaml con el policy.yaml del perfil (o con `path` si se indica)."""
    explicit = path or os.environ.get("JEV_GUARD_POLICY")
    data = _read_yaml(DEFAULTS)
    if explicit:
        data = deep_merge(data, _read_yaml(Path(explicit)))
        name = profile or profile_name()
    else:
        pdir = profile_dir(profile)
        name = pdir.name
        if (pdir / "policy.yaml").exists():
            data = deep_merge(data, _read_yaml(pdir / "policy.yaml"))
    data.setdefault("profile", name)
    return Policy.model_validate(data)


def load_context(path: str | Path | None = None, profile: str | None = None) -> BusinessContext:
    explicit = path or os.environ.get("JEV_GUARD_CONTEXT")
    source = Path(explicit) if explicit else profile_dir(profile) / "context.yaml"
    return BusinessContext.model_validate(_read_yaml(source))


def scenario_files(profile: str | None = None) -> list[Path]:
    return sorted(profile_dir(profile).glob("scenarios*.yaml"))


@lru_cache(maxsize=1)
def default_policy() -> Policy:
    return load_policy()


@lru_cache(maxsize=1)
def default_context() -> BusinessContext:
    return load_context()

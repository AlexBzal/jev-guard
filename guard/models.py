"""Modelos de datos de JEV Guard.

Una *acción* es lo que un agente interno de 30X quiere ejecutar (enviar un correo,
tocar el CRM, publicar). Una *decisión* es la respuesta del guardián: dejarla pasar,
frenarla o retenerla para que la revise una persona.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Acciones que pueden proponer los agentes
# ---------------------------------------------------------------------------

class EmailPurpose(str, Enum):
    FOLLOW_UP = "follow_up"          # seguimiento comercial a un lead
    EVENT_INVITE = "event_invite"    # invitación o recordatorio de evento (Luma)
    PROGRAM = "program"              # comunicación a alumnos de un programa
    NEWSLETTER = "newsletter"        # contenido editorial periódico
    TRANSACTIONAL = "transactional"  # confirmaciones, accesos, facturas


class Audience(BaseModel):
    segment_id: str
    description: str = Field(description="Descripción en lenguaje natural del segmento")
    expected_size: int | None = Field(default=None, ge=0, description="Tamaño esperado del segmento")


class _ActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(default_factory=lambda: _uid("act"))
    agent_id: str = Field(description="Identificador del agente que propone la acción")
    task: str = Field(description="La instrucción que recibió el agente; JEV verifica que la acción la cumpla")
    requested_at: datetime | None = None


class EmailSendAction(_ActionBase):
    action_type: Literal["email.send"] = "email.send"
    to: list[str] = Field(min_length=1)
    subject: str
    body: str
    purpose: EmailPurpose
    send_at: datetime | None = None


class EmailBulkAction(_ActionBase):
    action_type: Literal["email.bulk"] = "email.bulk"
    audience: Audience
    recipients: list[str] = Field(default_factory=list, description="Lista completa o muestra de destinatarios")
    recipient_count: int | None = Field(default=None, ge=0, description="Total real si `recipients` es una muestra")
    subject: str
    body: str
    purpose: EmailPurpose
    send_at: datetime | None = None


class CrmObject(str, Enum):
    CONTACT = "contact"
    DEAL = "deal"
    COMPANY = "company"


class CrmUpdateAction(_ActionBase):
    action_type: Literal["crm.update"] = "crm.update"
    object: CrmObject
    record_ids: list[str] = Field(default_factory=list)
    record_count: int | None = Field(default=None, ge=0)
    filter: str = Field(default="", description="Filtro que define los registros afectados")
    changes: dict[str, Any] = Field(min_length=1)
    previous: dict[str, Any] = Field(default_factory=dict, description="Valores anteriores, si se conocen")
    evidence: str = Field(default="", description="Por qué el agente cree que el cambio es correcto")


class CrmDeleteAction(_ActionBase):
    action_type: Literal["crm.delete"] = "crm.delete"
    object: CrmObject
    record_ids: list[str] = Field(default_factory=list)
    record_count: int | None = Field(default=None, ge=0)
    filter: str = ""
    reason: str = ""
    evidence: str = ""


class Platform(str, Enum):
    LINKEDIN = "linkedin"
    X = "x"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    BLOG = "blog"


class ContentPublishAction(_ActionBase):
    action_type: Literal["content.publish"] = "content.publish"
    platform: Platform
    text: str
    title: str = ""
    media: list[str] = Field(default_factory=list)
    scheduled_at: datetime | None = None


AgentAction = Annotated[
    Union[EmailSendAction, EmailBulkAction, CrmUpdateAction, CrmDeleteAction, ContentPublishAction],
    Field(discriminator="action_type"),
]
ACTION_ADAPTER: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)

ACTION_TYPES = ["email.send", "email.bulk", "crm.update", "crm.delete", "content.publish"]


def parse_action(data: dict[str, Any]) -> AgentAction:
    return ACTION_ADAPTER.validate_python(data)


# ---------------------------------------------------------------------------
# Hechos deterministas (lo que calcula el código, no JEV)
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    BLOCK = "block"    # frena la acción sin consultar a JEV
    REVIEW = "review"  # obliga a revisión humana
    INFO = "info"      # se registra y se pasa a JEV como contexto


class RuleHit(BaseModel):
    code: str
    severity: Severity
    message: str


class Tier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


TIER_ORDER = [Tier.LOW, Tier.MEDIUM, Tier.HIGH, Tier.CRITICAL]


def bump_tier(tier: Tier, steps: int = 1) -> Tier:
    idx = min(TIER_ORDER.index(tier) + steps, len(TIER_ORDER) - 1)
    return TIER_ORDER[idx]


class Facts(BaseModel):
    """Resultado del análisis determinista de una acción."""

    tier: Tier
    blast_radius: int = Field(description="Personas o registros afectados")
    reversible: bool
    values: dict[str, Any] = Field(default_factory=dict, description="Hechos calculados que se pasan a JEV")
    hits: list[RuleHit] = Field(default_factory=list)

    @property
    def blocking(self) -> list[RuleHit]:
        return [h for h in self.hits if h.severity == Severity.BLOCK]

    @property
    def needs_review(self) -> list[RuleHit]:
        return [h for h in self.hits if h.severity == Severity.REVIEW]


# ---------------------------------------------------------------------------
# Respuestas de JEV normalizadas
# ---------------------------------------------------------------------------

class JevAnswer(BaseModel):
    type: Literal["choice", "score", "noul"]
    choice: str | None = None
    score: float | None = None
    noul: float | None = None
    confidence: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)


class JevResult(BaseModel):
    model: str
    answers: dict[str, JevAnswer]
    input_tokens: int
    output_tokens: int = 0
    latency_ms: float
    simulated: bool


# ---------------------------------------------------------------------------
# Decisión final
# ---------------------------------------------------------------------------

class Verdict(str, Enum):
    ALLOW = "allow"  # el agente puede ejecutar
    BLOCK = "block"  # el agente no debe ejecutar
    HOLD = "hold"    # retenida: espera revisión humana


class Route(str, Enum):
    RULES = "rules"  # resuelta por reglas deterministas
    JEV = "jev"      # resuelta por JEV de forma autónoma
    LLM = "llm"      # JEV dudó y un LLM dio segunda opinión
    HUMAN = "human"  # pasó a una persona


class Reason(BaseModel):
    source: Literal["rule", "jev", "llm", "system", "human"]
    code: str
    message: str
    risk: float | None = None
    certainty: float | None = None
    severity: Severity | None = None


class SignalReading(BaseModel):
    """Cómo se interpretó cada respuesta de JEV en términos de riesgo."""

    qid: str
    label: str
    risk: float
    certainty: float
    weight: float
    critical: bool = False
    raw: JevAnswer


class Decision(BaseModel):
    decision_id: str = Field(default_factory=lambda: _uid("dec"))
    action_id: str
    agent_id: str
    action_type: str
    verdict: Verdict
    route: Route
    tier: Tier
    risk: float = Field(description="Riesgo compuesto 0-1")
    reasons: list[Reason] = Field(default_factory=list)
    signals: list[SignalReading] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    jev_latency_ms: float | None = None
    jev_model: str | None = None
    jev_simulated: bool | None = None
    input_tokens: int = 0
    cost_usd: float = 0.0
    llm_used: bool = False
    status: Literal["final", "pending_review"] = "final"
    summary: str = Field(default="", description="Descripción breve de la acción, para personas")
    sandbox: bool = Field(default=False, description="Evaluación de prueba: no se guarda ni cuenta en métricas")
    created_at: datetime = Field(default_factory=utcnow)


class ReviewInput(BaseModel):
    approve: bool = Field(description="True si la acción es segura y puede ejecutarse")
    reviewer: str
    note: str = ""


class LabelInput(BaseModel):
    """Etiqueta de auditoría sobre cualquier decisión (también las automáticas)."""

    safe: bool
    reviewer: str
    note: str = ""

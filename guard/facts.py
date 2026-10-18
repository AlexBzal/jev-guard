"""Reglas deterministas.

JEV no sabe contar, hacer aritmética ni comparar fechas, y esas comprobaciones tienen
respuesta exacta. Por eso se resuelven aquí, en código, antes de llamar a JEV:

* si una regla dice BLOCK, la acción se frena sin gastar una llamada a JEV;
* si dice REVIEW, la acción irá a una persona pase lo que pase;
* los hechos calculados (conteos, dominios, campos tocados) se le pasan a JEV como
  contexto para que juzgue con datos correctos.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .config import BusinessContext, Policy
from .models import (
    TIER_ORDER,
    ContentPublishAction,
    CrmDeleteAction,
    CrmUpdateAction,
    EmailBulkAction,
    EmailSendAction,
    Facts,
    RuleHit,
    Severity,
    Tier,
    bump_tier,
    utcnow,
)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"')\]]+", re.IGNORECASE)
MERGE_TAG_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")
PLACEHOLDER_RE = re.compile(
    r"\[(?:nombre|empresa|cargo|fecha|link|enlace|name|company|first[_ ]?name|insert[^\]]*|inserta[^\]]*)\]"
    r"|<(?:nombre|empresa|name|company)>"
    r"|(?<!\{)\{(?:nombre|empresa|name|first_name|company)\}(?!\})"
    r"|lorem ipsum",
    re.IGNORECASE,
)
# Marcadores de borrador: solo en mayúsculas, para no confundir "TODO" con la palabra "todo".
DRAFT_MARK_RE = re.compile(r"\bTODO\b|\bTBD\b|\bXXX+\b")
SECRET_PATTERNS = {
    "clave de API": re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{20,}"),
    "credencial de AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "token de GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "token de Slack": re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}"),
    "contraseña": re.compile(r"(?:contraseña|password|clave)\s*[:=]\s*\S{4,}", re.IGNORECASE),
}
CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}")
INLINE_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HASHTAG_RE = re.compile(r"#\w+")
UNSUBSCRIBE_RE = re.compile(r"\{\{\s*unsubscribe_url\s*\}\}|darte de baja|darse de baja|cancelar (?:tu )?suscripci[oó]n|unsubscribe", re.IGNORECASE)

THIRD_PARTY_EMAILS_REVIEW = 3
STAT_CLAIM_RE = re.compile(
    # No se usa el patrón "N x": chocaría con marcas como "30X".
    r"\d+(?:[.,]\d+)?\s*%|\b(?:multiplica\w*|duplica\w*|triplica\w*)\b|\b\d+\s*veces\b"
    r"|\bpor (?:dos|tres|cuatro|cinco|diez)\b", re.IGNORECASE)
SOURCE_RE = re.compile(r"\b(?:fuente|seg[uú]n|source|estudio|informe|reporte|encuesta)\b", re.IGNORECASE)

# Etiquetas de combinación que el proveedor de correo resuelve en envíos masivos.
ALLOWED_MERGE_TAGS = {"first_name", "company", "unsubscribe_url", "event_url", "program_name"}


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def find_secrets(text: str) -> list[str]:
    found = [name for name, rx in SECRET_PATTERNS.items() if rx.search(text)]
    for cand in CARD_CANDIDATE_RE.findall(text):
        digits = re.sub(r"\D", "", cand)
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            found.append("número de tarjeta")
            break
    return found


def extract_links(text: str) -> list[str]:
    return [u.rstrip(".,;:!?") for u in URL_RE.findall(text)]


def _host(url: str) -> str:
    if not url.lower().startswith("http"):
        url = "https://" + url
    return (urlparse(url).hostname or "").lower()


def _domain_allowed(host: str, allowed: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in allowed)


class FactEngine:
    def __init__(self, policy: Policy, context: BusinessContext):
        self.policy = policy
        self.ctx = context
        self.tz = ZoneInfo(policy.timezone)
        self._suppressed = {e.lower() for e in context.suppression_list}

    # -- API pública ---------------------------------------------------------

    def analyze(self, action, now: datetime | None = None) -> Facts:
        now = now or utcnow()
        handler = {
            "email.send": self._email_send,
            "email.bulk": self._email_bulk,
            "crm.update": self._crm_update,
            "crm.delete": self._crm_delete,
            "content.publish": self._publish,
        }.get(action.action_type, self._custom)
        facts = handler(action, now)
        self._agent_permissions(action, facts)
        return facts

    # -- Reglas comunes ------------------------------------------------------

    def _agent_permissions(self, action, facts: Facts) -> None:
        agent = self.policy.agents.get(action.agent_id)
        if agent is None:
            facts.hits.append(RuleHit(code="G001", severity=Severity.BLOCK,
                                      message=f"El agente '{action.agent_id}' no está registrado en la política."))
            return
        if action.action_type not in agent.allowed:
            facts.hits.append(RuleHit(code="G002", severity=Severity.BLOCK,
                                      message=f"El agente '{action.agent_id}' no tiene permiso para {action.action_type}."))
        if TIER_ORDER.index(facts.tier) > TIER_ORDER.index(agent.max_tier):
            facts.hits.append(RuleHit(code="G003", severity=Severity.REVIEW,
                                      message=f"El impacto ({facts.tier.value}) supera lo autorizado para este agente ({agent.max_tier.value})."))

    def _text_checks(self, text: str, hits: list[RuleHit], values: dict, *, merge_tags_ok: bool) -> None:
        secrets = find_secrets(text)
        if secrets:
            hits.append(RuleHit(code="T001", severity=Severity.BLOCK,
                                message="Contiene datos sensibles: " + ", ".join(sorted(set(secrets))) + "."))
        placeholders = [m.group(0) for m in PLACEHOLDER_RE.finditer(text)] + DRAFT_MARK_RE.findall(text)
        tags = MERGE_TAG_RE.findall(text)
        bad_tags = [t for t in tags if not (merge_tags_ok and t in ALLOWED_MERGE_TAGS)]
        if placeholders or bad_tags:
            shown = placeholders + ["{{" + t + "}}" for t in bad_tags]
            hits.append(RuleHit(code="T002", severity=Severity.BLOCK,
                                message="Tiene marcadores sin reemplazar: " + ", ".join(shown[:5]) + "."))
        links = extract_links(text)
        hosts = sorted({_host(u) for u in links})
        shorteners = [h for h in hosts if h in self.ctx.link_shorteners]
        external = [h for h in hosts if not _domain_allowed(h, self.ctx.allowed_link_domains) and h not in shorteners]
        insecure = [u for u in links if u.lower().startswith("http://")]
        if shorteners:
            hits.append(RuleHit(code="T003", severity=Severity.REVIEW,
                                message="Usa acortadores de enlaces que ocultan el destino: " + ", ".join(shorteners) + "."))
        if external:
            hits.append(RuleHit(code="T004", severity=Severity.REVIEW,
                                message="Enlaza a dominios fuera de la lista permitida: " + ", ".join(external) + "."))
        if insecure:
            hits.append(RuleHit(code="T005", severity=Severity.INFO,
                                message=f"{len(insecure)} enlace(s) sin HTTPS."))
        values.update(link_count=len(links), link_domains=hosts, external_domains=external,
                      char_count=len(text))

    def _purpose(self, key: str, hits: list[RuleHit]):
        purpose = self.ctx.email_purposes.get(key)
        if purpose is None:
            options = ", ".join(self.ctx.email_purposes)
            hits.append(RuleHit(code="E012", severity=Severity.BLOCK,
                                message=f"El propósito '{key}' no está registrado en el perfil. Opciones: {options}."))
        return purpose

    def _third_party_contacts(self, body: str, recipients: list[str], hits: list[RuleHit], values: dict) -> None:
        """Un correo que lleva direcciones de otras personas en el cuerpo puede estar filtrando datos."""
        own = {r.lower() for r in recipients}
        others = {e.lower() for e in INLINE_EMAIL_RE.findall(body)} - own
        values["third_party_emails_in_body"] = len(others)
        if len(others) >= THIRD_PARTY_EMAILS_REVIEW:
            hits.append(RuleHit(code="E011", severity=Severity.REVIEW,
                                message=f"El cuerpo incluye {len(others)} direcciones de correo de otras personas: posible filtración de datos."))

    def _local_hour(self, when: datetime) -> int:
        if when.tzinfo is None:
            when = when.replace(tzinfo=self.tz)
        return when.astimezone(self.tz).hour

    def _in_quiet_hours(self, when: datetime) -> bool:
        start, end = self.policy.limits.quiet_hours
        hour = self._local_hour(when)
        return hour >= start or hour < end

    def _history(self, emails: list[str]) -> tuple[dict[str, int], dict[str, list[str]]]:
        """Correos en los últimos 7 días por destinatario y asuntos de las últimas 24 h."""
        wanted = {e.lower() for e in emails}
        counts: dict[str, int] = {}
        recent: dict[str, list[str]] = {}
        for rec in self.ctx.send_history:
            email = rec.email.lower()
            if email not in wanted:
                continue
            if rec.days_ago <= 7:
                counts[email] = counts.get(email, 0) + 1
            if rec.days_ago <= 1:
                recent.setdefault(email, []).append(rec.subject.strip().lower())
        return counts, recent

    def _recipient_checks(self, recipients: list[str], subject: str, hits: list[RuleHit], values: dict,
                          *, bulk: bool) -> None:
        invalid = [r for r in recipients if not EMAIL_RE.match(r)]
        if invalid:
            hits.append(RuleHit(code="E003", severity=Severity.BLOCK,
                                message=f"{len(invalid)} dirección(es) con formato inválido, p. ej. '{invalid[0]}'."))
        suppressed = [r for r in recipients if r.lower() in self._suppressed]
        if suppressed:
            hits.append(RuleHit(code="E001", severity=Severity.BLOCK,
                                message=f"{len(suppressed)} destinatario(s) se dieron de baja y no pueden recibir correos."))
        counts, recent = self._history(recipients)
        cap = self.policy.limits.frequency_cap_7d
        over_cap = [e for e, n in counts.items() if n >= cap]
        dupes = [e for e, subs in recent.items() if subject.strip().lower() in subs]
        if dupes:
            hits.append(RuleHit(code="E009", severity=Severity.BLOCK,
                                message=f"{len(dupes)} destinatario(s) ya recibieron este mismo correo en las últimas 24 h."))
        if over_cap:
            share = len(over_cap) / max(len(recipients), 1)
            if not bulk or share >= self.policy.limits.frequency_cap_share_bulk:
                hits.append(RuleHit(code="E006", severity=Severity.REVIEW,
                                    message=f"{len(over_cap)} destinatario(s) ya recibieron {cap} o más correos esta semana."))
        values.update(invalid_recipients=len(invalid), suppressed_recipients=len(suppressed),
                      over_frequency_cap=len(over_cap), duplicate_last_24h=len(dupes))

    # -- Correo individual ---------------------------------------------------

    def _email_send(self, a: EmailSendAction, now: datetime) -> Facts:
        hits: list[RuleHit] = []
        values: dict = {"recipient_count": len(a.to), "declared_purpose": a.purpose}
        n = len(a.to)
        tier = Tier.LOW if n <= 5 else Tier.MEDIUM if n <= self.policy.limits.email_send_max_recipients else Tier.HIGH
        if n > self.policy.limits.email_send_max_recipients:
            hits.append(RuleHit(code="E010", severity=Severity.REVIEW,
                                message=f"Envío individual con {n} destinatarios: debería ser una campaña masiva."))
        if not a.subject.strip() or not a.body.strip():
            hits.append(RuleHit(code="E008", severity=Severity.BLOCK, message="El asunto o el cuerpo están vacíos."))
        self._recipient_checks(a.to, a.subject, hits, values, bulk=False)
        self._text_checks(f"{a.subject}\n{a.body}", hits, values, merge_tags_ok=False)
        self._third_party_contacts(a.body, a.to, hits, values)
        when = a.send_at or now
        values["local_send_hour"] = self._local_hour(when)
        purpose = self._purpose(a.purpose, hits)
        if self._in_quiet_hours(when) and not (purpose and purpose.quiet_hours_exempt):
            hits.append(RuleHit(code="E007", severity=Severity.REVIEW,
                                message=f"Se enviaría a las {values['local_send_hour']}:00, fuera del horario permitido."))
        return Facts(tier=tier, blast_radius=n, reversible=False, values=values, hits=hits)

    # -- Correo masivo -------------------------------------------------------

    def _email_bulk(self, a: EmailBulkAction, now: datetime) -> Facts:
        hits: list[RuleHit] = []
        lim = self.policy.limits
        n = a.recipient_count if a.recipient_count is not None else len(a.recipients)
        values: dict = {"recipient_count": n, "declared_purpose": a.purpose,
                        "segment_id": a.audience.segment_id, "expected_size": a.audience.expected_size}
        if n == 0:
            hits.append(RuleHit(code="B004", severity=Severity.BLOCK, message="La campaña no tiene destinatarios."))
        tier = Tier.MEDIUM if n < 500 else Tier.HIGH if n < lim.bulk_two_keys_from else Tier.CRITICAL
        if n >= lim.bulk_two_keys_from:
            hits.append(RuleHit(code="B003", severity=Severity.REVIEW,
                                message=f"Campaña a {n:,} personas: requiere segunda llave humana.".replace(",", ".")))
        if a.audience.expected_size:
            ratio = n / a.audience.expected_size
            values["audience_ratio"] = round(ratio, 2)
            if ratio >= lim.audience_overshoot_block:
                hits.append(RuleHit(code="B002", severity=Severity.BLOCK,
                                    message=f"Va a {ratio:.1f} veces más personas que el segmento esperado. ¿Se seleccionó toda la base?"))
            elif ratio >= lim.audience_overshoot_review:
                hits.append(RuleHit(code="B002", severity=Severity.REVIEW,
                                    message=f"Va a {ratio:.1f} veces más personas que el segmento esperado."))
        purpose = self._purpose(a.purpose, hits)
        if purpose and purpose.marketing and not UNSUBSCRIBE_RE.search(a.body):
            hits.append(RuleHit(code="B001", severity=Severity.BLOCK,
                                message="El correo masivo no incluye forma de darse de baja."))
        if not a.subject.strip() or not a.body.strip():
            hits.append(RuleHit(code="E008", severity=Severity.BLOCK, message="El asunto o el cuerpo están vacíos."))
        if a.recipients:
            self._recipient_checks(a.recipients, a.subject, hits, values, bulk=True)
        self._text_checks(f"{a.subject}\n{a.body}", hits, values, merge_tags_ok=True)
        when = a.send_at or now
        values["local_send_hour"] = self._local_hour(when)
        if self._in_quiet_hours(when) and not (purpose and purpose.quiet_hours_exempt):
            hits.append(RuleHit(code="E007", severity=Severity.BLOCK,
                                message=f"Campaña programada a las {values['local_send_hour']}:00, fuera del horario permitido. Reprogramar."))
        return Facts(tier=tier, blast_radius=n, reversible=False, values=values, hits=hits)

    # -- CRM -----------------------------------------------------------------

    def _crm_scope(self, a, hits: list[RuleHit]) -> int:
        n = a.record_count if a.record_count is not None else len(a.record_ids)
        if n == 0 and not a.record_ids:
            hits.append(RuleHit(code="C006", severity=Severity.BLOCK, message="No se especificaron registros afectados."))
        if not a.record_ids and not a.filter.strip():
            hits.append(RuleHit(code="C003", severity=Severity.BLOCK,
                                message="La operación no tiene IDs ni filtro: afectaría a todos los registros."))
        return n

    def _crm_update(self, a: CrmUpdateAction, now: datetime) -> Facts:
        hits: list[RuleHit] = []
        lim = self.policy.limits
        n = self._crm_scope(a, hits)
        protected = sorted(set(a.changes) & set(self.policy.protected_crm_fields))
        values: dict = {"record_count": n, "object": a.object.value, "fields_changed": sorted(a.changes),
                        "protected_fields_touched": protected, "has_evidence": bool(a.evidence.strip())}
        tier = Tier.LOW if n <= 10 else Tier.MEDIUM if n <= 200 else Tier.HIGH if n <= lim.crm_review_records else Tier.CRITICAL
        if protected:
            tier = bump_tier(tier)
            hits.append(RuleHit(code="C001", severity=Severity.REVIEW,
                                message="Modifica campos protegidos: " + ", ".join(protected) + "."))
        if n > lim.crm_review_records:
            hits.append(RuleHit(code="C003", severity=Severity.REVIEW,
                                message=f"Modifica {n} registros a la vez."))
        if "deal_amount" in a.changes and "deal_amount" in a.previous:
            try:
                old, new = float(a.previous["deal_amount"]), float(a.changes["deal_amount"])
                delta = abs(new - old) / old if old else 1.0
                values["deal_amount_change"] = round(delta, 2)
                if delta >= lim.deal_amount_change_review:
                    hits.append(RuleHit(code="C002", severity=Severity.REVIEW,
                                        message=f"Cambia el monto del negocio en {delta:.0%}."))
            except (TypeError, ValueError):
                hits.append(RuleHit(code="C002", severity=Severity.REVIEW, message="El monto del negocio no es numérico."))
        if str(a.previous.get("stage", "")).lower() in {"won", "ganado", "closed_won"} and "stage" in a.changes:
            hits.append(RuleHit(code="C005", severity=Severity.REVIEW,
                                message="Cambia la etapa de un negocio que ya estaba ganado."))
        text = " ".join(str(v) for v in a.changes.values())
        if find_secrets(text):
            hits.append(RuleHit(code="T001", severity=Severity.BLOCK, message="Intenta guardar datos sensibles en el CRM."))
        return Facts(tier=tier, blast_radius=n, reversible=True, values=values, hits=hits)

    def _crm_delete(self, a: CrmDeleteAction, now: datetime) -> Facts:
        hits: list[RuleHit] = []
        lim = self.policy.limits
        n = self._crm_scope(a, hits)
        values: dict = {"record_count": n, "object": a.object.value, "has_reason": bool(a.reason.strip()),
                        "has_evidence": bool(a.evidence.strip())}
        tier = Tier.MEDIUM if n <= 5 else Tier.HIGH if n <= lim.crm_delete_review_records else Tier.CRITICAL
        if not a.reason.strip():
            hits.append(RuleHit(code="C004", severity=Severity.BLOCK, message="Eliminación sin motivo declarado."))
        if a.object.value == "deal":
            hits.append(RuleHit(code="C007", severity=Severity.REVIEW,
                                message="Eliminar negocios borra historial comercial: requiere una persona."))
        if n > lim.crm_delete_review_records:
            hits.append(RuleHit(code="C004", severity=Severity.REVIEW,
                                message=f"Elimina {n} registros: siempre requiere una persona."))
        return Facts(tier=tier, blast_radius=n, reversible=False, values=values, hits=hits)

    # -- Publicación ---------------------------------------------------------

    def _publish(self, a: ContentPublishAction, now: datetime) -> Facts:
        hits: list[RuleHit] = []
        text = f"{a.title}\n{a.text}".strip()
        values: dict = {"platform": a.platform.value}
        limit = self.policy.platform_max_chars.get(a.platform.value)
        if limit and len(a.text) > limit:
            hits.append(RuleHit(code="P001", severity=Severity.BLOCK,
                                message=f"Tiene {len(a.text)} caracteres; el máximo en {a.platform.value} es {limit}."))
        if not a.text.strip():
            hits.append(RuleHit(code="P002", severity=Severity.BLOCK, message="La publicación está vacía."))
        self._text_checks(text, hits, values, merge_tags_ok=False)
        if STAT_CLAIM_RE.search(text) and not SOURCE_RE.search(text):
            hits.append(RuleHit(code="P007", severity=Severity.REVIEW,
                                message="Publica cifras o resultados sin citar una fuente."))
        hashtags = HASHTAG_RE.findall(a.text)
        values["hashtag_count"] = len(hashtags)
        if len(hashtags) > self.policy.limits.hashtags_max:
            hits.append(RuleHit(code="P003", severity=Severity.INFO, message=f"Usa {len(hashtags)} hashtags."))
        pii = INLINE_EMAIL_RE.findall(text) + [p for p in PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 9]
        values["pii_found"] = len(pii)
        if pii:
            hits.append(RuleHit(code="P006", severity=Severity.REVIEW,
                                message="Publicaría datos de contacto personales (correo o teléfono)."))
        return Facts(tier=Tier.HIGH, blast_radius=1, reversible=False, values=values, hits=hits)

    # -- Acciones personalizadas -------------------------------------------------

    def _custom(self, a, now: datetime) -> Facts:
        """Acciones declaradas por la empresa en `custom_actions` de su perfil."""
        spec = self.policy.custom_actions.get(a.action_type)
        hits: list[RuleHit] = []
        if spec is None:
            known = ", ".join(self.policy.action_types)
            hits.append(RuleHit(code="G005", severity=Severity.BLOCK,
                                message=f"El tipo de acción '{a.action_type}' no está declarado en el perfil. Tipos válidos: {known}."))
            return Facts(tier=Tier.HIGH, blast_radius=1, reversible=False, values={}, hits=hits)

        missing = [f.name for f in spec.fields if f.name not in a.content]
        if missing:
            hits.append(RuleHit(code="X001", severity=Severity.BLOCK,
                                message="Faltan campos de la acción: " + ", ".join(missing) + "."))
        scope = spec.scope.fixed
        if spec.scope.field is not None:
            raw = a.content.get(spec.scope.field)
            try:
                scope = int(raw)
            except (TypeError, ValueError):
                scope = len(raw) if isinstance(raw, (list, tuple)) else 1
                if not isinstance(raw, (list, tuple)):
                    hits.append(RuleHit(code="X002", severity=Severity.REVIEW,
                                        message=f"No se pudo leer el alcance en el campo '{spec.scope.field}'."))
        limits = spec.tier_by_scope
        tier = (Tier.LOW if scope <= limits.get("low", 5) else Tier.MEDIUM if scope <= limits.get("medium", 200)
                else Tier.HIGH if scope <= limits.get("high", 2000) else Tier.CRITICAL)
        values: dict = {"scope": scope, "action_label": spec.label}
        text = "\n".join(str(v) for v in _strings(a.content))
        self._text_checks(text, hits, values, merge_tags_ok=False)
        pii = INLINE_EMAIL_RE.findall(text)
        values["emails_in_content"] = len(pii)
        return Facts(tier=tier, blast_radius=scope, reversible=spec.reversible, values=values, hits=hits)


def _strings(obj):
    """Todos los textos de un contenido anidado."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)

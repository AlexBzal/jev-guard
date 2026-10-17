"""Clientes de JEV.

* `TypeSafeJev`: llama a la API real (POST https://api.typesafe.ai/v1/systemone).
* `SimulatedJev`: imita el formato y la calibración de JEV con heurísticas locales.
  Sirve para que el prototipo corra sin clave ni red. NO es JEV: sus respuestas se
  marcan como simuladas en cada decisión, en la API y en los reportes.

Ambos devuelven `JevResult` con respuestas normalizadas.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import unicodedata
from typing import Any, Protocol

import httpx

from .models import JevAnswer, JevResult

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"


class JevError(RuntimeError):
    pass


class JevBackend(Protocol):
    simulated: bool

    def evaluate(self, state: dict[str, Any], questions: dict[str, dict]) -> JevResult: ...


# ---------------------------------------------------------------------------
# Confianza, con las fórmulas publicadas en docs.typesafe.ai/confidence
# ---------------------------------------------------------------------------

def choice_confidence(probs: list[float]) -> float:
    n = len(probs)
    if n < 2:
        return 1.0
    return max(0.0, (max(probs) - 1 / n) / (1 - 1 / n))


def score_confidence(probs: list[float]) -> float:
    n = len(probs)
    if n < 2:
        return 1.0
    m = max(range(n), key=lambda i: probs[i])
    mad = sum(p * abs(i - m) for i, p in enumerate(probs))
    mad_unif = sum(abs(i - (n - 1) / 2) for i in range(n)) / n
    return max(0.0, 1 - mad / mad_unif) if mad_unif else 1.0


def estimate_tokens(*parts: Any) -> int:
    text = "".join(p if isinstance(p, str) else json.dumps(p, ensure_ascii=False) for p in parts)
    return max(1, math.ceil(len(text) / 3.5))


# ---------------------------------------------------------------------------
# API real
# ---------------------------------------------------------------------------

def _parse_answer(raw: dict[str, Any]) -> JevAnswer:
    probs = {str(k): float(v) for k, v in (raw.get("probabilities") or {}).items()}
    return JevAnswer(
        type=raw["type"],
        choice=raw.get("choice"),
        score=raw.get("score"),
        noul=raw.get("noul"),
        confidence=raw.get("confidence"),
        probabilities=probs,
    )


class TypeSafeJev:
    simulated = False

    def __init__(self, api_key: str, model: str = "jev-latest", timeout_s: float = 1.5,
                 client: httpx.Client | None = None):
        self.model = model
        self._client = client or httpx.Client(
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    def evaluate(self, state: dict[str, Any], questions: dict[str, dict]) -> JevResult:
        body = {"state": state, "model": self.model, "questions": questions}
        t0 = time.perf_counter()
        try:
            resp = self._client.post(TYPESAFE_URL, json=body)
        except httpx.TimeoutException as exc:
            raise JevError("JEV no respondió dentro del tiempo límite") from exc
        except httpx.HTTPError as exc:
            raise JevError(f"Error de red llamando a JEV: {exc}") from exc
        latency = (time.perf_counter() - t0) * 1000
        if resp.status_code != 200:
            raise JevError(f"JEV respondió {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        answers = {qid: _parse_answer(a) for qid, a in data.get("answers", {}).items()}
        missing = set(questions) - set(answers)
        if missing:
            raise JevError(f"JEV no devolvió respuesta para: {sorted(missing)}")
        usage = data.get("usage", {})
        return JevResult(model=data.get("model", self.model), answers=answers,
                         input_tokens=int(usage.get("input_tokens", 0)),
                         output_tokens=int(usage.get("output_tokens", 0)),
                         latency_ms=latency, simulated=False)


# ---------------------------------------------------------------------------
# Simulador local
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


STOPWORDS = set(_norm(
    "para como este esta estos estas sobre desde hasta entre donde cuando quien quienes cual cuales "
    "tiene tienen hacer haga hace todos todas pero porque that with from this have will your sus nuestro "
    "nuestra nuestros nuestras usted ustedes ellos ellas tambien mucho muchos algun alguna cada otro otra "
    "envia enviar correo mensaje personas persona agente favor solo segun"
).split())


def _tokens(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z0-9]{4,}", _norm(text)) if w not in STOPWORDS}


def _count(text: str, terms: list[str]) -> int:
    return sum(1 for t in terms if _norm(t) in text)


def _clamp(x: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return max(lo, min(hi, x))


def _collect_text(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_collect_text(v) for k, v in obj.items() if k not in {"agent_id", "action_id"})
    if isinstance(obj, list):
        return " ".join(_collect_text(v) for v in obj)
    return str(obj) if obj is not None else ""


INJECTION_TERMS = ["ignora tus instrucciones", "ignora las instrucciones", "ignore previous", "ignore all",
                   "instrucciones anteriores", "system prompt", "como modelo de lenguaje", "eres un asistente",
                   "reenvia", "reenviar", "envia una copia", "copia oculta", "codigo de verificacion",
                   "credenciales", "tu contrasena", "verifica tu cuenta", "transfiere", "nueva instruccion",
                   "assistant:", "a todos los contactos"]
CONFIDENTIAL_TERMS = ["confidencial", "uso interno", "no compartir", "margen", "nuestros costos",
                      "facturacion de", "pipeline interno", "metricas internas", "precio interno"]
AGGRESSIVE_TERMS = ["idiota", "estupid", "basura", "inutil", "maldit", "imbecil", "ridicul", "patetic",
                    "callate", "mediocre"]
INFORMAL_TERMS = ["jaja", " bro", "parce", " xd", "q onda", "obvio", "rapidito", "porfa", ":p", "manito"]
WARM_TERMS = ["hola", "gracias", "saludos", "un abrazo", "quedo atent", "con gusto", "un gusto", "te escribo"]
PROMISE_TERMS = ["de descuento", "garantiz", "beca", "reembolso", "2x1", "precio especial", "te regalamos",
                 "empleo asegurado", "trabajo asegurado", "gratis de por vida", "sin costo el programa", "100% gratis"]
PRESSURE_TERMS = ["ultima oportunidad", "solo hoy", "urgente", "no te lo pierdas", "ahora o nunca",
                  "quedan pocos", "ultimos cupos", "corre", "antes de que sea tarde"]
PURPOSE_TERMS = {
    "follow_up": ["conversacion", "agendar", "reunion", "llamada", "propuesta", "seguimiento", "20 minutos",
                  "te interesa", "tu interes", "tu equipo", "calendly", "precio", "tus dudas", "resolver"],
    "event_invite": ["evento", "meetup", "lu.ma", "luma", "inscribete", "te esperamos", "webinar", "agenda del",
                     "cupos", "asistir", "invitacion"],
    "program": ["modulo", "clase", "entrega", "tarea", "sesion", "alumno", "cohorte", "mentor", "proyecto final"],
    "newsletter": ["edicion", "esta semana", "boletin", "newsletter", "lecturas", "lo que aprendimos", "tendencias"],
    "transactional": ["confirmacion", "tu acceso", "factura", "recibo", "tu inscripcion fue", "credenciales de acceso",
                      "restablecer"],
}
AI_TOPIC_TERMS = ["inteligencia artificial", " ia ", " ia.", " ia,", "automatiz", "datos", "modelo", "agentes",
                  "empresa", "lider", "adopcion", "caso", "aprendizaje", "herramienta", "productividad"]
FORBIDDEN_TOPIC_TERMS = ["elecciones", "partido", "candidato", "presidente", "votar", "religion", "dios",
                         "izquierda", "derecha politica"]
STRONG_CLAIM_TERMS = ["100%", "garantiz", "todos nuestros", "triplica", "duplica tus", "comprobado",
                      "el mejor", "unico en", "asegurado", "sin excepcion", "10x"]
FALSE_CLAIM_TERMS = ["estafa", "fraude", "mienten", "cura", "ilegal", "roban"]
NEGATIVE_TERMS = ["estafa", "fraude", "incompetente", "mediocre", "peor", "fracaso", "mienten", "roban",
                  "no sirve", "verguenza"]
CRISIS_TERMS = ["tragedia", "muertos", "atentado", "masacre", "escandalo"]


class SimulatedJev:
    """Aproximación heurística de JEV. Determinista: la misma entrada da la misma salida."""

    simulated = True

    def __init__(self, model: str = "jev-simulado", sleep: bool | None = None):
        self.model = model
        # Con JEV_SIM_LATENCY=1 se duerme una latencia realista (70-300 ms) para demos.
        self.sleep = sleep if sleep is not None else os.environ.get("JEV_SIM_LATENCY") == "1"

    def evaluate(self, state: dict[str, Any], questions: dict[str, dict]) -> JevResult:
        t0 = time.perf_counter()
        action = state.get("action", {})
        text = " " + _norm(_collect_text(action)) + " "
        ctx = _Ctx(state=state, action=action, text=text, raw_text=_collect_text(action))
        answers = {}
        for qid, q in questions.items():
            handler = getattr(self, f"_q_{qid}", None)
            answers[qid] = handler(ctx, q) if handler else self._fallback(q)
        if self.sleep:
            time.sleep((70 + self._seed(ctx.text, "lat") * 230) / 1000)
        latency = (time.perf_counter() - t0) * 1000
        return JevResult(model=self.model, answers=answers, input_tokens=estimate_tokens(state, questions),
                         output_tokens=len(questions) * 12, latency_ms=latency, simulated=True)

    # -- utilidades ----------------------------------------------------------

    @staticmethod
    def _seed(text: str, key: str) -> float:
        h = hashlib.sha256((key + text).encode()).digest()
        return int.from_bytes(h[:4], "big") / 2**32

    def _noul(self, p: float, ctx: "_Ctx", qid: str) -> JevAnswer:
        jitter = (self._seed(ctx.text, qid) - 0.5) * 0.06
        return JevAnswer(type="noul", noul=round(_clamp(p + jitter), 3))

    def _score(self, level: float, n: int, spread: float = 0.6) -> JevAnswer:
        weights = [math.exp(-((i - level) ** 2) / (2 * spread**2)) for i in range(n)]
        total = sum(weights)
        probs = [w / total for w in weights]
        score = sum(i * p for i, p in enumerate(probs))
        return JevAnswer(type="score", score=round(score, 3), confidence=round(score_confidence(probs), 3),
                         probabilities={str(i): round(p, 3) for i, p in enumerate(probs)})

    def _choice(self, scores: dict[str, float], temperature: float = 0.8) -> JevAnswer:
        mx = max(scores.values())
        exps = {k: math.exp((v - mx) / temperature) for k, v in scores.items()}
        total = sum(exps.values())
        probs = {k: v / total for k, v in exps.items()}
        best = max(probs, key=probs.get)
        return JevAnswer(type="choice", choice=best, confidence=round(choice_confidence(list(probs.values())), 3),
                         probabilities={k: round(v, 3) for k, v in probs.items()})

    def _fallback(self, q: dict) -> JevAnswer:
        if q["type"] == "noul":
            return JevAnswer(type="noul", noul=0.5)
        if q["type"] == "score":
            return self._score((len(q["criteria"]) - 1) / 2, len(q["criteria"]), spread=3.0)
        return self._choice({k: 0.0 for k in q["criteria"]})

    # -- preguntas comunes ---------------------------------------------------

    def _q_goal_alignment(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        task = _tokens(ctx.state.get("task", ""))
        content = _tokens(ctx.raw_text)
        overlap = len(task & content) / max(len(task), 1)
        p = 0.4 + 0.58 * min(1.0, overlap * 2.2)
        if _count(ctx.text, INJECTION_TERMS):
            p *= 0.35
        return self._noul(p, ctx, q.get("_id", "goal"))

    def _q_injection_signs(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        task = " " + _norm(ctx.state.get("task", "")) + " "
        hits = _count(ctx.text, INJECTION_TERMS) + _count(task, INJECTION_TERMS)
        return self._noul(0.04 + 0.42 * hits, ctx, "inj")

    def _q_confidential_leak(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        entities = ctx.state.get("context", {}).get("confidential_entities", [])
        p = 0.05 + 0.85 * bool(_count(ctx.text, entities)) + 0.35 * _count(ctx.text, CONFIDENTIAL_TERMS)
        return self._noul(p, ctx, "conf")

    def _q_tone(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        n = len(q["criteria"])
        if _count(ctx.text, AGGRESSIVE_TERMS):
            return self._score(3, n, 0.5)
        informal = _count(ctx.text, INFORMAL_TERMS) + ctx.raw_text.count("!!!") + _shouting(ctx.raw_text)
        if informal >= 2:
            return self._score(2.1, n, 0.6)
        if informal == 1:
            return self._score(1.5, n, 0.8)
        if _count(ctx.text, WARM_TERMS):
            return self._score(0.1, n, 0.5)
        return self._score(0.9, n, 0.6)

    # -- correo --------------------------------------------------------------

    def _q_unoffered_promise(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        text = ctx.text
        hits = _count(text, PROMISE_TERMS)
        percents = [int(m) for m in re.findall(r"(\d{1,3})\s*%", text)]
        allowed_code = "early10" in text
        hits += sum(1 for pct in percents if not (allowed_code and pct == 10))
        return self._noul(0.05 + 0.42 * hits, ctx, "promise")

    def _q_pressure_tactics(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        hits = _count(ctx.text, PRESSURE_TERMS) + ctx.raw_text.count("!!!") + _shouting(ctx.raw_text)
        return self._noul(0.05 + 0.33 * hits, ctx, "pressure")

    def _q_purpose(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        scores = {opt: float(_count(ctx.text, PURPOSE_TERMS.get(opt, []))) for opt in q["criteria"]}
        scores["other"] = 0.4
        return self._choice(scores, temperature=0.7)

    def _q_audience_fit(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        desc = _tokens(ctx.action.get("audience", {}).get("description", ""))
        content = _tokens(_collect_text({k: v for k, v in ctx.action.items() if k != "audience"}))
        overlap = len(desc & content) / max(len(desc), 1)
        return self._noul(0.35 + 0.63 * min(1.0, overlap * 2.5), ctx, "aud")

    # -- CRM -----------------------------------------------------------------

    def _q_change_supported(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        evidence = _norm(ctx.action.get("evidence", ""))
        changes = ctx.action.get("changes", {})
        if not evidence.strip():
            return self._noul(0.18, ctx, "sup")
        matched = sum(1 for v in changes.values() if _tokens(str(v)) & _tokens(evidence) or _norm(str(v)) in evidence)
        return self._noul(0.3 + 0.65 * matched / max(len(changes), 1), ctx, "sup")

    def _q_change_kind(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        changes = {k: _norm(str(v)) for k, v in ctx.action.get("changes", {}).items()}
        scores = {opt: 0.0 for opt in q["criteria"]}
        if "consent_marketing" in changes:
            scores["consent_change"] += 3
        if "owner_id" in changes:
            scores["reassignment"] += 3
        stage = changes.get("stage", "")
        if any(w in stage for w in ["lost", "perdid", "descart"]):
            scores["regression"] += 3
        elif stage:
            scores["progression"] += 3
        if ctx.action.get("previous") and not any(scores.values()):
            scores["correction"] += 2.5
        if not any(scores.values()):
            scores["enrichment"] += 2
        scores["other"] += 0.3
        return self._choice(scores, temperature=0.9)

    def _q_scope_matches_task(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        task = _norm(ctx.state.get("task", ""))
        count = ctx.state.get("facts", {}).get("record_count", 0) or 0
        numbers = [int(n) for n in re.findall(r"\b(\d{1,6})\b", task)]
        if any(w in task for w in ["todos", "todas", "toda la base", "cada uno"]):
            p = 0.8
        elif numbers:
            target = max(numbers)
            p = 0.9 if count <= target * 1.2 else 0.12
        elif re.search(r"\b(este|esta|el|la|del|al)\s+(contacto|lead|negocio|empresa|registro|deal)\b", task):
            p = 0.88 if count <= 1 else 0.08
        else:
            p = 0.75 if count <= 50 else 0.3
        return self._noul(p, ctx, "scope")

    def _q_deletion_justified(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        why = _norm(ctx.action.get("reason", "") + " " + ctx.action.get("evidence", ""))
        if any(w in why for w in ["duplicad", "solicit", "pidio", "habeas", "eliminar mis datos", "prueba", "test"]):
            p = 0.86
        elif any(w in why for w in ["inactiv", "antigu", "no abren", "limpieza", "viejos"]):
            p = 0.3
        else:
            p = 0.2
        return self._noul(p, ctx, "del")

    def _q_deletion_reason(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        why = _norm(ctx.action.get("reason", "") + " " + ctx.action.get("evidence", ""))
        scores = {opt: 0.0 for opt in q["criteria"]}
        scores["duplicate"] = 3.0 * ("duplicad" in why)
        scores["data_subject_request"] = 3.0 * any(w in why for w in ["solicit", "pidio", "habeas", "mis datos"])
        scores["test_data"] = 3.0 * any(w in why for w in ["prueba", "test"])
        scores["cleanup_inactive"] = 3.0 * any(w in why for w in ["inactiv", "antigu", "limpieza", "no abren"])
        scores["other"] = 0.8
        return self._choice(scores, temperature=0.9)

    # -- contenido -----------------------------------------------------------

    def _q_editorial_fit(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        on_topic = _count(ctx.text, AI_TOPIC_TERMS)
        forbidden = _count(ctx.text, FORBIDDEN_TOPIC_TERMS)
        p = 0.3 + 0.17 * min(on_topic, 4) - 0.35 * forbidden
        return self._noul(p, ctx, "edit")

    def _q_claims_risk(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        n = len(q["criteria"])
        if _count(ctx.text, FALSE_CLAIM_TERMS):
            return self._score(3, n, 0.6)
        strong = _count(ctx.text, STRONG_CLAIM_TERMS)
        if strong >= 2:
            return self._score(2.4, n, 0.5)
        if strong == 1:
            return self._score(1.8, n, 0.7)
        if re.search(r"\d+\s*%|\d{2,}", ctx.text):
            return self._score(1.0, n, 0.6)
        return self._score(0.2, n, 0.5)

    def _q_third_party_negative(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        return self._noul(0.05 + 0.4 * _count(ctx.text, NEGATIVE_TERMS), ctx, "neg")

    def _q_controversy(self, ctx: "_Ctx", q: dict) -> JevAnswer:
        n = len(q["criteria"])
        if _count(ctx.text, CRISIS_TERMS) or _count(ctx.text, NEGATIVE_TERMS) >= 2:
            return self._score(2.8, n, 0.6)
        if _count(ctx.text, FORBIDDEN_TOPIC_TERMS):
            return self._score(2.0, n, 0.6)
        if "polemic" in ctx.text or "opinion impopular" in ctx.text:
            return self._score(1.0, n, 0.6)
        return self._score(0.1, n, 0.5)


def _shouting(raw: str) -> int:
    words = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{4,}", raw)]
    if not words:
        return 0
    upper = sum(1 for w in words if w.isupper())
    return 1 if upper / len(words) > 0.3 and upper >= 3 else 0


class _Ctx:
    __slots__ = ("state", "action", "text", "raw_text")

    def __init__(self, state, action, text, raw_text):
        self.state, self.action, self.text, self.raw_text = state, action, text, raw_text


def make_backend(model: str = "jev-latest", timeout_s: float = 1.5, force_simulated: bool = False) -> JevBackend:
    """Usa JEV real si hay TYPESAFE_API_KEY; si no, el simulador."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if key and not force_simulated and os.environ.get("JEV_GUARD_SIMULATE") != "1":
        return TypeSafeJev(api_key=key, model=model, timeout_s=timeout_s)
    return SimulatedJev()

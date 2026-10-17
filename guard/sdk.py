"""Integración para agentes: envolver cualquier herramienta con el guardián.

    guard = GuardClient("http://127.0.0.1:8000")      # o LocalGuard() en el mismo proceso

    @guarded(guard, "email.send", agent_id="agente-seguimiento")
    def send_email(*, task, to, subject, body, purpose):
        return proveedor_de_correo.send(to, subject, body)

    send_email(task="...", to=[...], subject="...", body="...", purpose="follow_up")
    # -> ejecuta si allow; lanza ActionBlocked si block; ActionHeld si hold.

Los argumentos de la herramienta son los campos de la acción, así que el agente
no necesita aprender un formato nuevo.
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, Protocol

import httpx

from .models import Decision


class ActionBlocked(RuntimeError):
    def __init__(self, decision: Decision):
        self.decision = decision
        reasons = "; ".join(r.message for r in decision.reasons[:3]) or "sin detalle"
        super().__init__(f"Acción bloqueada por JEV Guard ({decision.decision_id}): {reasons}")


class ActionHeld(RuntimeError):
    def __init__(self, decision: Decision):
        self.decision = decision
        super().__init__(f"Acción retenida para revisión humana ({decision.decision_id})")


class Guard(Protocol):
    def check(self, action: dict[str, Any]) -> Decision: ...
    def status(self, decision_id: str) -> str | None: ...


class GuardClient:
    """Cliente HTTP para la API de JEV Guard."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout_s: float = 5.0):
        self._http = httpx.Client(base_url=base_url, timeout=timeout_s)

    def check(self, action: dict[str, Any]) -> Decision:
        resp = self._http.post("/v1/guard/check", json=action)
        resp.raise_for_status()
        return Decision.model_validate(resp.json())

    def status(self, decision_id: str) -> str | None:
        """Veredicto final tras la revisión humana, o None si sigue pendiente."""
        row = self._http.get(f"/v1/decisions/{decision_id}").json()
        return row.get("final_verdict")


class LocalGuard:
    """El guardián en el mismo proceso del agente (sin red)."""

    def __init__(self, service=None):
        from .service import GuardService

        self.service = service or GuardService()

    def check(self, action: dict[str, Any]) -> Decision:
        return self.service.check(action)

    def status(self, decision_id: str) -> str | None:
        row = self.service.store.get(decision_id)
        return row.get("final_verdict") if row else None


def guarded(guard: Guard, action_type: str, *, agent_id: str, wait_for_human_s: float = 0.0,
            poll_s: float = 2.0) -> Callable:
    """Decorador: verifica la acción antes de ejecutar la herramienta.

    Con `wait_for_human_s` > 0 el agente espera la revisión humana hasta ese tiempo;
    si no, recibe ActionHeld y puede seguir con otra tarea.
    """

    def wrap(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def inner(**kwargs):
            decision = guard.check({"agent_id": agent_id, "action_type": action_type, **kwargs})
            if decision.verdict.value == "allow":
                return fn(**kwargs)
            if decision.verdict.value == "block":
                raise ActionBlocked(decision)
            deadline = time.monotonic() + wait_for_human_s
            while time.monotonic() < deadline:
                final = guard.status(decision.decision_id)
                if final == "allow":
                    return fn(**kwargs)
                if final == "block":
                    raise ActionBlocked(decision)
                time.sleep(poll_s)
            raise ActionHeld(decision)

        return inner

    return wrap

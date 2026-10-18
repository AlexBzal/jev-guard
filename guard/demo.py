"""Generador de tráfico para la demo: los agentes de 30X trabajando dentro del servidor.

Usa los casos de data/scenarios*.yaml como plantillas. Los seguros pesan más, como en
la operación real. Cada decisión queda etiquetada con la verdad de la plantilla
(fuente "dataset") para que el tablero muestre métricas de calidad desde el primer
minuto. Las retenidas quedan en la bandeja para que una persona las resuelva en vivo.
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from .config import ROOT

log = logging.getLogger(__name__)


def load_scenarios(data_dir: Path = ROOT / "data") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("scenarios*.yaml")):
        out += yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return out


class TrafficGenerator:
    def __init__(self, service, scenarios: list[dict[str, Any]], safe_weight: float = 4.0, seed: int | None = None,
                 max_seconds: float | None = None):
        self.service = service
        self.scenarios = scenarios
        self.weights = [safe_weight if s["safe"] else 1.0 for s in scenarios]
        self.rng = random.Random(seed)
        self.rate = 3.0
        self.sent = 0
        # En un despliegue público nadie debe poder dejar a los agentes encendidos para siempre.
        self.max_seconds = max_seconds if max_seconds is not None else float(os.environ.get("JEV_GUARD_TRAFFIC_MAX_S", 600))
        self._started = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict[str, Any]:
        remaining = max(0.0, self.max_seconds - (time.monotonic() - self._started)) if self.running else None
        return {"running": self.running, "rate": self.rate, "sent": self.sent, "max_seconds": self.max_seconds,
                "remaining_s": round(remaining) if remaining is not None else None}

    def start(self, rate: float) -> dict[str, Any]:
        with self._lock:
            self.rate = max(0.2, min(float(rate), 30.0))
            self._started = time.monotonic()  # arrancar o cambiar el ritmo renueva el plazo
            if not self.running:
                self._stop.clear()
                self._thread = threading.Thread(target=self._run, name="jev-guard-traffic", daemon=True)
                self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        return self.status()

    def _run(self) -> None:
        while not self._stop.is_set():
            if time.monotonic() - self._started > self.max_seconds:
                log.info("Tráfico simulado detenido tras %.0f s", self.max_seconds)
                break
            tpl = self.rng.choices(self.scenarios, weights=self.weights)[0]
            action = dict(tpl["action"], action_id=f"act_{uuid.uuid4().hex[:12]}")
            try:
                decision = self.service.check(action, source=tpl["id"])
                self.service.store.label(decision.decision_id, tpl["safe"], reviewer="dataset",
                                         note=tpl["id"], source="dataset")
                self.sent += 1
            except Exception:  # la demo no debe morir por un caso malformado
                log.exception("Falló la plantilla %s", tpl.get("id"))
            self._stop.wait(1 / self.rate)

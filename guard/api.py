"""API HTTP de JEV Guard.

Cualquier agente (Python, n8n, Make, LangChain, un webhook) llama a
POST /v1/guard/check antes de ejecutar una acción y obedece el veredicto:
allow -> ejecuta, block -> no ejecuta, hold -> espera la revisión humana.

Ejecutar:  uvicorn guard.api:app --reload
Interfaz:  http://127.0.0.1:8000/          Docs: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from .config import ROOT
from .demo import TrafficGenerator, load_scenarios
from .models import ACTION_TYPES, Decision, LabelInput, ReviewInput
from .questions import QUESTION_SETS
from .service import GuardService
from .store import DecisionStore

DEMO_CLOCK = "2026-10-16T10:00:00-05:00"  # la hora de referencia de los casos de evaluación

EXAMPLE_ACTION = {
    "agent_id": "agente-seguimiento",
    "action_type": "email.send",
    "task": "Haz seguimiento a Andrea, que asistió al meetup de IA en finanzas, y propón una conversación de 20 minutos",
    "to": ["andrea.lopez@fintech-demo.example"],
    "subject": "Gracias por venir al meetup de IA en finanzas",
    "body": "Hola Andrea, gracias por asistir al meetup. Si te interesa, agendemos 20 minutos para ver cómo tu equipo puede aplicar IA. Un abrazo, equipo 30X",
    "purpose": "follow_up",
}


class TrafficInput(BaseModel):
    running: bool
    rate: float = Field(default=3.0, ge=0.2, le=30)


def create_app(service: GuardService | None = None) -> FastAPI:
    demo = os.environ.get("JEV_GUARD_DEMO") == "1"
    if demo and not os.environ.get("JEV_GUARD_NOW"):
        # En la demo el reloj se fija para que horarios e historial coincidan con los casos.
        os.environ["JEV_GUARD_NOW"] = DEMO_CLOCK
    if service is None:
        db = os.environ.get("JEV_GUARD_DB", str(ROOT / "data" / "runtime" / "guard.db"))
        service = GuardService(store=DecisionStore(db))

    scenarios = load_scenarios()
    traffic = TrafficGenerator(service, scenarios)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        traffic.stop()

    app = FastAPI(
        lifespan=lifespan,
        title="JEV Guard",
        version="0.2.0",
        description="Guardián en tiempo real para agentes internos de 30X, construido sobre JEV (TypeSafe AI).",
    )
    app.state.guard = service
    app.state.traffic = traffic
    app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("JEV_GUARD_CORS", "*").split(","),
                       allow_methods=["*"], allow_headers=["*"])

    # -- sistema ---------------------------------------------------------------

    @app.get("/health", tags=["sistema"])
    def health() -> dict[str, Any]:
        return {"status": "ok", **service.mode, "demo": demo, "clock": os.environ.get("JEV_GUARD_NOW"),
                "traffic": traffic.status(), "subscribers": service.events.subscribers}

    @app.get("/v1/policy", tags=["sistema"], summary="Política activa y catálogo de preguntas a JEV")
    def policy():
        return {
            "policy": service.policy.model_dump(mode="json"),
            "questions": {t: [{"qid": s.qid, "label": s.label, "short": s.short, "weight": s.weight, "critical": s.critical,
                               "question": s.question} for s in QUESTION_SETS[t]] for t in ACTION_TYPES},
        }

    @app.get("/v1/scenarios", tags=["sistema"], summary="Casos preparados (datos simulados)")
    def list_scenarios():
        return [{"id": s["id"], "title": s["title"], "safe": s["safe"], "expected": s["expected"],
                 "why": s.get("why", ""), "action_type": s["action"]["action_type"],
                 "agent_id": s["action"]["agent_id"], "action": s["action"]} for s in scenarios]

    # -- guardián ----------------------------------------------------------------

    @app.post("/v1/guard/check", response_model=Decision, tags=["guardián"],
              summary="Evalúa una acción antes de que el agente la ejecute")
    def check(action: dict[str, Any] = Body(..., examples=[EXAMPLE_ACTION]),
              sandbox: bool = Query(False, description="Prueba: no se guarda ni cuenta en métricas")) -> Decision:
        try:
            return service.check(action, persist=not sandbox)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc

    @app.get("/v1/stream", tags=["guardián"], summary="Flujo en vivo de decisiones (Server-Sent Events)")
    async def stream(request: Request):
        sub = service.events.subscribe(asyncio.get_running_loop())

        async def events():
            try:
                yield "retry: 2000\n\n"
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(sub[1].get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            finally:
                service.events.unsubscribe(sub)

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # -- auditoría y revisión ------------------------------------------------------

    @app.get("/v1/decisions", tags=["auditoría"])
    def list_decisions(status: str | None = None, verdict: str | None = None, action_type: str | None = None,
                       agent_id: str | None = None, limit: int = Query(50, le=500), offset: int = 0):
        return service.store.list(status=status, verdict=verdict, action_type=action_type, agent_id=agent_id,
                                  limit=limit, offset=offset)

    @app.get("/v1/decisions/{decision_id}", tags=["auditoría"])
    def get_decision(decision_id: str):
        row = service.store.get(decision_id)
        if not row:
            raise HTTPException(404, "Decisión no encontrada")
        return row

    @app.get("/v1/reviews/pending", tags=["revisión humana"])
    def pending(limit: int = Query(50, le=500)):
        return service.store.list(status="pending_review", limit=limit)

    @app.post("/v1/reviews/{decision_id}", tags=["revisión humana"],
              summary="Una persona aprueba o rechaza una acción retenida")
    def review(decision_id: str, body: ReviewInput):
        row = service.store.resolve_review(decision_id, body.approve, body.reviewer, body.note)
        if not row:
            raise HTTPException(404, "No hay una revisión pendiente con ese id")
        service.events.publish({"type": "review", "decision_id": decision_id,
                                "final_verdict": row["final_verdict"], "reviewer": body.reviewer})
        return row

    @app.post("/v1/decisions/{decision_id}/label", tags=["auditoría"],
              summary="Etiqueta de auditoría (también sobre decisiones automáticas) para medir calidad")
    def label(decision_id: str, body: LabelInput):
        row = service.store.label(decision_id, body.safe, body.reviewer, body.note)
        if not row:
            raise HTTPException(404, "Decisión no encontrada")
        return row

    @app.get("/v1/metrics", tags=["métricas"])
    def metrics():
        return service.metrics()

    # -- solo demo -------------------------------------------------------------------

    if demo:
        @app.get("/v1/demo/traffic", tags=["demo"])
        def traffic_status():
            return traffic.status()

        @app.post("/v1/demo/traffic", tags=["demo"], summary="Arranca o detiene a los agentes simulados")
        def traffic_control(body: TrafficInput):
            return traffic.start(body.rate) if body.running else traffic.stop()

        @app.delete("/v1/decisions", tags=["demo"], summary="Borra el registro")
        def reset():
            traffic.stop()
            service.store.clear()
            service.events.publish({"type": "reset"})
            return {"status": "cleared"}

    # La interfaz (HTML + JS sin compilación) se sirve en la raíz, después de la API.
    ui_dir = ROOT / "ui"
    if (ui_dir / "index.html").exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")

    return app


def __getattr__(name: str):
    # `uvicorn guard.api:app` crea la app al primer acceso, no al importar el módulo.
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)

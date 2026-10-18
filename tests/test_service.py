from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from guard.api import create_app
from guard.jev import JevError, SimulatedJev
from guard.llm import LlmOpinion
from guard.models import Route, Verdict
from guard.sdk import ActionBlocked, ActionHeld, LocalGuard, guarded
from guard.service import GuardService
from guard.store import DecisionStore

from .conftest import NOW, email

ROOT = Path(__file__).resolve().parent.parent


class FailingJev:
    simulated = False

    def evaluate(self, state, questions):
        raise JevError("timeout")


class FakeLlm:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def review(self, payload):
        self.calls += 1
        return LlmOpinion(verdict=self.verdict, reason="razón", input_tokens=1000, output_tokens=50,
                          cost_usd=0.005, model="claude-opus-5-5")


def test_rules_block_skips_jev(service):
    d = service.check(email(to=["baja1@example.com"]), now=NOW)
    assert d.verdict == Verdict.BLOCK and d.route == Route.RULES
    assert d.jev_model is None and d.cost_usd == 0


def test_clean_email_allowed_and_audited(service):
    d = service.check(email(), now=NOW)
    assert d.verdict == Verdict.ALLOW and d.route == Route.JEV
    assert service.store.get(d.decision_id)["final_verdict"] == "allow"
    assert d.cost_usd > 0 and d.input_tokens > 0


def test_jev_failure_policy(policy, context):
    svc = GuardService(policy=policy, context=context, backend=FailingJev(), store=DecisionStore(), second_opinion=False)
    low = svc.check(email(), now=NOW)  # tier low: on_jev_error = allow
    assert low.verdict == Verdict.ALLOW and any(r.code == "jev_error" for r in low.reasons)
    big = svc.check({**email(), "to": [f"p{i}@demo.example" for i in range(20)]}, now=NOW)  # medium: hold
    assert big.verdict == Verdict.HOLD and big.status == "pending_review"


class UnsureJev(SimulatedJev):
    """JEV que duda de todo: probabilidades planas en cada pregunta."""

    def evaluate(self, state, questions):
        result = super().evaluate(state, questions)
        result.answers = {qid: self._fallback(q) for qid, q in questions.items()}
        return result


def test_llm_second_opinion_paths(policy, context):
    for llm_verdict, expected in (("allow", Verdict.ALLOW), ("block", Verdict.BLOCK), ("human", Verdict.HOLD)):
        llm = FakeLlm(llm_verdict)
        svc = GuardService(policy=policy, context=context, backend=UnsureJev(sleep=False),
                           store=DecisionStore(), second_opinion=llm)
        d = svc.check(email(), now=NOW)
        assert llm.calls == 1
        assert d.verdict == expected and d.llm_used
        assert d.route == (Route.HUMAN if llm_verdict == "human" else Route.LLM)
        assert d.cost_usd > 0.005


def test_doubt_without_llm_goes_to_human(policy, context):
    svc = GuardService(policy=policy, context=context, backend=UnsureJev(sleep=False),
                       store=DecisionStore(), second_opinion=False)
    d = svc.check(email(), now=NOW)
    assert d.verdict == Verdict.HOLD and any(r.code == "llm_unavailable" for r in d.reasons)


def test_doubt_on_high_tier_skips_llm(policy, context):
    llm = FakeLlm("allow")
    svc = GuardService(policy=policy, context=context, backend=UnsureJev(sleep=False),
                       store=DecisionStore(), second_opinion=llm)
    post = {"agent_id": "agente-contenido", "action_type": "content.publish", "task": "Publica el caso",
            "platform": "linkedin", "text": "Un caso de adopción de IA en logística."}
    d = svc.check(post, now=NOW)
    assert llm.calls == 0 and d.verdict == Verdict.HOLD


def test_hold_review_cycle(service):
    d = service.check(email(to=["carla.mendez@cliente-demo.example"]), now=NOW)
    assert d.verdict == Verdict.HOLD
    row = service.store.resolve_review(d.decision_id, approve=False, reviewer="ana", note="demasiados correos")
    assert row["final_verdict"] == "block" and row["label_safe"] is False
    assert service.store.resolve_review(d.decision_id, approve=True, reviewer="ana", note="") is None


def test_api_end_to_end(service):
    client = TestClient(create_app(service))
    assert client.get("/health").json()["jev"] == "simulated"
    r = client.post("/v1/guard/check", json=email())
    assert r.status_code == 200 and r.json()["verdict"] == "allow"
    held = client.post("/v1/guard/check", json=email(to=["carla.mendez@cliente-demo.example"])).json()
    pending = client.get("/v1/reviews/pending").json()
    assert [p["decision_id"] for p in pending] == [held["decision_id"]]
    assert client.post(f"/v1/reviews/{held['decision_id']}",
                       json={"approve": True, "reviewer": "ana"}).json()["final_verdict"] == "allow"
    assert client.post("/v1/guard/check", json={"action_type": "email.send"}).status_code == 422
    m = client.get("/v1/metrics").json()
    assert m["decisions"] == 2 and m["quality"]["labeled"] == 1
    assert "email.send" in client.get("/v1/policy").json()["questions"]


def test_sdk_decorator(service):
    guard = LocalGuard(service)
    sent = []

    @guarded(guard, "email.send", agent_id="agente-seguimiento")
    def send_email(**kwargs):
        sent.append(kwargs["to"])
        return "ok"

    base = {k: v for k, v in email().items() if k not in ("agent_id", "action_type")}
    assert send_email(**base) == "ok"
    try:
        send_email(**{**base, "to": ["baja1@example.com"]})
        raise AssertionError("debió bloquear")
    except ActionBlocked as exc:
        assert "baja" in str(exc)
    try:
        send_email(**{**base, "to": ["carla.mendez@cliente-demo.example"]})
        raise AssertionError("debió retener")
    except ActionHeld:
        pass
    assert sent == [base["to"]]


def test_scenarios_never_allow_unsafe_actions(service):
    scenarios = yaml.safe_load((ROOT / "profiles" / "demo" / "scenarios.yaml").read_text(encoding="utf-8"))
    known_simulator_gaps = {"cu-07"}  # paráfrasis de inyección que el simulador no reconoce (ver BITACORA)
    false_allows = [sc["id"] for sc in scenarios
                    if not sc["safe"] and service.check(dict(sc["action"]), now=NOW).verdict == Verdict.ALLOW]
    assert set(false_allows) <= known_simulator_gaps


def test_sandbox_does_not_persist_or_publish(service):
    seen = []
    service.events.publish = lambda e: seen.append(e)
    d = service.check(email(), now=NOW, persist=False)
    assert d.sandbox and service.store.get(d.decision_id) is None and seen == []
    service.check(email(), now=NOW)
    assert len(seen) == 1 and seen[0]["type"] == "decision"


def test_decision_summary(service):
    d = service.check(email(), now=NOW)
    assert d.summary.startswith("Correo a 1 persona")


def test_demo_endpoints(service, monkeypatch):
    import time

    monkeypatch.setenv("JEV_GUARD_DEMO", "1")
    monkeypatch.setenv("JEV_GUARD_NOW", "2026-10-16T10:00:00-05:00")
    client = TestClient(create_app(service))
    scenarios = client.get("/v1/scenarios").json()
    assert len(scenarios) >= 40 and {"id", "action", "safe"} <= set(scenarios[0])
    r = client.post("/v1/guard/check?sandbox=true", json=email()).json()
    assert r["sandbox"] and client.get("/v1/metrics").json()["decisions"] == 0
    assert client.post("/v1/demo/traffic", json={"running": True, "rate": 30}).json()["running"]
    deadline = time.time() + 5
    while service.metrics()["decisions"] < 3 and time.time() < deadline:
        time.sleep(0.1)
    assert client.post("/v1/demo/traffic", json={"running": False}).json()["running"] is False
    m = client.get("/v1/metrics").json()
    assert m["decisions"] >= 3 and m["quality"]["labeled"] == m["decisions"]
    assert sum(b["count"] for b in m["latency_hist"]) == m["decisions"]
    assert client.delete("/v1/decisions").json()["status"] == "cleared"


def test_traffic_stops_by_itself(service):
    import time

    from guard.demo import TrafficGenerator, load_scenarios

    gen = TrafficGenerator(service, load_scenarios(), max_seconds=0.3)
    gen.start(30)
    deadline = time.time() + 3
    while gen.running and time.time() < deadline:
        time.sleep(0.05)
    assert not gen.running and gen.sent >= 1


def test_ui_files_are_revalidated(service):
    client = TestClient(create_app(service))
    assert client.get("/").headers.get("cache-control") == "no-cache"
    assert client.get("/js/app.js").headers.get("cache-control") == "no-cache"
    assert "cache-control" not in client.get("/health").headers

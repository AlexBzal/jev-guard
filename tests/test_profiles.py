"""Pruebas de la parte genérica: perfiles, acciones personalizadas y configuración por empresa."""
import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from guard.api import create_app
from guard.config import ROOT, CustomActionSpec, QuestionSpec, deep_merge, load_context, load_policy
from guard.facts import FactEngine
from guard.jev import SimulatedJev
from guard.models import Route, Tier, Verdict, parse_action
from guard.questions import QuestionCatalog
from guard.service import GuardService
from guard.store import DecisionStore

from .conftest import NOW, bulk, email

REPLY = {
    "agent_id": "agente-soporte",
    "action_type": "support.reply",
    "task": "Responder el ticket de una clienta que no puede descargar sus facturas",
    "content": {
        "customer": "Panadería Demo",
        "subject": "No puedo descargar facturas",
        "ticket": "Hola, no puedo descargar mis facturas desde el panel, me sale un error.",
        "reply": "Hola, lamentamos el inconveniente con la descarga de tus facturas. Ya corregimos el error del "
                 "panel; vuelve a intentarlo y, si persiste, respóndenos y lo revisamos contigo.",
    },
}


def test_profiles_merge_defaults(policy):
    assert policy.profile == "demo"
    assert policy.tiers[Tier.LOW].block == 0.85              # viene de defaults.yaml
    assert "agente-soporte" in policy.agents                 # viene del perfil
    assert "support.reply" in policy.action_types
    other = load_policy(profile="30x")
    assert other.timezone == "America/Bogota" and "support.reply" not in other.action_types


def test_deep_merge():
    assert deep_merge({"a": {"x": 1, "y": 2}, "b": 1}, {"a": {"y": 3}, "b": [1]}) == {"a": {"x": 1, "y": 3}, "b": [1]}


def test_unknown_profile_is_explicit():
    with pytest.raises(FileNotFoundError, match="Perfiles disponibles"):
        load_policy(profile="no-existe")


@pytest.mark.parametrize("spec,message", [
    ({"qid": "q", "type": "noul", "instructions": "x", "label": "x"}, "risk"),
    ({"qid": "q", "type": "choice", "instructions": "x", "label": "x", "criteria": {"a": "A"}}, "other"),
    ({"qid": "q", "type": "score", "instructions": "x", "label": "x", "criteria": {"a": "A"}}, "lista"),
])
def test_question_spec_validation(spec, message):
    with pytest.raises(ValidationError, match=message):
        QuestionSpec.model_validate(spec)


def test_custom_action_cannot_shadow_builtin(policy):
    data = policy.model_dump(mode="json")
    data["custom_actions"] = {"email.send": CustomActionSpec(label="x").model_dump(mode="json")}
    with pytest.raises(ValidationError, match="estándar"):
        type(policy).model_validate(data)


def test_catalog_uses_profile_purposes_and_custom_questions(policy, context):
    catalog = QuestionCatalog(policy, context)
    purpose = next(s for s in catalog.sets["email.send"] if s.qid == "purpose")
    assert set(purpose.question["criteria"]) == set(context.email_purposes) | {"other"}
    qids = [s.qid for s in catalog.sets["support.reply"]]
    assert qids[:4] == ["goal_alignment", "injection_signs", "confidential_leak", "tone"]
    assert {"resolves_issue", "policy_promise", "blames_customer"} <= set(qids)


def test_no_company_names_in_generic_questions(policy, context):
    for signals in QuestionCatalog(policy, context).sets.values():
        for s in signals:
            text = s.question["instructions"] + s.label + s.short
            assert "30X" not in text and "Nimbus" not in text, s.qid


def test_unknown_purpose_blocks(policy, context):
    facts = FactEngine(policy, context).analyze(parse_action(email(purpose="program")), now=NOW)
    assert any(h.code == "E012" for h in facts.blocking)


def test_marketing_flag_drives_unsubscribe_rule(policy, context):
    engine = FactEngine(policy, context)
    body = "Hola {{first_name}}, cambia tu plan desde el panel."
    assert any(h.code == "B001" for h in engine.analyze(parse_action(bulk(purpose="newsletter", body=body)), now=NOW).hits)
    assert not any(h.code == "B001" for h in engine.analyze(parse_action(bulk(purpose="customer_update", body=body)), now=NOW).hits)


def test_custom_action_facts(policy, context):
    engine = FactEngine(policy, context)
    facts = engine.analyze(parse_action(REPLY), now=NOW)
    assert facts.hits == [] and facts.tier == Tier.LOW and facts.blast_radius == 1
    missing = engine.analyze(parse_action({**REPLY, "content": {"reply": "hola"}}), now=NOW)
    assert any(h.code == "X001" for h in missing.blocking)
    secret = engine.analyze(parse_action({**REPLY, "content": {**REPLY["content"], "reply": "tu clave: sk-abcdefghijklmnopqrstuvwxyz"}}), now=NOW)
    assert any(h.code == "T001" for h in secret.blocking)


def test_undeclared_custom_action_is_blocked(service):
    d = service.check({**REPLY, "action_type": "billing.refund"}, now=NOW)
    assert d.verdict == Verdict.BLOCK and d.route == Route.RULES
    assert "no está declarado" in d.reasons[0].message


def test_custom_action_end_to_end(service):
    ok = service.check(REPLY, now=NOW)
    assert ok.verdict == Verdict.ALLOW and ok.summary.startswith("Respuesta de soporte")
    bad = service.check({**REPLY, "content": {**REPLY["content"],
                         "reply": "Te devolvemos el dinero y te damos 3 meses gratis, inmediatamente."}}, now=NOW)
    assert bad.verdict in (Verdict.BLOCK, Verdict.HOLD)
    assert any(r.code == "policy_promise" for r in bad.reasons)


def test_custom_scope_from_field():
    spec = CustomActionSpec.model_validate({"label": "Mensaje en Slack", "scope": {"field": "members"},
                                            "fields": [{"name": "members"}, {"name": "text"}]})
    policy = load_policy(profile="demo")
    policy.custom_actions["slack.post"] = spec
    policy.agents["agente-soporte"].allowed.append("slack.post")
    facts = FactEngine(policy, load_context(profile="demo")).analyze(parse_action({
        "agent_id": "agente-soporte", "action_type": "slack.post", "task": "Avisa al canal",
        "content": {"members": 3500, "text": "Hola equipo"}}), now=NOW)
    assert facts.blast_radius == 3500 and facts.tier == Tier.CRITICAL


def test_30x_profile_still_works():
    policy, context = load_policy(profile="30x"), load_context(profile="30x")
    svc = GuardService(policy=policy, context=context, backend=SimulatedJev(sleep=False), store=DecisionStore(),
                       second_opinion=False)
    scenarios = yaml.safe_load((ROOT / "profiles" / "30x" / "scenarios.yaml").read_text(encoding="utf-8"))
    results = {sc["id"]: svc.check(dict(sc["action"]), now=NOW).verdict.value in sc["expected"] for sc in scenarios}
    assert all(results.values()), [k for k, v in results.items() if not v]


def test_profile_endpoint_and_agent_key(service, monkeypatch):
    monkeypatch.setenv("JEV_GUARD_API_KEY", "secreto")
    client = TestClient(create_app(service))
    prof = client.get("/v1/profile").json()
    assert prof["company"]["name"] == "Nimbus" and prof["auth_required"]
    assert "support.reply" in prof["custom_actions"] and "customer_update" in prof["email_purposes"]
    assert client.post("/v1/guard/check", json=email()).status_code == 401
    assert client.post("/v1/guard/check", json=email(), headers={"Authorization": "Bearer otro"}).status_code == 401
    assert client.post("/v1/guard/check", json=email(), headers={"Authorization": "Bearer secreto"}).status_code == 200
    assert client.post("/v1/guard/check?sandbox=true", json=email()).status_code == 200


def test_adoption_guide_examples_are_valid_config():
    """Los bloques YAML de docs/PERFILES.md deben ser configuración válida: la gente los copia."""
    import re

    from guard.config import DEFAULTS, PROFILES_DIR, Policy, _read_yaml

    doc = (ROOT / "docs" / "PERFILES.md").read_text(encoding="utf-8")
    over = {}
    for block in re.findall(r"```yaml\n(.*?)```", doc, re.S):
        over = deep_merge(over, yaml.safe_load(block))
    base = deep_merge(_read_yaml(DEFAULTS), _read_yaml(PROFILES_DIR / "demo" / "policy.yaml"))
    policy = Policy.model_validate(deep_merge(base, over))
    catalog = QuestionCatalog(policy, load_context(profile="demo"))
    assert "billing.refund" in catalog.sets and policy.tiers[Tier.HIGH].min_certainty == 0.6

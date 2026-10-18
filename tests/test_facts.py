from datetime import datetime

import pytest

from guard.facts import FactEngine, find_secrets
from guard.models import Tier, parse_action

from .conftest import NOW, bulk, email


@pytest.fixture
def engine(policy, context):
    return FactEngine(policy, context)


def codes(facts):
    return {h.code for h in facts.hits}


def test_clean_email_has_no_hits(engine):
    facts = engine.analyze(parse_action(email()), now=NOW)
    assert facts.hits == []
    assert facts.tier == Tier.LOW
    assert facts.values["recipient_count"] == 1


def test_suppressed_recipient_blocks(engine):
    facts = engine.analyze(parse_action(email(to=["baja1@example.com"])), now=NOW)
    assert "E001" in codes(facts) and facts.blocking


@pytest.mark.parametrize("body", ["Hola [NOMBRE], ¿cómo estás?", "Hola {{first_name}}", "Hola {nombre}",
                                  "TODO: escribir el cierre", "Lorem ipsum dolor"])
def test_placeholders_block_individual_email(engine, body):
    facts = engine.analyze(parse_action(email(body=body)), now=NOW)
    assert "T002" in codes(facts)


def test_spanish_word_todo_is_not_a_draft_marker(engine):
    facts = engine.analyze(parse_action(email(body="Hola Andrea, todo listo para el meetup. Saludos.")), now=NOW)
    assert "T002" not in codes(facts)


def test_allowed_merge_tags_in_bulk_are_fine(engine):
    facts = engine.analyze(parse_action(bulk()), now=NOW)
    assert "T002" not in codes(facts)


def test_unknown_merge_tag_in_bulk_blocks(engine):
    facts = engine.analyze(parse_action(bulk(body="Hola {{cargo}}. Para darte de baja: {{unsubscribe_url}}")), now=NOW)
    assert "T002" in codes(facts)


def test_bulk_without_unsubscribe_blocks(engine):
    facts = engine.analyze(parse_action(bulk(body="Hola {{first_name}}, ven al meetup.")), now=NOW)
    assert "B001" in codes(facts)


def test_audience_overshoot(engine):
    review = engine.analyze(parse_action(bulk(recipient_count=700)), now=NOW)
    block = engine.analyze(parse_action(bulk(recipient_count=5000)), now=NOW)
    assert any(h.code == "B002" and h.severity.value == "review" for h in review.hits)
    assert any(h.code == "B002" and h.severity.value == "block" for h in block.hits)


def test_two_keys_for_large_campaigns(engine):
    facts = engine.analyze(parse_action(bulk(recipient_count=6000, audience={
        "segment_id": "all", "description": "Toda la base", "expected_size": 6100})), now=NOW)
    assert facts.tier == Tier.CRITICAL and "B003" in codes(facts)


def test_quiet_hours_use_policy_timezone(engine):
    night = datetime.fromisoformat("2026-10-16T22:00:00-05:00")
    day = datetime.fromisoformat("2026-10-16T10:00:00-05:00")
    assert "E007" in codes(engine.analyze(parse_action(email(send_at=night.isoformat())), now=NOW))
    assert "E007" not in codes(engine.analyze(parse_action(email(send_at=day.isoformat())), now=NOW))
    # Los transaccionales están exentos.
    assert "E007" not in codes(engine.analyze(parse_action(email(send_at=night.isoformat(), purpose="transactional")), now=NOW))


def test_frequency_cap_and_duplicates(engine):
    cap = engine.analyze(parse_action(email(to=["carla.mendez@cliente-demo.example"])), now=NOW)
    dup = engine.analyze(parse_action(email(to=["diego.paz@cliente-demo.example"],
                                            subject="Seguimiento: tu prueba de Nimbus Pro")), now=NOW)
    assert "E006" in codes(cap)
    assert "E009" in codes(dup)


def test_links(engine):
    facts = engine.analyze(parse_action(email(body="Mira https://bit.ly/abc y https://malo.example/x y https://lu.ma/ok")), now=NOW)
    assert {"T003", "T004"} <= codes(facts)
    assert facts.values["external_domains"] == ["malo.example"]


def test_secrets_detection():
    assert "clave de API" in find_secrets("usa sk-abcdefghijklmnopqrstuvwx123")
    assert "número de tarjeta" in find_secrets("tarjeta 4111 1111 1111 1111")
    assert find_secrets("el número 1234 5678 9012 3456 no pasa Luhn") == []


def test_agent_permissions(engine):
    wrong = engine.analyze(parse_action(email(agent_id="agente-contenido")), now=NOW)
    unknown = engine.analyze(parse_action(email(agent_id="nadie")), now=NOW)
    assert "G002" in codes(wrong)
    assert "G001" in codes(unknown)


def test_crm_update_rules(engine):
    action = parse_action({
        "agent_id": "agente-crm", "action_type": "crm.update", "task": "Corrige el monto", "object": "deal",
        "record_ids": ["d1"], "changes": {"deal_amount": 1000}, "previous": {"deal_amount": 10000}, "evidence": "x"})
    facts = engine.analyze(action, now=NOW)
    assert {"C001", "C002"} <= codes(facts)
    assert facts.tier == Tier.MEDIUM  # low + campo protegido


def test_crm_without_scope_blocks(engine):
    action = parse_action({"agent_id": "agente-crm", "action_type": "crm.update", "task": "x", "object": "contact",
                           "record_count": 0, "changes": {"priority": "alta"}})
    assert "C003" in codes(engine.analyze(action, now=NOW))


def test_publish_length_and_pii(engine):
    long_post = parse_action({"agent_id": "agente-contenido", "action_type": "content.publish", "task": "x",
                              "platform": "x", "text": "a" * 281})
    pii = parse_action({"agent_id": "agente-contenido", "action_type": "content.publish", "task": "x",
                        "platform": "linkedin", "text": "Llámala al +57 310 555 0199"})
    assert "P001" in codes(engine.analyze(long_post, now=NOW))
    assert "P006" in codes(engine.analyze(pii, now=NOW))


def test_third_party_emails_in_body(engine):
    body = "Listado: a@x.example, b@x.example, c@x.example"
    facts = engine.analyze(parse_action(email(body=body)), now=NOW)
    assert "E011" in codes(facts) and facts.values["third_party_emails_in_body"] == 3


def test_program_bulk_does_not_need_unsubscribe(engine):
    facts = engine.analyze(parse_action(bulk(purpose="customer_update", body="Hola {{first_name}}, ya está la guía.")), now=NOW)
    assert "B001" not in codes(facts)


def test_deleting_deals_requires_human(engine):
    action = parse_action({"agent_id": "agente-crm", "action_type": "crm.delete", "task": "x", "object": "deal",
                           "record_ids": ["d1"], "reason": "duplicado", "evidence": "mismo nombre"})
    assert "C007" in codes(engine.analyze(action, now=NOW))


@pytest.mark.parametrize("text,flagged", [
    ("El 97% de los egresados recibió un ascenso.", True),
    ("Los equipos multiplican su productividad.", True),
    ("Según el informe de McKinsey, el 60% de las empresas usa IA.", False),
    ("Meetup de 30X este jueves: https://lu.ma/30x-agentes", False),
])
def test_stats_without_source(engine, text, flagged):
    action = parse_action({"agent_id": "agente-contenido", "action_type": "content.publish", "task": "x",
                           "platform": "linkedin", "text": text})
    assert ("P007" in codes(engine.analyze(action, now=NOW))) is flagged

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard.config import load_context, load_policy  # noqa: E402
from guard.jev import SimulatedJev  # noqa: E402
from guard.service import GuardService  # noqa: E402
from guard.store import DecisionStore  # noqa: E402

NOW = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)  # 10:00 en Bogotá


@pytest.fixture
def policy():
    return load_policy()


@pytest.fixture
def context():
    return load_context()


@pytest.fixture
def service(policy, context):
    return GuardService(policy=policy, context=context, backend=SimulatedJev(sleep=False),
                        store=DecisionStore(), second_opinion=False)


def email(**over):
    base = {
        "agent_id": "agente-seguimiento",
        "action_type": "email.send",
        "task": "Haz seguimiento a Andrea, que asistió al meetup de IA en finanzas, y propón una conversación",
        "to": ["andrea.lopez@fintech-demo.example"],
        "subject": "Gracias por venir al meetup de IA en finanzas",
        "body": "Hola Andrea, gracias por asistir al meetup de IA en finanzas. ¿Agendamos una conversación? Saludos.",
        "purpose": "follow_up",
    }
    base.update(over)
    return base


def bulk(**over):
    base = {
        "agent_id": "agente-campanas",
        "action_type": "email.bulk",
        "task": "Invita al segmento de líderes de finanzas al meetup de IA en finanzas",
        "audience": {"segment_id": "seg-fin", "description": "Líderes de finanzas interesados en IA", "expected_size": 400},
        "recipient_count": 380,
        "subject": "Meetup de IA en finanzas",
        "body": "Hola {{first_name}}, te invitamos al meetup de IA en finanzas: https://lu.ma/x. Para darte de baja: {{unsubscribe_url}}",
        "purpose": "event_invite",
    }
    base.update(over)
    return base

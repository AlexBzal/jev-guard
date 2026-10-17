import json

import httpx
import pytest

from guard.jev import JevError, SimulatedJev, TypeSafeJev, choice_confidence, score_confidence
from guard.questions import QUESTION_SETS, questions_payload

# Respuesta de ejemplo tomada de la guía de inicio rápido de TypeSafe.
DOC_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "department": {"type": "choice", "choice": "technical", "confidence": 1.0,
                       "probabilities": {"technical": 1.0, "billing": 0.0, "sales": 0.0}},
        "frustration": {"type": "score", "score": 0.67, "confidence": 0.5,
                        "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
                        "probabilities": {"0": 0.33, "1": 0.67, "2": 0.0}},
        "is_urgent": {"type": "noul", "noul": 0.99},
    },
    "usage": {"input_tokens": 428, "output_tokens": 73},
}
QUESTIONS = {"department": {"type": "choice"}, "frustration": {"type": "score"}, "is_urgent": {"type": "noul"}}


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_typesafe_request_and_parsing():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=DOC_RESPONSE)

    jev = TypeSafeJev(api_key="k", client=client_with(handler))
    result = jev.evaluate({"x": 1}, QUESTIONS)
    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
    assert seen["body"]["model"] == "jev-latest" and seen["body"]["questions"] == QUESTIONS
    assert result.answers["department"].choice == "technical"
    assert result.answers["frustration"].probabilities["1"] == 0.67
    assert result.answers["is_urgent"].noul == 0.99
    assert result.input_tokens == 428 and not result.simulated


def test_typesafe_errors():
    with pytest.raises(JevError):
        TypeSafeJev(api_key="k", client=client_with(lambda r: httpx.Response(500, text="boom"))).evaluate({}, QUESTIONS)
    partial = {**DOC_RESPONSE, "answers": {"is_urgent": {"type": "noul", "noul": 0.5}}}
    with pytest.raises(JevError):
        TypeSafeJev(api_key="k", client=client_with(lambda r: httpx.Response(200, json=partial))).evaluate({}, QUESTIONS)

    def timeout(request):
        raise httpx.ReadTimeout("lento", request=request)

    with pytest.raises(JevError):
        TypeSafeJev(api_key="k", client=client_with(timeout)).evaluate({}, QUESTIONS)


def test_confidence_formulas_match_docs():
    # Ejemplos de docs.typesafe.ai/confidence
    assert choice_confidence([0.6, 0.3, 0.1]) == pytest.approx(0.4)
    assert score_confidence([0, 0.57, 0.43]) == pytest.approx(0.355, abs=0.01)
    assert score_confidence([0, 0.5, 0.5]) == pytest.approx(0.25)
    assert score_confidence([0.5, 0, 0.5]) == pytest.approx(0.0)


def test_simulator_answers_every_question_and_is_deterministic():
    for action_type, signals in QUESTION_SETS.items():
        qs = questions_payload(signals)
        state = {"task": "t", "action": {"text": "hola"}, "facts": {}, "context": {}}
        a = SimulatedJev(sleep=False).evaluate(state, qs)
        b = SimulatedJev(sleep=False).evaluate(state, qs)
        assert set(a.answers) == set(qs), action_type
        assert a.answers == b.answers


def test_every_choice_question_has_other_option():
    for signals in QUESTION_SETS.values():
        for s in signals:
            if s.question["type"] == "choice":
                assert "other" in s.question["criteria"], s.qid

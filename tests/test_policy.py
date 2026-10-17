from guard.models import Facts, JevAnswer, RuleHit, Severity, SignalReading, Tier
from guard.policy import Intent, PolicyEngine


def reading(qid, risk, certainty, weight=0.8, critical=False):
    return SignalReading(qid=qid, label=qid, risk=risk, certainty=certainty, weight=weight, critical=critical,
                         raw=JevAnswer(type="noul", noul=risk))


def facts(tier=Tier.LOW, hits=None):
    return Facts(tier=tier, blast_radius=1, reversible=False, hits=hits or [])


def test_noise_does_not_accumulate(policy):
    engine = PolicyEngine(policy)
    weak = [reading(f"q{i}", 0.15, 0.7) for i in range(10)]
    assert engine.composite(weak) == 0.0
    assert engine.decide(facts(), weak).intent == Intent.ALLOW


def test_one_strong_certain_signal_blocks(policy):
    out = PolicyEngine(policy).decide(facts(), [reading("promise", 0.97, 0.94, weight=0.9)])
    assert out.intent == Intent.BLOCK


def test_strong_but_uncertain_signal_escalates(policy):
    engine = PolicyEngine(policy)
    sig = [reading("promise", 0.99, 0.2, weight=1.0)]
    assert engine.decide(facts(Tier.LOW), sig).intent == Intent.LLM
    assert engine.decide(facts(Tier.HIGH), sig).intent == Intent.HUMAN


def test_critical_signal_blocks_regardless_of_weights(policy):
    out = PolicyEngine(policy).decide(facts(Tier.LOW), [reading("injection_signs", 0.8, 0.6, weight=0.1, critical=True)])
    assert out.intent == Intent.BLOCK


def test_rule_review_goes_to_human(policy):
    hit = RuleHit(code="E006", severity=Severity.REVIEW, message="tope")
    out = PolicyEngine(policy).decide(facts(hits=[hit]), [reading("ok", 0.05, 0.9)])
    assert out.intent == Intent.HUMAN


def test_rules_only_short_circuit(policy):
    hit = RuleHit(code="E001", severity=Severity.BLOCK, message="baja")
    out = PolicyEngine(policy).rules_only(facts(hits=[hit]))
    assert out.intent == Intent.BLOCK and out.decided_by == "rules"


def test_thresholds_tighten_with_tier(policy):
    engine = PolicyEngine(policy)
    moderate = [reading("tone", 0.6, 0.9, weight=0.7)]
    assert engine.decide(facts(Tier.LOW), moderate).intent == Intent.ALLOW
    assert engine.decide(facts(Tier.CRITICAL), moderate).intent == Intent.HUMAN


def test_uncertain_band_escalates(policy):
    out = PolicyEngine(policy).decide(facts(Tier.MEDIUM), [reading("audience_fit", 0.5, 0.1, weight=0.5)])
    assert out.intent == Intent.LLM


def test_single_strong_signal_can_block_even_with_weight_below_threshold(policy):
    # peso 0,85 y umbral de bloqueo 0,85 en tier bajo: antes el compuesto quedaba en 0,84 y no frenaba
    out = PolicyEngine(policy).decide(facts(Tier.LOW), [reading("unoffered_promise", 0.99, 0.98, weight=0.85)])
    assert out.intent == Intent.BLOCK


def test_strong_signal_rule_respects_certainty(policy):
    out = PolicyEngine(policy).decide(facts(Tier.HIGH), [reading("claims", 0.9, 0.3, weight=0.8)])
    assert out.intent == Intent.HUMAN

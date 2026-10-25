from __future__ import annotations

import pytest

from governance_hub.conditions import Context, RuleError, holds
from governance_hub.engine import assess, load_rules, review_months
from tests.conftest import make

PEOPLE = {"data_categories": ["personal"], "people_regions": ["EU"], "org_regions": ["EU"]}


def test_everyday_drafting_is_minimal_and_low() -> None:
    a = assess(make(use_area="general_productivity"))
    assert (a.tier, a.level, a.score) == ("minimal", "low", 0)
    assert a.regimes == []


def test_emotion_recognition_at_work_is_prohibited() -> None:
    a = assess(make(use_area="emotion_recognition", flags=["workplace_or_education"], data_categories=["biometric"]))
    assert a.tier == "prohibited" and a.level == "prohibited"
    assert a.prohibited[0].source == "EU AI Act Art. 5(1)(f)"
    assert a.controls == []


def test_emotion_recognition_for_safety_is_high_risk_not_banned() -> None:
    a = assess(make(use_area="emotion_recognition", flags=["workplace_or_education", "medical_or_safety_reason"]))
    assert a.tier == "high" and a.annex_point == "Annex III 1(c)"
    assert any(t.id == "art50_3" for t in a.transparency)


@pytest.mark.parametrize(
    ("flag", "source"),
    [("manipulative", "5(1)(a)"), ("exploits_vulnerability", "5(1)(b)"), ("social_scoring", "5(1)(c)"), ("crime_prediction_profiling", "5(1)(d)"),
     ("face_scraping", "5(1)(e)"), ("real_time_public_biometric", "5(1)(h)")],
)  # fmt: skip
def test_each_article_5_flag_blocks(flag: str, source: str) -> None:
    a = assess(make(flags=[flag]))
    assert a.tier == "prohibited" and source in a.prohibited[0].source


def test_inferring_sensitive_traits_from_biometrics_is_prohibited() -> None:
    a = assess(make(use_area="biometric_categorisation", flags=["infers_sensitive_traits"], data_categories=["biometric"]))
    assert a.prohibited[0].source.endswith("5(1)(g)")


def test_recruitment_is_high_risk_annex_iii_4a() -> None:
    a = assess(make(use_area="recruitment", flags=["about_individuals"], **PEOPLE))
    assert (a.tier, a.annex_area, a.annex_point, a.level) == ("high", "employment", "Annex III 4(a)", "high")
    assert any(d.id == "art26_11" for d in a.duties) and any(d.id == "art26_7" for d in a.duties)


def test_article_6_3_exception_without_profiling() -> None:
    a = assess(make(use_area="recruitment", flags=["narrow_procedural_task"]))
    assert a.tier == "minimal" and a.exception is not None and a.exception.source == "EU AI Act Art. 6(3)"


def test_profiling_overrides_the_article_6_3_exception() -> None:
    a = assess(make(use_area="recruitment", flags=["narrow_procedural_task", "profiling"]))
    assert a.tier == "high" and a.exception is None
    assert "always high-risk" in a.high_risk[0].explain


def test_biometric_verification_is_not_annex_iii() -> None:
    assert assess(make(use_area="biometric_verification", data_categories=["biometric"])).tier == "minimal"
    assert assess(make(use_area="biometric_identification", data_categories=["biometric"])).annex_point == "Annex III 1(a)"


def test_credit_scoring_only_for_people_and_not_fraud() -> None:
    assert assess(make(use_area="credit_scoring", flags=["about_individuals"])).annex_point == "Annex III 5(b)"
    assert assess(make(use_area="credit_scoring")).tier == "minimal"  # credit checks on companies
    assert assess(make(use_area="fraud_detection", flags=["about_individuals"])).tier == "minimal"


def test_only_life_and_health_insurance_pricing_is_high_risk() -> None:
    life = assess(make(purpose="Price life insurance policies", use_area="insurance_pricing", flags=["about_individuals"]))
    car = assess(make(purpose="Price car insurance from driving history", use_area="insurance_pricing", flags=["about_individuals"]))
    assert life.annex_point == "Annex III 5(c)" and car.tier == "minimal"
    assert any(d.id == "art27" for d in life.duties)


def test_chatbot_and_generated_media_carry_transparency_duties() -> None:
    bot = assess(make(use_area="customer_service", decision_mode="acts_with_review", affected=["customers"], **PEOPLE))
    img = assess(make(use_area="content_generation"))
    assert bot.tier == "limited" and [t.source for t in bot.transparency] == ["EU AI Act Art. 50(1)"]
    assert img.tier == "limited" and img.transparency[0].source == "EU AI Act Art. 50(2)"
    assert bot.level == "medium"  # transparency duty and customer data both set a medium floor


def test_safety_component_is_high_risk_under_article_6_1_even_with_narrow_task() -> None:
    a = assess(make(flags=["safety_component", "narrow_procedural_task"]))
    assert a.annex_area == "product_safety" and a.tier == "high"


def test_privacy_regimes_follow_people_and_establishment() -> None:
    a = assess(make(data_categories=["personal"], people_regions=["UK", "AU"], org_regions=["NZ"], processing_region="US", affected=["customers"]))
    assert a.regime_ids == ["uk_gdpr", "au_app", "nz_ipp"]
    assert all(r.transfer_note for r in a.regimes)
    assert any(o.id == "app_8" for r in a.regimes for o in r.obligations)


def test_no_personal_data_means_no_privacy_regime() -> None:
    a = assess(make(data_categories=["confidential"], people_regions=["EU"], org_regions=["EU"]))
    assert a.regimes == []


def test_adequacy_decision_is_named_in_transfer_note() -> None:
    a = assess(make(data_categories=["personal"], people_regions=["EU"], processing_region="UK"))
    assert "covered by an adequacy decision" in a.regimes[0].transfer_note


def test_special_category_and_automated_decisions_raise_floor() -> None:
    a = assess(make(use_area="other", data_categories=["health"], affected=["customers"], flags=["about_individuals"], people_regions=["EU"], decision_mode="fully_automatic"))
    assert a.level == "high"
    ids = {d.id for d in a.drivers}
    assert {"special_category", "special_external", "automated_decision", "fully_automatic"} <= ids
    gdpr = {o.id for o in a.regimes[0].obligations}
    assert {"gdpr_9", "gdpr_22", "gdpr_35"} <= gdpr


def test_every_driver_and_finding_cites_a_source() -> None:
    a = assess(make(use_area="recruitment", data_categories=["personal", "health"], affected=["public"], flags=["about_individuals", "profiling"],
                    people_regions=["EU", "US"], processing_region="US", vendor="Acme AI"))  # fmt: skip
    items = [*a.drivers, *a.high_risk, *a.duties, *[o for r in a.regimes for o in r.obligations], *[c for cs in a.nist.values() for c in cs], *a.controls]
    assert items and all(i.source.strip() for i in items)


def test_required_controls_by_level() -> None:
    low = assess(make(use_area="general_productivity", vendor="X", data_categories=["confidential"]))
    high = assess(make(use_area="recruitment", flags=["about_individuals"], vendor="X", **PEOPLE))
    assert {c.id for c in low.required_controls} == {"vendor_terms"}
    assert {"human_review", "impact_assessment", "bias_testing", "logging", "kill_switch", "training", "transparency_notice"} <= {c.id for c in high.required_controls}


def test_review_months() -> None:
    assert (review_months("high"), review_months("medium"), review_months("low")) == (6, 12, 24)


def test_rule_files_only_use_known_condition_keys() -> None:
    """Evaluate every condition in every rules file against two very different intakes; unknown keys raise."""
    rules = load_rules()
    conds = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if "when" in o:
                conds.append(o["when"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(rules)
    assert len(conds) > 80
    for it in (
        make(),
        make(data_categories=["personal", "health", "children", "biometric", "financial", "confidential"], affected=["public"], flags=["about_individuals", "profiling"], vendor="v"),
    ):
        for c in conds:
            holds(c, Context(it, tier="high", region="EU"))


def test_unknown_condition_key_is_rejected() -> None:
    with pytest.raises(RuleError):
        holds({"colour": "red"}, Context(make()))

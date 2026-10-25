import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.credit.decision import DecisionInput, ProductTerms, _result, decide
from app.credit.limit import MIN_DSCR, annuity_payment
from app.credit.reasons import FALLBACK_HINT, REASONS
from app.credit.statuses import TransitionError, check_transition
from app.credit.stop_factors import STOP_FACTORS, StopFacts, evaluate
from app.enums import ApplicationStatus as S
from tests.conftest import MODELS_JSON

WORKING = ProductTerms(
    "WORKING_CAPITAL", "Оборотный", "term_loan",
    Decimal(300_000), Decimal(50_000_000), 6, 60, Decimal(24),
)  # fmt: skip
LINE = ProductTerms(
    "CREDIT_LINE", "Линия", "credit_line",
    Decimal(300_000), Decimal(30_000_000), 6, 18, Decimal(22),
)  # fmt: skip
OVERDRAFT = ProductTerms(
    "OVERDRAFT", "Овердрафт", "overdraft",
    Decimal(100_000), Decimal(10_000_000), 1, 12, Decimal(26),
)  # fmt: skip
CLEAN = StopFacts(
    company_active=True,
    bankruptcy_messages=0,
    zsk_zone="green",
    age_months=60,
    tax_debt=Decimal(0),
    fssp_remaining=Decimal(0),
    current_overdue=Decimal(0),
    worst_dpd=0,
)
INCOME = Decimal(450_000)


def _input(**overrides) -> DecisionInput:
    base = DecisionInput(
        product=WORKING,
        requested_amount=Decimal(5_000_000),
        requested_term=12,
        stop_checks=evaluate(CLEAN),
        income=INCOME,
        payments=Decimal(100_000),
        monthly_inflow=Decimal(4_050_000),
        own_bank_client=True,
        grade="A",
        score_reasons=["turnover_cv"],
        products=[WORKING, LINE, OVERDRAFT],
    )
    return replace(base, **overrides)


def _fits_dscr(amount: Decimal, rate: Decimal, term: int, payments: Decimal) -> bool:
    return INCOME / (payments + annuity_payment(amount, rate, term)) >= MIN_DSCR


def test_counter_offer_matches_case_example():
    # пример из постановки: 5 млн / 12 мес / 24%, доход 450 тыс, платежи 100 тыс → ≈ 2,75 млн
    d = decide(_input())

    assert d.outcome == "counter_offer" and d.reasons == ["ABOVE_LIMIT"]
    first, second = d.offers
    assert (first.amount, first.term_months) == (Decimal(2_749_000), 12)
    # второй вариант — вся запрошенная сумма на самый короткий срок, где она проходит DSCR
    assert (second.amount, second.term_months) == (Decimal(5_000_000), 36)
    assert d.alternatives == [] and d.hints


def test_offers_never_break_dscr():
    for payments in (Decimal(0), Decimal(100_000), Decimal(250_000)):
        d = decide(_input(payments=payments))
        assert d.offers
        for o in d.offers:
            assert _fits_dscr(o.amount, o.rate, o.term_months, payments)
            assert o.amount <= Decimal(5_000_000)


def test_amount_within_limit_is_approved_at_grade_rate():
    d = decide(_input(requested_amount=Decimal(1_000_000), grade="B"))

    assert d.outcome == "approved" and d.reasons == [] and len(d.offers) == 1
    assert d.offer is not None and d.offer.amount == Decimal(1_000_000)
    assert d.offer.rate == Decimal(25)  # базовая 24% + надбавка за B


def test_decline_by_dscr_suggests_other_products():
    payments = Decimal(
        345_000
    )  # свободно 15 тыс в месяц: 300 тыс на 12 мес не помещается
    d = decide(_input(payments=payments, requested_amount=Decimal(1_000_000)))

    assert d.outcome == "declined" and d.reasons == ["DSCR_LOW"] and d.offers == []
    assert {a.product_code for a in d.alternatives} == {"WORKING_CAPITAL", "OVERDRAFT"}
    for a in d.alternatives:
        assert _fits_dscr(a.amount, a.rate, a.term_months, payments)


def test_hard_stop_wins_over_everything():
    facts = replace(CLEAN, bankruptcy_messages=1, age_months=3, tax_debt=Decimal(10**6))
    d = decide(_input(stop_checks=evaluate(facts)))

    assert d.outcome == "declined" and d.reasons == ["BANKRUPTCY"]
    assert d.offers == [] and d.alternatives == [] and d.hints


def test_young_business_gets_date_to_come_back():
    facts = replace(CLEAN, age_months=4, eligible_from=date(2026, 12, 4))
    d = decide(_input(stop_checks=evaluate(facts)))

    assert (d.outcome, d.reasons) == ("declined", ["AGE_LT_6M"])
    assert d.hints == ["Подайте заявку после 04.12.2026 — бизнесу исполнится 6 месяцев"]


@pytest.mark.parametrize(
    ("facts", "outcome", "code"),
    [
        (replace(CLEAN, tax_debt=Decimal(60_000)), "manual_review", "TAX_DEBT"),
        (replace(CLEAN, worst_dpd=45), "manual_review", "PAST_DPD_30"),
        (replace(CLEAN, current_overdue=Decimal(1)), "manual_review", "CURRENT_DPD"),
    ],
)
def test_soft_stop_factors(facts, outcome, code):
    d = decide(_input(stop_checks=evaluate(facts)))
    assert (d.outcome, d.reasons) == (outcome, [code])


@pytest.mark.parametrize(
    ("overrides", "outcome", "first_reason"),
    [
        ({"income": None}, "manual_review", "NO_STATEMENT"),
        ({"grade": None}, "manual_review", "NO_MODEL"),
        ({"source_error": True}, "manual_review", "SOURCE_ERROR"),
        ({"grade": "C"}, "manual_review", "MANUAL_GRADE"),
        ({"grade": "D"}, "declined", "turnover_cv"),
        ({"grade": "E"}, "declined", "turnover_cv"),
    ],
)
def test_matrix(overrides, outcome, first_reason):
    d = decide(_input(**overrides))
    assert d.outcome == outcome and d.reasons[0] == first_reason
    assert d.offers == [] and d.alternatives == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"grade": "E", "score_reasons": []},
        {"grade": "E", "score_reasons": ["неизвестный_признак"]},
        {"grade": "C"},
        {"income": None},
        {"payments": Decimal(400_000)},
        {"stop_checks": evaluate(replace(CLEAN, company_active=False))},
        {"stop_checks": evaluate(replace(CLEAN, age_months=2))},
    ],
)
def test_refusal_always_has_advice(overrides):
    d = decide(_input(**overrides))
    assert d.outcome != "approved" and d.hints and all(d.hints)


def test_every_reason_code_has_text_and_hint():
    codes = {f.code for f in STOP_FACTORS} | {
        "NO_STATEMENT", "NO_MODEL", "SOURCE_ERROR", "DSCR_LOW", "ABOVE_LIMIT",
        "LOW_GRADE", "MANUAL_GRADE",
    }  # fmt: skip
    for code in codes:
        text, hint = REASONS[code]
        assert text and hint, code


def test_overdraft_needs_own_bank_account():
    small = _input(requested_amount=Decimal(200_000), product=OVERDRAFT)
    assert decide(small).outcome == "approved"
    assert decide(replace(small, own_bank_client=False)).outcome == "declined"


def test_status_machine():
    check_transition(S.SUBMITTED, S.SCORING)
    check_transition(S.APPROVED, S.OFFER_ACCEPTED)
    for current, target in [
        (S.SUBMITTED, S.APPROVED),  # мимо проверки
        (S.DECLINED, S.OFFER_ACCEPTED),
        (S.ISSUED, S.CANCELLED),
        (S.CONTRACT_SIGNED, S.CANCELLED),
    ]:
        with pytest.raises(TransitionError):
            check_transition(current, target)


def test_every_model_feature_has_text_and_hint():
    spec = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    for model in spec["models"]:
        for feature in model["features"]:
            text, hint = REASONS[feature["code"]]
            assert text and hint, feature["code"]


def test_unknown_reason_still_gets_advice():
    d = _result("declined", ["NEW_RULE_WITHOUT_TEXT"])
    assert d.hints == [FALLBACK_HINT]

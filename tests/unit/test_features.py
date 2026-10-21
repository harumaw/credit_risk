"""Признаки скоринга из КИ, оборотов и карточки компании."""

from datetime import date

from app.credit.features import (
    RECENCY_DECAY,
    SEVERITY,
    CompanyFacts,
    Obligation,
    TurnoverMonth,
    bki_features,
    company_features,
    delinquency_index,
    okved_section,
    turnover_features,
)

AS_OF = date(2025, 6, 15)


def test_delinquency_index_weights_and_decay():
    # позиция 0 — без просрочки, 1 — «до 30» месяц назад, 2 — «30+» два месяца назад
    expected = SEVERITY["1"] * RECENCY_DECAY + SEVERITY["2"] * RECENCY_DECAY**2
    assert delinquency_index(["012-0"]) == round(expected, 4)
    assert delinquency_index(["0000", "----"]) == 0


def test_bki_features_from_payment_strings():
    obligations = [
        Obligation(
            1_000_000, 400_000, 30_000, date(2023, 1, 10), None, "0010000000002"
        ),
        Obligation(500_000, 0, 0, date(2025, 3, 1), date(2025, 5, 1), "00"),
    ]
    f = bki_features(obligations, AS_OF)
    assert f["bki_loans_cnt"] == 2 and f["bki_active_cnt"] == 1
    assert f["bki_dpd_months_12m"] == 1  # статус «2» на позиции 12 — уже за окном
    assert f["bki_dpd30_months_24m"] == 1
    assert f["bki_months_since_dpd"] == 2
    assert f["bki_worst_status_3m"] == 1
    assert f["bki_new_loans_6m"] == 1
    assert f["bki_history_months"] == 29
    assert f["bki_utilization"] == 0.4


def test_turnover_features():
    rows = [
        TurnoverMonth(date(2025, m, 1), 100.0 if m <= 3 else 120.0, 90.0, 50.0)
        for m in range(1, 7)
    ]
    f = turnover_features(rows)
    assert f["turnover_months"] == 6
    assert f["revenue_12m"] == 1320.0  # 660 за 6 мес. → к году
    assert f["turnover_trend"] == 0.2
    assert f["balance_to_inflow"] == round(50 / 110, 4)
    assert turnover_features([])["revenue_12m"] is None


def test_company_features_without_history_or_turnovers():
    facts = CompanyFacts(
        as_of_date=AS_OF, legal_form="ООО", registration_date=date(2025, 1, 10), msp_category="micro",
        okved_main="62.01", region_code="77", tax_regime="usn_income",
    )  # fmt: skip
    f = company_features(facts)
    assert f["company_age_months"] == 5
    assert f["legal_form"] == "ЮЛ" and f["okved_section"] == "J"
    assert f["bki_loans_cnt"] == 0 and f["bki_months_since_dpd"] == 99
    assert f["debt_burden"] is None and f["revenue_12m"] is None


def test_okved_section():
    assert okved_section("47.19") == "G"
    assert okved_section("41.20") == "F"
    assert okved_section(None) is None

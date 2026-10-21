"""Скоркарта и выбор сегмента: чистые функции + сверка с ноутбуком (ml/artifacts/models.json)."""

import json
from pathlib import Path

import pytest

from app.credit.scorecard import (
    OTHER,
    Bin,
    Grade,
    Scorecard,
    Segment,
    check_conditions,
    match_segment,
    score,
)

MODELS_JSON = Path(__file__).resolve().parents[2] / "ml" / "artifacts" / "models.json"

SEGMENTS = [
    Segment("new_business", 10, {"any": [
        {"feature": "company_age_months", "op": "<", "value": 12},
        {"feature": "bki_loans_cnt", "op": "==", "value": 0},
    ]}),
    Segment("sme", 30, {"all": [
        {"feature": "legal_form", "op": "==", "value": "ЮЛ"},
        {"feature": "msp_category", "op": "in", "value": ["small", "medium"]},
    ]}),
    Segment("off", 5, {}, is_active=False),
    Segment("all", 100, {}),
]  # fmt: skip


def test_first_matching_segment_by_priority():
    young_sme = {
        "company_age_months": 5,
        "bki_loans_cnt": 3,
        "legal_form": "ЮЛ",
        "msp_category": "small",
    }
    assert match_segment(SEGMENTS, young_sme) == "new_business"  # priority 10 раньше 30
    old_sme = {**young_sme, "company_age_months": 40}
    assert match_segment(SEGMENTS, old_sme) == "sme"
    ip = {
        "company_age_months": 40,
        "bki_loans_cnt": 3,
        "legal_form": "ИП",
        "msp_category": "micro",
    }
    assert match_segment(SEGMENTS, ip) == "all"  # выключенный сегмент пропускается


def test_missing_feature_does_not_match_comparison():
    assert not check_conditions(
        {"feature": "company_age_months", "op": "<", "value": 12}, {}
    )
    assert check_conditions(
        {"feature": "x", "op": "is_null", "value": True}, {"x": None}
    )
    with pytest.raises(ValueError):
        check_conditions({"feature": "x", "op": "~", "value": 1}, {"x": 1})


def _card() -> Scorecard:
    return Scorecard(
        model_id="t",
        base_score=500,
        bins=[
            Bin("age", 0, -20, upper=12),
            Bin("age", 1, 10, lower=12, upper=60),
            Bin("age", 2, 30, lower=60),
            Bin("age", 3, -5, is_missing=True),
            Bin("okved", 0, 15, categories=("J", "L")),
            Bin("okved", 1, 0, categories=("G", OTHER)),
            Bin("okved", 2, -25, categories=("F",)),
        ],
        grades=[
            Grade("A", 520, 9999, 0.01),
            Grade("B", 490, 520, 0.03),
            Grade("E", -9999, 490, 0.2),
        ],
    )


def test_score_sums_bin_points_and_assigns_grade():
    out = score(
        _card(), {"age": 60, "okved": "J"}
    )  # граница 60 — в верхнем бине [60; ∞)
    assert out.score == 545 and out.grade == "A"
    out = score(_card(), {"age": 3, "okved": "F"})
    assert out.score == 455 and out.grade == "E"
    assert out.reason_codes() == ["age", "okved"]  # −50 и −40 от лучших бинов


def test_unknown_category_goes_to_other_and_missing_to_missing_bin():
    out = score(_card(), {"age": None, "okved": "Z"})
    assert out.score == 495  # −5 (пропуск) + 0 (прочие)


def test_app_reproduces_notebook_scores():
    spec = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    segments = [
        Segment(s["code"], s["priority"], s["conditions"], s["is_active"])
        for s in spec["segments"]
    ]
    cards = {}
    for m in spec["models"]:
        if m["status"] != "champion":
            continue
        cards[m["segment_code"]] = Scorecard(
            model_id=m["model_name"],
            base_score=m["params"]["intercept_points"],
            bins=[
                Bin(b["feature"], b["order"], b["points"], b["woe"], b["lower"], b["upper"],
                    tuple(b["categories"]) if b["categories"] else None, b["is_missing"])
                for b in m["bins"]
            ],
            grades=[Grade(g["grade"], g["score_from"], g["score_to"], g["pd"]) for g in m["grades"]],
            pd_a=m["params"]["pd_a"],
            pd_b=m["params"]["pd_b"],
        )  # fmt: skip
    assert spec["examples"]
    for ex in spec["examples"]:
        seg = match_segment(segments, ex["features"])
        card = cards.get(seg, cards["all"])
        out = score(card, ex["features"])
        assert card.model_id == ex["model"]
        assert out.score == pytest.approx(ex["score"], abs=0.01)
        assert out.grade == ex["grade"]
        assert out.pd == pytest.approx(ex["pd"], abs=1e-5)

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.services.goal import _build_goal_read


def _months_ago(n: int) -> datetime:
    now = datetime.now(UTC)
    total = now.year * 12 + (now.month - 1) - n
    year, month = divmod(total, 12)
    return datetime(year, month + 1, 1, tzinfo=UTC)


def _goal(*, target_amount: Decimal, months: int, created_at: datetime, currency: str = "KZT") -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        user_id=1,
        name="Goal",
        target_amount=target_amount,
        months=months,
        currency=currency,
        created_at=created_at,
    )


def test_behind_when_nothing_saved_this_month():
    goal = _goal(target_amount=Decimal("1200"), months=12, created_at=_months_ago(0))
    result = _build_goal_read(goal, saved=Decimal("0"))

    assert result["monthly_target"] == Decimal("100.00")
    assert result["status"] == "behind"
    assert result["behind_by"] == Decimal("100.00")
    assert result["pct"] == 0


def test_on_track_when_saved_matches_expected():
    goal = _goal(target_amount=Decimal("1200"), months=12, created_at=_months_ago(2))
    # к третьему месяцу (elapsed=2 -> forced min 1, but 2 elapsed) ожидается 2 взноса
    result = _build_goal_read(goal, saved=Decimal("200.00"))

    assert result["status"] == "on_track"
    assert result["behind_by"] == Decimal("0")


def test_behind_by_when_saving_less_than_expected():
    goal = _goal(target_amount=Decimal("1200"), months=12, created_at=_months_ago(3))
    result = _build_goal_read(goal, saved=Decimal("100"))

    # elapsed=3, monthly_target=100 -> expected_by_now=300
    assert result["status"] == "behind"
    assert result["behind_by"] == Decimal("200.00")


def test_done_when_saved_reaches_target():
    goal = _goal(target_amount=Decimal("1000"), months=10, created_at=_months_ago(1))
    result = _build_goal_read(goal, saved=Decimal("1000"))

    assert result["status"] == "done"
    assert result["behind_by"] == Decimal("0")
    assert result["pct"] == 100


def test_pct_never_exceeds_100_when_overfunded():
    goal = _goal(target_amount=Decimal("100"), months=1, created_at=_months_ago(0))
    result = _build_goal_read(goal, saved=Decimal("500"))

    assert result["pct"] == 100
    assert result["status"] == "done"


def test_zero_target_amount_does_not_crash():
    goal = _goal(target_amount=Decimal("0"), months=1, created_at=_months_ago(0))
    result = _build_goal_read(goal, saved=Decimal("0"))

    assert result["pct"] == 0
    assert result["monthly_target"] == Decimal("0.00")


def test_elapsed_months_floored_to_one_for_new_goal():
    # цель создана "в этом месяце" -> elapsed_months форсируется к 1, а не к 0
    goal = _goal(target_amount=Decimal("120"), months=12, created_at=_months_ago(0))
    result = _build_goal_read(goal, saved=Decimal("9"))

    assert result["status"] == "behind"
    assert result["behind_by"] == Decimal("1.00")

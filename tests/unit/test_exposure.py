from datetime import date
from decimal import Decimal

from app.credit.exposure import OwnCredit, fits_dscr, maturity_date, own_payments
from app.credit.limit import annuity_payment


def test_payment_and_outstanding_follow_annuity_schedule():
    c = OwnCredit(Decimal(1_200_000), Decimal(24), 12, date(2026, 1, 15))
    payment = annuity_payment(Decimal(1_200_000), Decimal(24), 12)
    assert c.monthly_payment == payment.quantize(Decimal(1))
    assert c.outstanding(date(2026, 1, 20)) == Decimal(
        1_200_000
    )  # платежей ещё не было
    after_six = c.outstanding(date(2026, 7, 15))
    assert Decimal(600_000) < after_six < Decimal(700_000)  # проценты в начале больше
    assert c.outstanding(date(2027, 2, 1)) == 0
    assert c.next_payment_date(date(2026, 1, 20)) == date(2026, 2, 15)
    assert c.next_payment_date(date(2027, 2, 1)) is None


def test_accepted_offer_counts_in_full_until_issued():
    c = OwnCredit(Decimal(500_000), Decimal(24), 6, None)
    assert c.outstanding(date(2026, 5, 1)) == Decimal(500_000)
    assert c.next_payment_date(date(2026, 5, 1)) is None
    assert own_payments([c, c]) == 2 * c.monthly_payment


def test_fits_dscr_keeps_margin():
    assert fits_dscr(Decimal(125), Decimal(60), Decimal(40))  # 125 = 1,25 × 100
    assert not fits_dscr(Decimal(124), Decimal(60), Decimal(40))
    assert not fits_dscr(None, Decimal(0), Decimal(1))


def test_maturity_date_clamps_short_months():
    assert maturity_date(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert maturity_date(date(2026, 11, 15), 14) == date(2028, 1, 15)

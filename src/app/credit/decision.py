"""Решение по заявке — чистые функции: стоп-факторы → грейд → лимит DSCR → матрица (CLAUDE.md §10).

Матрица: жёсткий стоп → отказ; мягкий стоп → мягкий отказ или ручной разбор; нет оборотов /
модели / данных источника → ручной разбор; A–B → одобрение или контрпредложение; C → ручной
разбор; D, E → отказ.

Варианты (`offers`) — то, что клиент может принять сейчас по этой заявке: при одобрении —
запрошенные условия, при контрпредложении — 1–2 варианта того же продукта (сумма до лимита
на запрошенный срок; запрошенная сумма на более длинный срок). Альтернативы — только при
отказе по DSCR: другие продукты и сроки для новой заявки. Ничего больше, чем позволяет DSCR.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.credit import reasons as texts
from app.credit.limit import LIMIT_STEP, annuity_payment, dscr_limit
from app.credit.stop_factors import BY_CODE, StopCheck
from app.enums import StopSeverity

APPROVED, COUNTER_OFFER, DECLINED, MANUAL_REVIEW = (
    "approved",
    "counter_offer",
    "declined",
    "manual_review",
)
GRADE_PREMIUM = {"A": Decimal(0), "B": Decimal(1), "C": Decimal(2), "D": Decimal(4)}
OVERDRAFT_SHARE = Decimal("0.3")  # овердрафт — до 30% среднего месячного прихода
STANDARD_TERMS = (6, 12, 18, 24, 36, 48, 60, 84, 120)  # сроки для второго варианта
MAX_REASONS = 3
MAX_ALTERNATIVES = 2


@dataclass(frozen=True)
class ProductTerms:
    code: str
    name: str
    kind: str  # term_loan / credit_line / overdraft
    min_amount: Decimal
    max_amount: Decimal
    min_term: int
    max_term: int
    base_rate: Decimal


@dataclass(frozen=True)
class DecisionInput:
    product: ProductTerms
    requested_amount: Decimal
    requested_term: int
    stop_checks: list[StopCheck]
    income: Decimal | None  # чистый поток в месяц; None — оборотов нет
    payments: Decimal  # текущие платежи по кредитам в месяц
    monthly_inflow: Decimal | None
    own_bank_client: bool
    grade: str | None  # None — скоринг не делали (жёсткий стоп) или нет модели
    score_reasons: list[str] = field(default_factory=list)
    products: list[ProductTerms] = field(default_factory=list)  # для альтернатив
    source_error: bool = False


@dataclass(frozen=True)
class Offer:
    product_code: str
    product_name: str
    amount: Decimal
    term_months: int
    rate: Decimal
    monthly_payment: Decimal


@dataclass(frozen=True)
class Decision:
    outcome: str
    offers: list[Offer]
    reasons: list[str]
    alternatives: list[Offer] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    @property
    def offer(self) -> Offer | None:
        """Основной вариант — первый."""
        return self.offers[0] if self.offers else None


def rate_for(product: ProductTerms, grade: str) -> Decimal:
    return product.base_rate + GRADE_PREMIUM.get(grade, Decimal(0))


def max_amount(inp: DecisionInput, p: ProductTerms, term: int, grade: str) -> Decimal:
    """Сколько можно дать по продукту на срок: DSCR, рамки продукта, правило овердрафта."""
    if inp.income is None:
        return Decimal(0)
    amount = min(
        dscr_limit(inp.income, inp.payments, rate_for(p, grade), term), p.max_amount
    )
    if p.kind == "overdraft":
        if not inp.own_bank_client or not inp.monthly_inflow:
            return Decimal(0)
        cap = inp.monthly_inflow * OVERDRAFT_SHARE
        amount = min(amount, (cap / LIMIT_STEP).to_integral_value() * LIMIT_STEP)
    return amount


def make_offer(p: ProductTerms, amount: Decimal, term: int, grade: str) -> Offer:
    rate = rate_for(p, grade)
    payment = annuity_payment(amount, rate, term).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return Offer(p.code, p.name, amount, term, rate, payment)


def longer_term_offer(inp: DecisionInput, grade: str, first: Offer) -> Offer | None:
    """Второй вариант контрпредложения: запрошенная сумма на самый короткий срок, где она
    проходит DSCR; если не проходит нигде — максимум на самом длинном сроке продукта."""
    p = inp.product
    terms = [t for t in STANDARD_TERMS if inp.requested_term < t <= p.max_term]
    for term in terms:
        if max_amount(inp, p, term, grade) >= inp.requested_amount:
            return make_offer(p, inp.requested_amount, term, grade)
    if terms:
        amount = max_amount(inp, p, terms[-1], grade)
        if amount > first.amount:
            return make_offer(p, amount, terms[-1], grade)
    return None


def alternatives(inp: DecisionInput, grade: str) -> list[Offer]:
    """Новая заявка вместо отказа: лучший вариант по каждому продукту (запрошенный срок в
    рамках продукта или максимальный), сумма не больше запрошенной и не меньше минимума."""
    best: dict[str, Offer] = {}
    for p in inp.products:
        terms = {min(max(inp.requested_term, p.min_term), p.max_term), p.max_term}
        for term in sorted(terms):
            amount = min(inp.requested_amount, max_amount(inp, p, term, grade))
            if amount < p.min_amount:
                continue
            current = best.get(p.code)
            if current is None or (amount, -term) > (
                current.amount,
                -current.term_months,
            ):
                best[p.code] = make_offer(p, amount, term, grade)
    ranked = sorted(best.values(), key=lambda o: (-o.amount, o.term_months))
    return ranked[:MAX_ALTERNATIVES]


def _result(
    outcome: str,
    reasons: list[str],
    offers: list[Offer] | None = None,
    alts: list[Offer] | None = None,
    extra_hints: list[str] | None = None,
) -> Decision:
    """Причины без повторов (не больше трёх) и советы к ним — всегда хотя бы один."""
    reasons = list(dict.fromkeys(reasons))[:MAX_REASONS]
    hints = [*(extra_hints or []), *texts.hints(reasons)]
    if outcome != APPROVED and not hints:  # без совета клиента не оставляем
        hints = [texts.FALLBACK_HINT]
    return Decision(outcome, offers or [], reasons, alts or [], hints)


def _age_hint(checks: list[StopCheck]) -> list[str]:
    for c in checks:
        if c.code == "AGE_LT_6M" and c.triggered and c.details.get("eligible_from"):
            day = date.fromisoformat(c.details["eligible_from"])
            return [
                f"Подайте заявку после {day:%d.%m.%Y} — бизнесу исполнится 6 месяцев"
            ]
    return []


def decide(inp: DecisionInput) -> Decision:
    hit = [c.code for c in inp.stop_checks if c.triggered]
    hard = [c for c in hit if BY_CODE[c].severity == StopSeverity.HARD]
    if hard:
        return _result(DECLINED, hard)
    if inp.source_error:
        return _result(MANUAL_REVIEW, ["SOURCE_ERROR"])
    soft_decline = [c for c in hit if BY_CODE[c].action == "decline"]
    if soft_decline:
        age = _age_hint(inp.stop_checks)
        if age:
            return Decision(DECLINED, [], soft_decline[:MAX_REASONS], hints=age)
        return _result(DECLINED, soft_decline)
    review = [c for c in hit if BY_CODE[c].action == "review"]
    if review:
        return _result(MANUAL_REVIEW, review)
    if inp.income is None:
        return _result(MANUAL_REVIEW, ["NO_STATEMENT"])
    grade = inp.grade
    if grade is None:
        return _result(MANUAL_REVIEW, ["NO_MODEL"])
    if grade in ("D", "E"):
        return _result(DECLINED, [*inp.score_reasons, "LOW_GRADE"])
    if grade == "C":
        return _result(MANUAL_REVIEW, ["MANUAL_GRADE", *inp.score_reasons])

    p, term = inp.product, inp.requested_term
    limit = max_amount(inp, p, term, grade)
    if inp.requested_amount <= limit:
        return _result(APPROVED, [], [make_offer(p, inp.requested_amount, term, grade)])
    if limit >= p.min_amount:
        first = make_offer(p, limit, term, grade)
        second = longer_term_offer(inp, grade, first)
        offers = [first, second] if second else [first]
        return _result(COUNTER_OFFER, ["ABOVE_LIMIT"], offers)
    return _result(DECLINED, ["DSCR_LOW"], alts=alternatives(inp, grade))

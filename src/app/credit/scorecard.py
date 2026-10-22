"""Скоркарта и выбор модели по сегменту — чистые функции без БД.

Модели, бины и сегменты лежат в БД (`scoring_segments`, `model_versions`, `scorecard_bins`,
`rating_scale`), сюда приходят уже прочитанными. Обучение и обоснование — ml/research.ipynb.

Баллы: Score = base_score + Σ points(бин признака); шкала PDO 20, 600 баллов при odds 50:1.
PD: 1 / (1 + exp(−(a + b·Score))) — калибровка на реальный уровень дефолта сегмента.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

PDO = 20
BASE_SCORE = 600
BASE_ODDS = 50
FACTOR = PDO / math.log(2)
OFFSET = BASE_SCORE - FACTOR * math.log(BASE_ODDS)

OTHER = "__other__"  # бин «прочие категории»

_OPS = {
    "<": lambda a, b: a is not None and a < b,
    "<=": lambda a, b: a is not None and a <= b,
    ">": lambda a, b: a is not None and a > b,
    ">=": lambda a, b: a is not None and a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "is_null": lambda a, b: (a is None) == bool(b),
}


# ---------------------------------------------------------------- сегменты


@dataclass(frozen=True)
class Segment:
    code: str
    priority: int
    conditions: Mapping[str, Any]
    is_active: bool = True


def check_conditions(conditions: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    """{"all": [...]}, {"any": [...]}, {"feature", "op", "value"}; {} — истина."""
    if not conditions:
        return True
    if "all" in conditions:
        return all(check_conditions(c, facts) for c in conditions["all"])
    if "any" in conditions:
        return any(check_conditions(c, facts) for c in conditions["any"])
    op = _OPS.get(conditions["op"])
    if op is None:
        raise ValueError(f"неизвестная операция {conditions['op']!r}")
    return op(facts.get(conditions["feature"]), conditions.get("value"))


def match_segment(segments: Sequence[Segment], facts: Mapping[str, Any]) -> str | None:
    """Код первого активного сегмента (по priority), условиям которого отвечает компания."""
    for seg in sorted(segments, key=lambda s: s.priority):
        if seg.is_active and check_conditions(seg.conditions, facts):
            return seg.code
    return None


# ---------------------------------------------------------------- скоркарта


@dataclass(frozen=True)
class Bin:
    feature: str
    order: int
    points: float
    woe: float = 0.0
    lower: float | None = None  # [lower, upper)
    upper: float | None = None
    categories: tuple[str, ...] | None = None
    is_missing: bool = False

    def matches(self, value: Any) -> bool:
        if value is None:
            return self.is_missing
        if self.categories is not None:
            return str(value) in self.categories
        if self.is_missing:
            return False
        v = float(value)
        return (self.lower is None or v >= self.lower) and (
            self.upper is None or v < self.upper
        )


@dataclass(frozen=True)
class Grade:
    grade: str
    score_from: float  # включительно
    score_to: float  # не включительно
    pd: float


@dataclass(frozen=True)
class Scorecard:
    model_id: str
    base_score: float
    bins: Sequence[Bin]
    grades: Sequence[Grade] = ()
    pd_a: float = 0.0  # калибровка: logit(PD) = a + b·score
    pd_b: float = -1 / FACTOR

    @property
    def features(self) -> list[str]:
        return sorted({b.feature for b in self.bins})


@dataclass(frozen=True)
class Contribution:
    feature: str
    value: Any
    bin_order: int | None
    points: float
    max_points: float  # лучший бин признака — для кодов причин


@dataclass(frozen=True)
class ScoreOutcome:
    score: float
    pd: float
    grade: str | None
    contributions: list[Contribution] = field(default_factory=list)

    def reason_codes(self, n: int = 3) -> list[str]:
        """Признаки, сильнее всего снизившие балл (относительно лучшего бина)."""
        lost = sorted(
            (c for c in self.contributions if c.max_points - c.points > 0.5),
            key=lambda c: c.max_points - c.points,
            reverse=True,
        )
        return [c.feature for c in lost[:n]]


def find_bin(bins: Sequence[Bin], value: Any) -> Bin | None:
    for b in bins:
        if b.matches(value):
            return b
    if value is not None:  # неизвестная категория → «прочие»
        return next((b for b in bins if b.categories and OTHER in b.categories), None)
    return None


def pd_from_score(card: Scorecard, score: float) -> float:
    return 1 / (1 + math.exp(-(card.pd_a + card.pd_b * score)))


def grade_for(card: Scorecard, score: float) -> str | None:
    for g in card.grades:
        if g.score_from <= score < g.score_to:
            return g.grade
    return None


def score(card: Scorecard, features: Mapping[str, Any]) -> ScoreOutcome:
    by_feature: dict[str, list[Bin]] = {}
    for b in card.bins:
        by_feature.setdefault(b.feature, []).append(b)
    total = card.base_score
    contributions = []
    for feature, bins in sorted(by_feature.items()):
        value = features.get(feature)
        b = find_bin(sorted(bins, key=lambda x: x.order), value)
        points = b.points if b else 0.0  # нет бина — нейтрально (WoE = 0)
        total += points
        contributions.append(
            Contribution(
                feature,
                value,
                b.order if b else None,
                points,
                max(x.points for x in bins),
            )
        )
    total = round(total, 2)
    return ScoreOutcome(
        score=total,
        pd=round(pd_from_score(card, total), 6),
        grade=grade_for(card, total),
        contributions=contributions,
    )

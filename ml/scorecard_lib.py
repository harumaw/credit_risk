"""Инструменты разработки скоркарты для ml/research.ipynb: биннинг, WoE/IV, логрег, метрики.

WoE = ln(%good / %bad) — положительный WoE означает «лучше среднего».
Баллы бина = −Factor·β·WoE (β < 0 у логрега на дефолт), базовый балл = Offset − Factor·α.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.credit.scorecard import FACTOR, OTHER

EPS = 0.5  # сглаживание пустых ячеек


# ---------------------------------------------------------------- WoE / IV


def woe_table(groups: pd.Series, y: pd.Series) -> pd.DataFrame:
    """Таблица по группам: count, bad, bad_rate, share, woe, iv."""
    t = pd.DataFrame({"g": groups.values, "y": y.values}).groupby(
        "g", dropna=False, observed=True
    )["y"]
    t = t.agg(count="size", bad="sum")
    t["good"] = t["count"] - t["bad"]
    n_good, n_bad, k = t.good.sum(), t.bad.sum(), len(t)
    dist_good = (t.good + EPS) / (n_good + EPS * k)
    dist_bad = (t.bad + EPS) / (n_bad + EPS * k)
    t["bad_rate"] = t.bad / t["count"]
    t["share"] = t["count"] / t["count"].sum()
    t["woe"] = np.log(dist_good / dist_bad)
    t["iv"] = (dist_good - dist_bad) * t["woe"]
    return t


def information_value(groups: pd.Series, y: pd.Series) -> float:
    return float(woe_table(groups, y)["iv"].sum())


def iv_strength(iv: float) -> str:
    if iv < 0.02:
        return "нет связи"
    if iv < 0.1:
        return "слабая"
    if iv < 0.3:
        return "средняя"
    if iv < 0.5:
        return "сильная"
    return "подозрительно сильная"


# ---------------------------------------------------------------- биннинг


@dataclass
class FeatureBinning:
    feature: str
    kind: str  # numeric / categorical
    edges: list[float] = field(default_factory=list)  # внутренние границы numeric
    groups: list[list[str]] = field(default_factory=list)  # группы категорий
    missing_bin: bool = False
    table: pd.DataFrame | None = None  # статистика на train
    woe: dict[int, float] = field(default_factory=dict)  # bin_order → WoE

    def assign(self, x: pd.Series) -> pd.Series:
        """Номер бина (0..), −1 — пропуск."""
        if self.kind == "numeric":
            vals = pd.to_numeric(x, errors="coerce")
            idx = np.searchsorted(np.array(self.edges), vals.to_numpy(), side="right")
            out = pd.Series(idx, index=x.index)
            out[vals.isna()] = -1
            return out
        mapping = {c: i for i, g in enumerate(self.groups) for c in g}
        other = next((i for i, g in enumerate(self.groups) if OTHER in g), None)
        out = x.astype("object").map(
            lambda v: mapping.get(str(v), other) if pd.notna(v) else -1
        )
        return out.fillna(-1).astype(int)

    def transform(self, x: pd.Series) -> pd.Series:
        b = self.assign(x)
        return b.map(lambda i: self.woe.get(int(i), 0.0)).astype(float)

    def describe(self) -> pd.DataFrame:
        rows = []
        for order, row in self.table.iterrows():  # type: ignore[union-attr]
            rows.append(
                {
                    "feature": self.feature,
                    "bin": self.label(int(order)),
                    **row.to_dict(),
                }
            )
        return pd.DataFrame(rows)

    def label(self, order: int) -> str:
        if order == -1:
            return "пропуск"
        if self.kind == "categorical":
            return ", ".join(self.groups[order])
        lo = self.edges[order - 1] if order > 0 else None
        hi = self.edges[order] if order < len(self.edges) else None
        if lo is None:
            return f"< {hi:g}"
        if hi is None:
            return f">= {lo:g}"
        return f"[{lo:g}; {hi:g})"

    def bins_export(self, beta: float) -> list[dict]:
        """Бины в формате scorecard_bins (баллы = −Factor·β·WoE)."""
        out = []
        for order, row in self.table.iterrows():  # type: ignore[union-attr]
            order = int(order)
            item = {
                "feature": self.feature,
                "order": order if order >= 0 else len(self.table),  # type: ignore[arg-type]
                "woe": round(float(row.woe), 6),
                "points": round(-FACTOR * beta * float(row.woe), 2),
                "event_rate": round(float(row.bad_rate), 5),
                "population_share": round(float(row.share), 5),
                "is_missing": order == -1,
                "lower": None,
                "upper": None,
                "categories": None,
            }
            if order >= 0 and self.kind == "numeric":
                item["lower"] = self.edges[order - 1] if order > 0 else None
                item["upper"] = self.edges[order] if order < len(self.edges) else None
            elif order >= 0:
                item["categories"] = list(self.groups[order])
            out.append(item)
        return out


def _monotone_merge(
    edges: list[float], x: pd.Series, y: pd.Series, min_share: float, min_bad: int
) -> list[float]:
    """Сливаем соседние бины, пока bad rate не станет монотонным и бины не наберут объём."""
    direction = np.sign(pd.Series(x).corr(pd.Series(y), method="spearman") or 1)
    while edges:
        b = np.searchsorted(np.array(edges), x.to_numpy(), side="right")
        t = (
            pd.DataFrame({"b": b, "y": y.to_numpy()})
            .groupby("b")["y"]
            .agg(["size", "sum", "mean"])
        )
        t = t.reindex(range(len(edges) + 1), fill_value=0)
        small = (t["size"] / len(x) < min_share) | (t["sum"] < min_bad)
        diffs = np.diff(t["mean"].to_numpy()) * direction
        bad_pairs = np.where(diffs < 0)[0]
        if small.any():
            i = int(np.where(small)[0][0])
            j = i - 1 if i == len(edges) else i  # граница, которую убираем
            if i > 0 and i < len(edges):  # сливаем с более похожим соседом
                left = abs(t["mean"].iat[i] - t["mean"].iat[i - 1])
                right = abs(t["mean"].iat[i] - t["mean"].iat[i + 1])
                j = i - 1 if left <= right else i
            edges.pop(j)
        elif len(bad_pairs):
            edges.pop(int(bad_pairs[0]))
        else:
            break
    return edges


def bin_numeric(
    x: pd.Series,
    y: pd.Series,
    feature: str,
    max_bins: int = 8,
    min_share: float = 0.05,
    min_bad: int = 5,
    special: list[float] | None = None,
) -> FeatureBinning:
    vals = pd.to_numeric(x, errors="coerce")
    mask = vals.notna()
    q = np.unique(np.nanquantile(vals[mask], np.linspace(0, 1, max_bins * 2 + 1)[1:-1]))
    edges = sorted({float(e) for e in q} | set(special or []))
    edges = [e for e in edges if vals[mask].min() < e <= vals[mask].max()]
    edges = _monotone_merge(edges, vals[mask], y[mask], min_share, min_bad)
    while len(edges) + 1 > max_bins:
        edges = edges[::2] if len(edges) > 2 else edges[:1]
    fb = FeatureBinning(
        feature, "numeric", edges=edges, missing_bin=bool((~mask).any())
    )
    _fit_table(fb, x, y)
    return fb


def bin_categorical(
    x: pd.Series,
    y: pd.Series,
    feature: str,
    max_groups: int = 6,
    min_share: float = 0.05,
    min_bad: int = 5,
) -> FeatureBinning:
    s = (
        x.astype("object")
        .where(x.notna(), None)
        .map(lambda v: None if v is None else str(v))
    )
    t = woe_table(s.fillna("__nan__"), y)
    rare = t[(t["share"] < min_share) | (t["bad"] < min_bad)].index.tolist()
    s = s.map(lambda v: OTHER if v in rare else v)
    t = (
        woe_table(s.fillna("__nan__"), y)
        .drop(index="__nan__", errors="ignore")
        .sort_values("bad_rate")
    )
    groups = [[str(c)] for c in t.index]
    stats = [(float(r["bad"]), float(r["count"])) for _, r in t.iterrows()]
    while (
        len(groups) > max_groups
    ):  # сливаем соседние по bad rate группы с ближайшим уровнем
        rates = [b / n for b, n in stats]
        i = int(np.argmin(np.diff(rates)))
        groups[i] += groups.pop(i + 1)
        b2, n2 = stats.pop(i + 1)
        stats[i] = (stats[i][0] + b2, stats[i][1] + n2)
    if not any(
        OTHER in g for g in groups
    ):  # новые категории в проде → к самой многочисленной группе
        biggest = int(np.argmax([n for _, n in stats]))
        groups[biggest].append(OTHER)
    fb = FeatureBinning(
        feature, "categorical", groups=groups, missing_bin=bool(x.isna().any())
    )
    _fit_table(fb, x, y)
    return fb


def _fit_table(fb: FeatureBinning, x: pd.Series, y: pd.Series) -> None:
    t = woe_table(fb.assign(x), y).sort_index()
    fb.table = t
    fb.woe = {int(k): float(v) for k, v in t["woe"].items()}


def auto_bin(
    df: pd.DataFrame, y: pd.Series, features: list[str], categorical: set[str], **kw
) -> dict[str, FeatureBinning]:
    out = {}
    for f in features:
        if f in categorical:
            out[f] = bin_categorical(
                df[f],
                y,
                f,
                min_share=kw.get("min_share", 0.05),
                min_bad=kw.get("min_bad", 5),
            )
        else:
            out[f] = bin_numeric(
                df[f],
                y,
                f,
                max_bins=kw.get("max_bins", 8),
                min_share=kw.get("min_share", 0.05),
                min_bad=kw.get("min_bad", 5),
            )
    return out


def iv_summary(binnings: dict[str, FeatureBinning]) -> pd.DataFrame:
    rows = [
        {"feature": f, "iv": float(b.table["iv"].sum()), "bins": len(b.table)}  # type: ignore[index]
        for f, b in binnings.items()
    ]
    t = pd.DataFrame(rows).sort_values("iv", ascending=False).reset_index(drop=True)
    t["strength"] = t["iv"].map(iv_strength)
    return t


# ---------------------------------------------------------------- логрег и метрики


def logit_fit(X: pd.DataFrame, y: pd.Series) -> tuple[LogisticRegression, pd.DataFrame]:
    """Логрег без регуляризации + Wald-статистика (как в statsmodels)."""
    m = LogisticRegression(C=1e6, max_iter=5000)
    m.fit(X, y)
    p = m.predict_proba(X)[:, 1]
    Xd = np.column_stack([np.ones(len(X)), X.to_numpy()])
    W = p * (1 - p)
    cov = np.linalg.pinv(Xd.T @ (Xd * W[:, None]))
    coef = np.concatenate([m.intercept_, m.coef_[0]])
    se = np.sqrt(np.diag(cov))
    z = coef / se
    pval = 2 * (1 - _norm_cdf(np.abs(z)))
    stats = pd.DataFrame(
        {"coef": coef, "se": se, "z": z, "p_value": pval},
        index=["intercept", *X.columns],
    )
    return m, stats


def _norm_cdf(z):
    return 0.5 * (1 + np.vectorize(math.erf)(z / math.sqrt(2)))


def stepwise_select(
    W: pd.DataFrame, y: pd.Series, candidates: list[str], p_max: float = 0.05
) -> tuple[list[str], list[str]]:
    """Убираем признаки с неверным знаком (β ≥ 0 при WoE «хорошо-ориентированном») и незначимые."""
    feats, log = list(candidates), []
    while feats:
        _, st = logit_fit(W[feats], y)
        st = st.drop(index="intercept")
        wrong = st[st.coef >= 0]
        if len(wrong):
            f = wrong.coef.idxmax()
            log.append(f"{f}: неверный знак β={st.coef[f]:+.3f} — исключён")
            feats.remove(f)
            continue
        weak = st[st.p_value > p_max]
        if len(weak):
            f = weak.p_value.idxmax()
            log.append(f"{f}: незначим (p={st.p_value[f]:.3f}) — исключён")
            feats.remove(f)
            continue
        break
    return feats, log


def correlation_filter(
    W: pd.DataFrame, ivs: pd.Series, threshold: float = 0.7
) -> tuple[list[str], list[str]]:
    keep, log = [], []
    for f in ivs.sort_values(ascending=False).index:
        corr = [abs(W[f].corr(W[k])) for k in keep]
        if corr and max(corr) > threshold:
            other = keep[int(np.argmax(corr))]
            log.append(f"{f}: |ρ|={max(corr):.2f} с {other} (IV выше) — исключён")
            continue
        keep.append(f)
    return keep, log


def vif(W: pd.DataFrame) -> pd.Series:
    out = {}
    for f in W.columns:
        others = W.drop(columns=f)
        if others.shape[1] == 0:
            out[f] = 1.0
            continue
        Xd = np.column_stack([np.ones(len(W)), others.to_numpy()])
        beta, *_ = np.linalg.lstsq(Xd, W[f].to_numpy(), rcond=None)
        resid = W[f].to_numpy() - Xd @ beta
        r2 = 1 - resid.var() / W[f].to_numpy().var()
        out[f] = 1 / max(1 - r2, 1e-9)
    return pd.Series(out)


def gini(y, score_bad) -> float:
    return 2 * roc_auc_score(y, score_bad) - 1


def ks(y, score_bad) -> float:
    fpr, tpr, _ = roc_curve(y, score_bad)
    return float(np.max(tpr - fpr))


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(np.clip(actual, edges[0], edges[-1]), edges)[0] / len(actual)
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def psi_label(v: float) -> str:
    return "стабильно" if v < 0.1 else "есть сдвиг" if v < 0.25 else "сильный сдвиг"

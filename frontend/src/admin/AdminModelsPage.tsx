import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  calculate,
  getModel,
  listModels,
  randomExample,
  type CalcResult,
  type Condition,
  type ModelDetail,
  type ModelInfo,
  type SegmentRule,
} from "../api/admin";
import { ApiError } from "../api/client";
import { useAsync } from "../lib/useAsync";
import { AdminShell, DECISIONS, GRADE_DECISION, GradeChip, Status, date, num, pct } from "./ui";

export function AdminModelsPage() {
  const list = useAsync(listModels, []);
  const [selected, setSelected] = useState<string | null>(null);

  const models = list.status === "ready" ? list.data.models : [];
  const current = selected ?? models.find((m) => m.status === "champion" && m.segment === "all")?.id ?? models[0]?.id ?? null;

  return (
    <AdminShell>
      <main>
        <section className="container page-head page-head-col">
          <h1>Модели скоринга</h1>
          <p className="page-head-sub">Бины и баллы каждой скоркарты, калькулятор и правила, когда какая модель применяется.</p>
          {list.status === "ready" && (
            <div className="adm-models">
              {models.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className={`adm-model ${m.id === current ? "is-on" : ""}`}
                  aria-pressed={m.id === current}
                  onClick={() => setSelected(m.id)}
                >
                  <span className="adm-model-name">{m.name}</span>
                  <span className="adm-model-meta">
                    сегмент {m.segment ?? "—"} · {m.status}
                  </span>
                  <span className="adm-model-meta">
                    Gini OOT {num(m.giniOot, 3)} · cutoff {num(m.cutoff)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
        <section className="sheet sheet-tight">
          <div className="container stack">
            {list.status === "loading" && <Status />}
            {list.status === "error" && <Status error={list.message} onRetry={list.reload} />}
            {list.status === "ready" && !models.length && (
              <Status error="Модели не загружены: python -m app.dataload.synthetic --models-only" />
            )}
            {list.status === "ready" && current && (
              <ModelView key={current} id={current} info={models.find((m) => m.id === current)!} />
            )}
            {list.status === "ready" && <Segments segments={list.data.segments} models={models} />}
          </div>
        </section>
      </main>
    </AdminShell>
  );
}

const pdFromScore = (score: number, params: Record<string, number | string>) => {
  const a = Number(params.pd_a);
  const b = Number(params.pd_b);
  return 1 / (1 + Math.exp(-(a + b * score)));
};

function ModelView({ id, info }: { id: string; info: ModelInfo }) {
  const detail = useAsync(() => getModel(id), [id]);
  if (detail.status === "loading") return <Status />;
  if (detail.status === "error") return <Status error={detail.message} onRetry={detail.reload} />;
  return <Calculator model={detail.data} info={info} />;
}

function Calculator({ model, info }: { model: ModelDetail; info: ModelInfo }) {
  // feature → порядковый номер бина; нет выбора — нейтрально (0 баллов)
  const [picked, setPicked] = useState<Record<string, number>>({});
  const [example, setExample] = useState<{ name: string; companyId: string; result: CalcResult } | null>(null);
  const [exampleDecision, setExampleDecision] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // по умолчанию — самый частый бин каждого признака: «типичная» компания
    const init: Record<string, number> = {};
    for (const f of model.features) {
      const top = [...f.bins].sort((a, b) => (b.share ?? 0) - (a.share ?? 0))[0];
      if (top) init[f.code] = top.order;
    }
    setPicked(init);
  }, [model]);

  const points = model.features.reduce((acc, f) => {
    const b = f.bins.find((x) => x.order === picked[f.code]);
    return acc + (b?.points ?? 0);
  }, 0);
  const total = model.base + points;
  const pd = model.params.pd_a !== undefined ? pdFromScore(total, model.params) : null;
  const grade = model.grades.find((g) => total >= g.from && total < g.to)?.grade ?? "—";

  async function fromDb() {
    setBusy(true);
    setErr(null);
    try {
      const ex = await randomExample(exampleDecision ? { decision: exampleDecision } : {});
      const result = await calculate(model.id, ex.features);
      const next: Record<string, number> = {};
      for (const c of result.contributions) {
        const f = model.features.find((x) => x.code === c.feature);
        const b = f?.bins.find((x) => x.label === c.bin);
        if (f && b) next[f.code] = b.order;
      }
      setPicked(next);
      setExample({ name: ex.name, companyId: ex.companyId, result });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Не удалось получить компанию");
    } finally {
      setBusy(false);
    }
  }

  const p = model.params;
  return (
    <>
      <section className="panel-lg">
        <div className="adm-panel-head">
          <h2>
            Калькулятор — {model.name} {model.version}
          </h2>
          <span className="muted">выберите бин каждого признака; сброс бина — нейтрально (0 баллов)</span>
        </div>
        <div className="adm-calc">
          <div className="adm-calc-features">
            {model.features.map((f) => (
              <div key={f.code} className="adm-calc-feature">
                <div className="adm-calc-name">
                  <strong>{f.name}</strong>
                  <span className="muted small">
                    {f.code} · IV {num(f.iv, 3)} · β {num(f.coefficient, 3)}
                    {f.formula ? ` · ${f.formula}` : ""}
                  </span>
                </div>
                <div className="adm-bins" role="group" aria-label={f.name}>
                  {f.bins.map((b) => (
                    <button
                      key={b.order}
                      type="button"
                      aria-pressed={picked[f.code] === b.order}
                      onClick={() =>
                        setPicked((s) => {
                          const n = { ...s };
                          if (n[f.code] === b.order) delete n[f.code];
                          else n[f.code] = b.order;
                          return n;
                        })
                      }
                      title={`WoE ${num(b.woe, 3)} · bad rate ${pct(b.eventRate)} · доля ${pct(b.share)}`}
                    >
                      {b.label}
                      <span className={b.points < 0 ? "is-bad" : "is-good"}>
                        {b.points > 0 ? "+" : ""}
                        {num(b.points, 1)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <aside className="adm-calc-total">
            <span className="adm-kpi-label">Итоговый балл</span>
            <span className="adm-calc-score">{num(total)}</span>
            <span>
              Грейд <GradeChip grade={grade} /> · PD {pct(pd)}
            </span>
            <span className="adm-calc-decision">{GRADE_DECISION[grade] ?? "—"}</span>
            <span className="muted-dark small">
              база {num(model.base)} · PDO {p.pdo} · {p.base_score} баллов при {p.base_odds}:1 · PD = 1/(1+e^−(a+b·балл))
            </span>
            <div className="adm-calc-db">
              <label className="adm-field adm-field-dark">
                Из БД с решением
                <select value={exampleDecision} onChange={(e) => setExampleDecision(e.target.value)}>
                  <option value="">любым</option>
                  {DECISIONS.map((d) => (
                    <option key={d.value} value={d.value}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className="btn btn-accent" onClick={fromDb} disabled={busy}>
                {busy ? "Ищем…" : "Подставить случайную компанию"}
              </button>
              {example && (
                <span className="small">
                  <Link to={`/adminuser/companies/${example.companyId}`}>{example.name}</Link>: этой моделью {num(example.result.score)} ·{" "}
                  {example.result.grade} · {example.result.decisionLabel}
                </span>
              )}
              {err && <span className="small" style={{ color: "#FF8A80" }}>{err}</span>}
            </div>
          </aside>
        </div>
      </section>

      <section className="panel-lg">
        <h2>Мастер-шкала и метрики</h2>
        <div className="adm-grades">
          {[...model.grades].reverse().map((g) => (
            <div key={g.grade}>
              <GradeChip grade={g.grade} />
              <span>
                {g.from <= -9999 ? `< ${num(g.to)}` : g.to >= 9999 ? `≥ ${num(g.from)}` : `${num(g.from)} – ${num(g.to)}`}
              </span>
              <span className="muted small">
                PD {pct(g.pd)} · {GRADE_DECISION[g.grade]}
              </span>
            </div>
          ))}
        </div>
        <div className="adm-metrics">
          <div>
            Gini train / valid / OOT
            <strong>
              {num(info.giniTrain, 3)} / {num(Number(p.gini_valid), 3)} / {num(info.giniOot, 3)}
            </strong>
          </div>
          <div>
            KS OOT<strong>{num(info.ksOot, 3)}</strong>
          </div>
          <div>
            PSI баллов train → OOT<strong>{num(Number(p.psi_oot), 4)}</strong>
          </div>
          <div>
            Обучение<strong>{`${date(info.trainFrom)} – ${date(info.trainTo)}`}</strong>
          </div>
          <div>
            OOT<strong>{`${date(info.ootFrom)} – ${date(info.ootTo)}`}</strong>
          </div>
          <div>
            Наблюдений train / OOT<strong>{`${p.n_train ?? "—"} / ${p.n_oot ?? "—"}`}</strong>
          </div>
        </div>
        {info.target && <p className="muted small">Целевое событие: {info.target}</p>}
      </section>
    </>
  );
}

const OP: Record<string, string> = { "<": "<", "<=": "≤", ">": ">", ">=": "≥", "==": "=", in: "∈", "!=": "≠" };
const cond = (c: Condition) => `${c.feature} ${OP[c.op] ?? c.op} ${Array.isArray(c.value) ? c.value.join(", ") : c.value}`;

function Segments({ segments, models }: { segments: SegmentRule[]; models: ModelInfo[] }) {
  return (
    <section className="panel-lg">
      <h2>Правила применения (scoring_segments)</h2>
      <p className="muted small">
        Сегменты проверяются по приоритету; первый подошедший с активной champion-моделью решает. Не подошёл или выключен — запасной «all».
      </p>
      <div className="panel-scroll">
        <table className="table table-wide adm-table">
          <thead>
            <tr>
              <th>Приоритет</th>
              <th>Сегмент</th>
              <th>Условие</th>
              <th>Модель</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {segments.map((s) => {
              const champ = models.find((m) => m.segment === s.code && m.status === "champion");
              const rule = s.conditions.any
                ? s.conditions.any.map(cond).join(" ИЛИ ")
                : s.conditions.all
                  ? s.conditions.all.map(cond).join(" И ")
                  : "всегда";
              return (
                <tr key={s.code}>
                  <td className="strong">{s.priority}</td>
                  <td>
                    <strong>{s.code}</strong>
                    <div className="table-sub">{s.name}</div>
                  </td>
                  <td className="adm-wrap">
                    {rule}
                    {s.description && <div className="table-sub">{s.description}</div>}
                  </td>
                  <td>{champ ? `${champ.name} ${champ.version}` : "—"}</td>
                  <td>{s.isActive ? <span className="chip chip-ok">активен</span> : <span className="chip chip-no">выключен</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

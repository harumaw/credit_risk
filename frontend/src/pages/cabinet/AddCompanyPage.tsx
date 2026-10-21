import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { addCompany, getCompanySources, lookupCompany, type CompanyLookup, type SourceStatus } from "../../api/cabinet";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { useCompanies } from "../../cabinet/CompanyContext";
import { CabinetHeader } from "../../components/cabinet/CabinetHeader";
import { Sheet } from "../../components/cabinet/EmptyCabinet";
import { CheckIcon, ChevronLeft } from "../../components/Icons";
import { SiteFooter } from "../../components/SiteHeader";
import { innError } from "../../lib/validation";

type Step = "inn" | "confirm" | "collect";

const SOURCE_TEXT: Record<SourceStatus["state"], string> = {
  done: "готово",
  work: "проверяем…",
  wait: "в очереди",
  error: "нужна выписка",
};

const POLL_MS = 500;

export function AddCompanyPage() {
  const { state } = useAuth();
  const { reload, select } = useCompanies();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>("inn");
  const [inn, setInn] = useState("");
  const [innTouched, setInnTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState<CompanyLookup | null>(null);
  const [companyId, setCompanyId] = useState<string | null>(null);
  const [sources, setSources] = useState<SourceStatus[]>([]);

  const user = state.status === "authenticated" ? state.user : null;
  const fullName = user ? [user.last_name, user.first_name, user.middle_name].filter(Boolean).join(" ") : "";
  const fieldError = innTouched ? innError(inn) : null;
  const collected = sources.length > 0 && sources.every((s) => s.state === "done" || s.state === "error");

  // Шаг 3: опрашиваем статус источников, пока все не ответят
  useEffect(() => {
    if (!companyId || collected) return;
    let cancelled = false;
    const tick = () =>
      getCompanySources(companyId).then(
        (s) => !cancelled && setSources(s),
        () => undefined,
      );
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [companyId, collected]);

  // Данные собраны — обновим список компаний в шапке
  useEffect(() => {
    if (collected) reload();
  }, [collected, reload]);

  async function onFind(e: FormEvent) {
    e.preventDefault();
    setInnTouched(true);
    if (innError(inn)) return;
    setError(null);
    setBusy(true);
    try {
      setFound(await lookupCompany(inn, fullName));
      setStep("confirm");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось найти компанию");
    } finally {
      setBusy(false);
    }
  }

  async function onConfirm() {
    if (!found) return;
    setError(null);
    setBusy(true);
    try {
      const company = await addCompany(found.inn);
      setCompanyId(company.id);
      setStep("collect");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось добавить компанию");
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    setStep("inn");
    setFound(null);
    setError(null);
  }

  function openCompany() {
    if (!companyId) return;
    select(companyId);
    navigate(`/cabinet/companies/${companyId}`);
  }

  const doneCount = sources.filter((s) => s.state !== "wait" && s.state !== "work").length;

  return (
    <>
      <CabinetHeader />
      <section className="container page-head page-head-col">
        <Link to="/cabinet" className="back-link">
          <ChevronLeft size={14} strokeWidth={2.4} />
          Назад
        </Link>
        <h1>Добавить компанию</h1>
        <p className="page-head-sub">Три шага. Данные подтянем сами — заполнять ничего не нужно.</p>
      </section>

      <Sheet>
        <div className="add-steps">
          {/* Шаг 1 */}
          <form className={`add-step ${step !== "inn" ? "is-past" : ""}`} onSubmit={onFind} noValidate>
            <span className="add-step-num">Шаг 1 из 3</span>
            <h2>Введите ИНН</h2>
            <div className="field">
              <label htmlFor="company-inn">ИНН компании или ИП</label>
              <input
                id="company-inn"
                className="inn-input"
                inputMode="numeric"
                autoComplete="off"
                maxLength={12}
                value={inn}
                disabled={step !== "inn"}
                aria-invalid={fieldError ? true : undefined}
                aria-describedby="company-inn-hint"
                onChange={(e) => setInn(e.target.value.replace(/\D/g, ""))}
                onBlur={() => inn && setInnTouched(true)}
              />
              {fieldError ? (
                <div className="error" id="company-inn-hint">
                  {fieldError}
                </div>
              ) : (
                <div className="hint" id="company-inn-hint">
                  10 цифр у ООО, 12 у ИП
                </div>
              )}
            </div>
            {step === "inn" && error && (
              <div className="form-error" role="alert">
                {error}
              </div>
            )}
            {step === "inn" ? (
              <button type="submit" className="btn btn-accent btn-lg" disabled={busy}>
                {busy ? "Ищем…" : "Найти"}
              </button>
            ) : (
              <button type="button" className="btn btn-white btn-lg" onClick={restart} disabled={step === "collect"}>
                Изменить ИНН
              </button>
            )}
          </form>

          {/* Шаг 2 */}
          <div className={`add-step ${step === "inn" ? "is-future" : ""} ${step === "collect" ? "is-past" : ""}`}>
            <span className="add-step-num">Шаг 2 из 3</span>
            <h2>Это ваша компания?</h2>
            {!found ? (
              <p className="muted">Найдём компанию в ЕГРЮЛ или ЕГРИП и покажем, кто руководитель.</p>
            ) : (
              <>
                <div className="found-card">
                  <strong>{found.name}</strong>
                  <dl>
                    <dt>ИНН</dt>
                    <dd>{found.inn}</dd>
                    <dt>Зарегистрирована</dt>
                    <dd>{found.registeredAt}</dd>
                    <dt>Деятельность</dt>
                    <dd>{found.activity}</dd>
                    <dt>{found.kind === "ip" ? "Предприниматель" : "Руководитель"}</dt>
                    <dd>{found.director}</dd>
                  </dl>
                </div>
                {found.alreadyAddedId ? (
                  <>
                    <p className="found-warn">Эта компания уже в вашем кабинете.</p>
                    <Link to={`/cabinet/companies/${found.alreadyAddedId}`} className="btn btn-dark btn-lg">
                      Открыть компанию
                    </Link>
                  </>
                ) : found.directorMatches ? (
                  <>
                    <p className="found-ok">
                      <CheckIcon size={18} strokeWidth={2.6} />
                      {found.kind === "ip" ? "Предприниматель в ЕГРИП" : "Руководитель в ЕГРЮЛ"} совпадает с вашим ФИО и
                      ИНН
                    </p>
                    <p className="muted small">
                      Если руководитель другой, добавить компанию нельзя — заявку подаёт только сам владелец.
                    </p>
                    {step === "confirm" && (
                      <>
                        {error && (
                          <div className="form-error" role="alert">
                            {error}
                          </div>
                        )}
                        <div className="btn-row">
                          <button type="button" className="btn btn-accent btn-lg grow" onClick={onConfirm} disabled={busy}>
                            {busy ? "Добавляем…" : "Да, добавить"}
                          </button>
                          <button type="button" className="btn btn-white btn-lg" onClick={restart} disabled={busy}>
                            Нет
                          </button>
                        </div>
                      </>
                    )}
                  </>
                ) : (
                  <>
                    <p className="found-warn">
                      Руководитель — другой человек. Добавить компанию нельзя: заявку подаёт только сам руководитель.
                    </p>
                    <button type="button" className="btn btn-white btn-lg" onClick={restart}>
                      Ввести другой ИНН
                    </button>
                  </>
                )}
              </>
            )}
          </div>

          {/* Шаг 3 */}
          <div className={`add-step add-step-dark ${step !== "collect" ? "is-future" : ""}`}>
            <span className="add-step-num">Шаг 3 из 3</span>
            <h2>Собираем данные</h2>
            {step !== "collect" ? (
              <p className="muted-dark">Проверим реестры, налоги, приставов, кредитную историю и обороты — около минуты.</p>
            ) : (
              <>
                <ul className="source-list" aria-live="polite">
                  {sources.map((s) => (
                    <li key={s.key}>
                      <span>{s.label}</span>
                      <span className={`source-${s.state}`}>{SOURCE_TEXT[s.state]}</span>
                    </li>
                  ))}
                </ul>
                <div
                  className="source-bar"
                  role="progressbar"
                  aria-label="Сбор данных"
                  aria-valuemin={0}
                  aria-valuemax={sources.length}
                  aria-valuenow={doneCount}
                >
                  {sources.map((s) => (
                    <span key={s.key} className={`source-${s.state}`} />
                  ))}
                </div>
                {collected ? (
                  <button type="button" className="btn btn-accent btn-lg" onClick={openCompany}>
                    Готово — открыть компанию
                  </button>
                ) : (
                  <p className="muted-dark">Можно не ждать — компания уже появилась в списке.</p>
                )}
              </>
            )}
          </div>
        </div>
      </Sheet>
      <SiteFooter />
    </>
  );
}

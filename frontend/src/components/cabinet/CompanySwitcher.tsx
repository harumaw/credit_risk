import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import type { Company } from "../../api/cabinet";
import { useCompanies } from "../../cabinet/CompanyContext";
import { plural, rubShort } from "../../lib/format";
import { CheckIcon, ChevronDown, GridIcon, PlusIcon } from "../Icons";

/** «ООО «Северный ветер»» → «СВ», ИП → «ИП» */
export function companyInitials(company: Company): string {
  if (company.kind === "ip") return "ИП";
  const words = company.name.replace(/^ООО\s*/, "").replace(/[«»"]/g, "").split(/\s+/).filter(Boolean);
  return words
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join("");
}

export function CompanyAvatar({ company }: { company: Company }) {
  return (
    <span className={`company-avatar ${company.kind === "ip" ? "is-ip" : ""}`} aria-hidden="true">
      {companyInitials(company)}
    </span>
  );
}

/** Подпись под компанией в списке: что с ней сейчас. */
function companyNote(company: Company): { text: string; urgent: boolean } {
  if (!company.hasStatement) return { text: "Нужна выписка из другого банка", urgent: true };
  return { text: `ИНН ${company.inn}`, urgent: false };
}

export function CompanySwitcher() {
  const { companies, selection, selected, select } = useCompanies();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const location = useLocation();

  // Закрываем при переходе, клике мимо и по Escape
  useEffect(() => setOpen(false), [location]);
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (companies.status !== "ready" || !companies.data.length) return null;
  const list = companies.data;
  const totalLimit = list.reduce((s, c) => s + (c.limit ?? 0), 0);
  const others = list.length - 1;

  return (
    <div className="switcher" ref={rootRef}>
      <button
        type="button"
        className="switcher-toggle"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="switcher-name">{selected ? selected.name : "Все компании"}</span>
        {selected && others > 0 && (
          <span className="switcher-more">
            +{others} {plural(others, ["компания", "компании", "компаний"])}
          </span>
        )}
        <ChevronDown size={14} strokeWidth={2.4} />
      </button>
      {open && (
        <div className="switcher-menu" id={menuId}>
          {list.length > 1 && (
            <>
              <Link
                to="/cabinet/companies"
                className="switcher-item"
                aria-current={selection === "all" ? "true" : undefined}
                onClick={() => select("all")}
              >
                <span className="company-avatar is-all" aria-hidden="true">
                  <GridIcon size={20} strokeWidth={2.2} />
                </span>
                <span className="switcher-text">
                  <strong>Все компании</strong>
                  <span>{totalLimit ? `Сводка: лимит по группе ${rubShort(totalLimit)}` : "Сводка по группе"}</span>
                </span>
                {selection === "all" && <CheckIcon size={18} strokeWidth={2.6} />}
              </Link>
              <div className="switcher-sep" />
            </>
          )}
          {list.map((c) => {
            const note = companyNote(c);
            const current = selection === c.id;
            return (
              <Link
                key={c.id}
                to={`/cabinet/companies/${c.id}`}
                className="switcher-item"
                aria-current={current ? "true" : undefined}
                onClick={() => select(c.id)}
              >
                <CompanyAvatar company={c} />
                <span className="switcher-text">
                  <strong>{c.name}</strong>
                  <span className={note.urgent ? "urgent" : undefined}>{note.text}</span>
                </span>
                {current && <CheckIcon size={18} strokeWidth={2.6} />}
              </Link>
            );
          })}
          <div className="switcher-sep" />
          <Link to="/cabinet/companies/new" className="switcher-item">
            <span className="company-avatar is-add" aria-hidden="true">
              <PlusIcon size={20} strokeWidth={2.4} />
            </span>
            <span className="switcher-text">
              <strong>Добавить компанию по ИНН</strong>
            </span>
          </Link>
        </div>
      )}
    </div>
  );
}

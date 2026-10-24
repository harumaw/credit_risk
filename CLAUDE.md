# CLAUDE.md — «Умный кредитный кабинет предпринимателя»

Главный контекст проекта. Расходится код с файлом — спроси. Приняли новое решение — обнови файл в том же PR. Пиши коротко.

## 1. Задача

Хакатон «Альфа-Будущее» (Альфа-Банк × Changellenge): прототип цифрового кредитного конвейера для МСБ — клиентский веб-кабинет (подбор, заявка, статус, решение) + обработка банком (проверки, данные, скоринг, андеррайтер). **Дедлайн 25.10.2026**, на дедлайн — тег версии. Главное для клиента — понятность: что подходит, пройду ли, где заявка, почему отказ, что вместо.

## 2. Ограничения кейса (нельзя нарушать)

Только веб · весь сценарий внутри продукта (без email/SMS; подписание — имитация кода) · без платных API, ключей, закрытых лицензий · только синтетические данные · автономно: никаких реальных ФНС/БКИ/банка, внешние источники — локальный симулятор · LLM только открытые веса, локально, под флагом (`AI_ENABLED=false`), без LLM сценарий проходит целиком · всё через `docker compose up` · lock-файлы и фиксированные теги образов · упрощения допустимы, если описаны.

## 3. Сдача

Тег + commit hash в README · доступ к репо для `alfa-hack-2026` · `docker compose up` + автоматический seed · README (назначение, архитектура, запуск, env, пошаговая проверка) · THIRD_PARTY_NOTICES (+ список смоделированных интеграций) · docs: `architecture.md`, `state-machine.md`, `data-model.md` (Mermaid), `model-card.md`, `test-scenarios.md` + автотесты · OpenAPI `/docs` + коллекция запросов · демо на VPS.

## 4. Правила работы

- Ветка + PR на каждую задачу (`feat/…`, `fix/…`). **В `main` не пушить**, мёржит пользователь; мёрж = автодеплой.
- **Без атрибуции Claude** в коммитах и PR (никаких `Co-Authored-By: Claude`, «Generated with…»).
- Перед любым UI — прототипы на холсте (Artifact), правки только после утверждения.
- Сервер, БД, чужие сервисы на VPS не трогать без явной просьбы; удалять — только после просмотра и подтверждения (на VPS живут чужие контейнеры: `amnezia-awg` — VPN, не трогать).
- Перед PR: `ruff check`, `ruff format`, `pytest` (бэкенд), `npm run build` (фронт).
- `pytest` идёт на PostgreSQL 16 (SQLite не используем): нужен `docker compose up -d postgres`; база `TEST_DATABASE_URL` (по умолчанию `app_test`) пересоздаётся и мигрируется на каждый прогон, тест — в транзакции с откатом. Подробнее — README.
- Секреты только в `.env` (не коммитить); новые переменные — в `*.example`.

## 5. Состояние (на 25.10)

Сделано:
- Модель данных по `docs/schema.dbml` — 67 таблиц, 25 enum (`src/app/models.py`, `enums.py`); миграции `5e6245fa835f_legacy_baseline` (пустая, ID старой цепочки) → `0001_credit_schema` (сносит старые таблицы, создаёт схему). На VPS применено.
- Auth: регистрация email+пароль + ФИО + ИНН ФЛ (обязателен, проверка контрольной суммы, уникален) + телефон (опц., нормализация +7). Статус сразу `active`. JWT, `/auth/register|login|me`. Блокированный → 403.
- Фронт React 18 + TS + Vite (`frontend/`): лендинг (чёрный верх, плитки, белая секция со скруглёнными углами), меню «Кредиты» → заглушка `/credits?product=…`, `/calculator` (аннуитет, ставка 24% для примера), `/login`, `/register` (красная точка у обязательных), `/profile`. Шрифт Manrope из npm (`@fontsource`), без внешних CDN.
- Docker: фронт собирается в multi-stage образ (node → nginx), `.dockerignore` (секреты и node_modules не попадают в образы), dev-compose работает без `local.env`.
- Симулятор источников (`src/simulator/`) + клиенты `src/app/integrations/` + API кабинета: `GET /companies`, `POST /companies/lookup`, `POST /companies`, `GET /companies/{id}`, `GET /companies/{id}/sources`, `GET /companies/group-summary` (ответы в camelCase — контракт фронта `frontend/src/api/cabinet.ts`); предварительный лимит по DSCR (`src/app/credit/`), прогноз оборотов на 3 мес; seed демо-учёток персон.
- Тесты: 147 API/unit (pytest, PostgreSQL 16, схема через миграции; сверка миграций с моделями — `tests/unit/test_schema.py`; паритет признаков конвейера с обучающей выборкой — `tests/api/test_scoring_parity.py`).
- Скоринг (21.10): синтетика `ml/data/synthetic_v1` (КИ из scoring_maps + бизнес-профиль, 40 тыс.), `ml/research.ipynb`, 4 скоркарты + GBM-ориентир; миграция `0002` — `scoring_segments` (когда какую модель), `ml_dataset_samples`, `model_versions.params`, `credit_obligations.payment_string`; признаки `app/credit/features.py`, скоркарта и выбор сегмента `app/credit/scorecard.py`, `services/scoring.py`; загрузка `python -m app.dataload.synthetic` / `server-load-synthetic.sh`.
- Конвейер (22.10): миграция `0003` — `tasks` (очередь), `loan_applications.idempotency_key` / `sign_code_*`, `credit_decisions.details` (входы, модель, сегмент, варианты, советы); воркер `python -m app.worker` (FOR UPDATE SKIP LOCKED, повторы → `manual_review`); `services/pipeline.py` (сбор данных → стоп-факторы → признаки из БД → скоринг → DSCR → решение); правила — `credit/{statuses,stop_factors,decision,reasons}.py`; API заявки `accept {offerIndex}` / `sign-code` / `sign` / `cancel` / `events` (SSE). Миграция `0004` — номер заявки из sequence (гонки отправки), `sign_code_attempts` (5 неверных вводов — код сгорает); истёкшее предложение не принять (409). Симулятор БКИ отдаёт `payment_string`. Отказ и ручной разбор всегда с причинами и советом; молодой бизнес — мягкий отказ с датой повторной подачи.
- Кабинет администратора (25.10): фронт `/adminuser` (`frontend/src/admin/`), API `/admin/*` (`routes|services|repositories/admin.py`) — компании и разбор скоринга, модели и калькулятор, выборки (решение × факт, champion/challenger, дрейф). Вход сотрудника: `staff_users.login + password_hash`, токен `kind=staff` (не смешивается с клиентским); суперпользователь из env `ADMIN_LOGIN`/`ADMIN_PASSWORD` в `seed`. Миграция `0005`: `staff_users.login/password_hash/last_login_at`, `score_results.features/segment_code/reason_codes/recommended_decision` (пишут конвейер — итог заявки — и загрузка синтетики — рекомендация по грейду, `credit/recommendation.py`), индексы `company_id` (перезаливка синтетики в разы быстрее). Пересчёт клиента — `services/rescoring.py` на `pipeline.gather`.

Дальше (по порядку, сквозной сценарий важнее красоты):
1. ГИР БО (бухотчётность) в симуляторе; загрузка выписки из другого банка (сейчас — флаг `needs_statement`).
2. Seed: продукты, стоп-факторы, андеррайтер (демо-учётки персон §9 уже есть).
3. Кабинет андеррайтера (T-15).

Решено: статусы — короткий путь без новых enum (`submitted → scoring → approved | declined | manual_review → offer_accepted → contract_signed → issued`; контрпредложение — `approved` с решением `counter_offer`; клиенту `scoring`/`manual_review` = «checking», `offer_accepted`/`contract_signed` = «signing»); очередь — таблица `tasks`. Вход сотрудников — `POST /admin/auth/login` (пока только роль admin); кабинет андеррайтера — T-15.

## 6. Инфраструктура и деплой

- Сервисы compose: `postgres` (pg_isready), `app` (FastAPI, при старте `alembic upgrade head` + `python -m app.seed`, healthcheck `/health` = `SELECT 1`), `simulator` (внешние источники, порт 8100, без БД, тот же образ, healthcheck `/health`; в проде без публичного порта), `worker` (конвейер заявок, тот же образ, `python -m app.worker`, healthcheck — свежесть heartbeat-файла), `nginx`/`frontend` (React-сборка + прокси `/auth/`, `/companies`, `/applications`, `/admin/`, `/health`; для `/applications/{id}/events` — без буферизации, SSE). Модели скоринга: в dev грузятся при старте app (`python -m app.dataload.synthetic --models-only`), на сервер — `server-load-synthetic.sh --models-only`; нет модели — заявка на ручной разбор. Планируется `llm` (профиль `ai`) — в оба compose-файла с healthcheck.
- Внешние источники — только по HTTP: `src/app/integrations/<источник>.py` (клиент + адаптер формата), URL из env `EGRUL_URL`, `FNS_URL`, `RMSP_URL`, `FSSP_URL`, `EFRSB_URL`, `ZSK_URL`, `BKI_URL`, `ABS_URL` (сейчас все → `http://simulator:8100`), таймаут/ретраи `SOURCE_*`. Ответ — снимком в `data_fetches`, разбор — в существующие таблицы. app не читает «данные симулятора» в обход API; симулятор не пишет в БД app. Подключить реальный источник = новый URL + адаптер.
- `.github/workflows/deploy.yml`: push в `main` → rsync на VPS `~/credit-risk` (папки `src migrations frontend` с `--delete`) → `docker compose -f docker-compose.prod.yml up -d --build --wait` → `curl /health`. Секреты Actions: `VPS_HOST/USER/SSH_KEY`; на сервере `.env` с `POSTGRES_PASSWORD`, `JWT_SECRET`, `ADMIN_PASSWORD` (вход в `/adminuser`).
- VPS `root@213.176.77.81` (ключ `~/.ssh/credit_risk_deploy`), 1 CPU / 2 ГБ RAM / диск ~84% — следить за местом. Не ломать `/health` и healthcheck'и.
- Локальная проверка прод-стека: `POSTGRES_PASSWORD=… JWT_SECRET=… docker compose -p crtest -f docker-compose.prod.yml up -d --build --wait`.

## 7. Архитектура и стек

Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, PostgreSQL 16 · слои `routes → services → repositories → models` (SQL только в repositories) · кредитная логика — чистые функции в `src/app/credit/` с unit-тестами · конвейер: свой автомат статусов + очередь в Postgres (`FOR UPDATE SKIP LOCKED`) · статусы в реальном времени — SSE · фронт React+TS+Vite, API тем же origin (dev: прокси Vite) · логи JSON с `request_id`.

Структура: `src/app/{routes,services,repositories,credit,integrations,worker,ai}`, `src/simulator/` (в `src`, чтобы деплой копировал его без правки workflow), `ml/`, `frontend/`, `migrations/`, `tests/{unit,api,e2e}`, `docs/`.

Симулятор (`src/simulator/`): ответ по ИНН детерминирован (генератор засеян хэшем ИНН), персоны §9 — фиксированные профили в `personas.py`; эндпоинты `/egrul/{inn}`, `/fns/{inn}`, `/rmsp/{inn}`, `/fssp/{inn}`, `/efrsb/{inn}`, `/zsk/{inn}`, `/bki/{inn}`, `/abs/{inn}/turnovers`, `/health`. Демо-учётки персон (`app/seed.py`, пароль `demo12345`) совпадают с руководителями персон по ФИО + ИНН ФЛ — только свою компанию можно добавить в кабинет.

## 8. Модель данных

Источник — `docs/schema.dbml` (группы: доступ, компании, внешние данные point-in-time, финансы, заявки, антифрод, скоринг, портфель, аудит, аналитика, деньги). Отступления от схемы: `users` + `password_hash`, `email` и `inn_fl` уникальны; id генерирует Python (`uuid4`); enum'ы — native PG с теми же именами. Новые таблицы/поля — только миграцией, `alembic check` должен быть чистым.

## 9. Домен

- Роли: `client`; сотрудники `staff_users` (underwriter, risk_analyst, fraud_analyst, assessor, admin). В компании — `user_company_links.role`: director, founder, accountant, employee_poa (доверенность: готовит, не подписывает).
- Один человек — несколько компаний (переключатель, сводка, лимит по группе).
- Продукты: оборотные (300 тыс–50 млн, 6–60 мес, без залога), линия (до 30 млн, до 18 мес), овердрафт (доля оборотов, до 12 мес, только РКО), под залог (до 50% залога / 150 млн, до 120 мес), льготный. Ставки и пороги — в БД/конфиге.
- Персоны для тестов: идеальный ИП (автоодобрение), ООО с высокой нагрузкой (контрпредложение), молодой бизнес 4 мес (мягкий отказ), просрочка в прошлом (ручной разбор), обороты в другом банке (дозапрос выписки), банкротство (жёсткий отказ), владелец ИП+ООО (группа), бухгалтер по доверенности.

## 10. Конвейер и решение

Шаги: полнота → стоп-факторы (жёсткие: ликвидация/банкротство, красная зона ЗСК, недостоверность ЕГРЮЛ, массовость; мягкие: возраст < порога, налоговый долг, ФССП > порога, текущая просрочка) → сбор данных (снимок ответов) → скоринг → лимит → решение → контрпредложение. Сбой источника: ретраи с backoff, затем `MANUAL_REVIEW`. Переходы статусов — только бэкенд (409 на недопустимый), каждое событие в историю. Отправка идемпотентна (`Idempotency-Key`). Решение хранит версию модели, входы, баллы, коды причин.

- Скоринг: WoE + логрег (скоркарты из `ml/research.ipynb`, синтетика 40 тыс., на сервер по умолчанию 10 тыс.), challenger GBM — ориентир; Score = Offset + Factor·ln((1−PD)/PD), PDO 20, 600 баллов при 50:1; рейтинги A–E (PD <2/4/8/15%). Модель выбирается по `scoring_segments` (priority, условия), champion сегмента или запасной `all`; сейчас активны `new_business`, `sme`, `all` (`ip_micro` выключен — не дал прироста). Итоги — `docs/model-card.md`.
- Лимит: DSCR ≥ 1,25 с учётом долгов группы; `min(запрос, DSCR-аннуитет, правила продукта)`.
- Матрица: A–B → одобрение / контрпредложение; C → ручной разбор / документы; D → контрпредложение с залогом / отказ; E → отказ. 2–3 кода причин простыми словами.
- Контрпредложения на тех же данных без повторного БКИ; никогда больше, чем позволяет DSCR. Пример для тестов: 5 млн / 12 мес / 24%, доход 450 тыс, платежи 100 тыс → 12 мес до ≈2,75 млн; 24 мес до ≈4,92 млн.

## 11. Кабинеты

Клиент: главная (сколько дадут, что с заявкой, что нужно), компании (дашборд из заметок: ОКВЭД, МСП, налоги, ФССП, банкротства, ЗСК, кредиты, обороты и остатки по месяцам с прогнозом; срезы, период, гранулярность, когорты), мастер заявки из 6 шагов с progress-bar и автозаполнением по компании, таймлайн (SSE), решение, подписание. Андеррайтер: очередь с фильтрами, карточка (источники, баллы, причины, расхождения), действия с обязательным комментарием, данные клиента не редактирует.

## 12. ИИ (под флагом)

Порядок: скоркарта (не LLM, обязательно) → разбор выписки PDF (Docling) → сводка андеррайтеру + объяснение клиенту по кодам причин (LLM только формулирует, есть шаблоны-фолбэк). Модели — в THIRD_PARTY_NOTICES.

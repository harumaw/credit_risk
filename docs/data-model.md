# Модель данных

Полная схема — [schema.dbml](schema.dbml) (67 таблиц, 25 перечислений; открывается на dbdiagram.io).
В базе она создаётся миграциями Alembic (`migrations/versions/`), модели SQLAlchemy — `src/app/models.py`;
тест `tests/unit/test_schema.py` проверяет, что миграции и модели совпадают.

Ниже — ключевые таблицы, через которые проходит сценарий «компания → заявка → решение».

## Клиент, компании, заявка, решение

```mermaid
erDiagram
    users ||--o{ user_company_links : "связан с"
    companies ||--o{ user_company_links : ""
    users ||--o{ loan_applications : "подаёт"
    companies ||--o{ loan_applications : "на компанию"
    credit_products ||--o{ loan_applications : "продукт"
    loan_applications ||--o{ application_status_history : "таймлайн"
    loan_applications ||--o{ consents : "согласия"
    loan_applications ||--o{ tasks : "очередь конвейера"
    loan_applications ||--o{ credit_decisions : "решение"
    credit_decisions }o--o| score_results : "по скорингу"

    users {
        uuid id PK
        string email UK
        string inn_fl UK "ИНН физлица"
        string password_hash
    }
    companies {
        uuid id PK
        string inn UK
        string full_name
        enum status "active / liquidating / bankrupt / …"
    }
    user_company_links {
        uuid user_id FK
        uuid company_id FK
        enum role "director / founder / accountant / employee_poa"
        enum status "confirmed — сверено с ЕГРЮЛ"
    }
    credit_products {
        int id PK
        string code UK
        decimal min_amount
        decimal max_amount
        decimal base_rate
    }
    loan_applications {
        uuid id PK
        string number UK "из sequence, с 1001"
        enum status
        decimal requested_amount
        int requested_term_months
        string idempotency_key "уникален вместе с автором"
        char sign_code_hash "sha256 кода подписи"
    }
    application_status_history {
        bigint id PK
        enum from_status
        enum to_status
        uuid changed_by_user_id
        string comment
    }
    tasks {
        bigint id PK
        string kind
        string status "queued / running / done / failed"
        int attempts
        timestamptz run_after
    }
    credit_decisions {
        uuid id PK
        enum decision "approve / counter_offer / decline / manual_review"
        decimal approved_amount
        int approved_term_months
        decimal rate
        text_array reason_codes
        timestamptz offer_expires_at
        jsonb details "входы, модель, варианты, советы"
    }
```

## Данные внешних источников

Каждый ответ источника сохраняется снимком в `data_fetches` (сырой JSON), затем разбирается
в предметные таблицы с датой, на которую данные верны (point-in-time).

```mermaid
erDiagram
    companies ||--o{ data_fetches : "снимки ответов"
    companies ||--o{ tax_debts : "ФНС"
    companies ||--o{ enforcement_proceedings : "ФССП"
    companies ||--o{ bankruptcy_events : "ЕФРСБ"
    companies ||--o{ zsk_statuses : "ЗСК"
    companies ||--o{ credit_obligations : "БКИ"
    credit_obligations ||--o{ obligation_payments : "график"
    companies ||--o{ bank_accounts : "АБС"
    bank_accounts ||--o{ monthly_turnovers : "обороты по месяцам"

    data_fetches {
        uuid id PK
        enum source "egrul / fns / fssp / bki / …"
        enum status
        jsonb raw_payload
    }
    credit_obligations {
        uuid id PK
        string deal_uid
        decimal outstanding "остаток долга"
        int max_dpd
        string payment_string "дисциплина за 48 мес."
    }
    monthly_turnovers {
        uuid account_id FK
        date month
        decimal inflow "приход"
        decimal outflow "расход"
        decimal closing_balance
    }
```

## Скоринг

```mermaid
erDiagram
    scoring_segments ||--o{ model_versions : "модели сегмента"
    model_versions ||--o{ scorecard_bins : "бины и баллы"
    model_versions ||--o{ rating_scale : "балл → грейд, PD"
    model_versions ||--o{ score_results : "расчёты"
    companies ||--o{ score_results : ""
    score_results ||--o{ score_feature_values : "вклад признаков"
    score_results ||--o{ stop_factor_results : "стоп-факторы"
    scorecard_bins ||--o{ score_feature_values : "попавший бин"
    companies ||--o{ ml_dataset_samples : "синтетика"

    scoring_segments {
        string code PK "new_business / sme / all"
        int priority
        jsonb conditions
        bool is_active
    }
    model_versions {
        uuid id PK
        string model_name
        string version
        enum status "champion / challenger"
        decimal gini_oot
    }
    score_results {
        uuid id PK
        uuid application_id "пусто для синтетики"
        decimal total_score
        decimal pd
        string grade "A–E"
        string segment_code
        enum recommended_decision
    }
    ml_dataset_samples {
        uuid company_id FK
        string dataset_code "synthetic_v1"
        string sample "train / valid / oot"
        int target "факт дефолта"
    }
```

- Модель выбирается по первому подошедшему активному сегменту (`scoring_segments.priority`); у сегмента
  рабочая модель — `champion`, иначе запасная `all`.
- `score_feature_values` хранит значение признака, бин и баллы — из них строится разбор «почему такой балл».
- Синтетика (`ml_dataset_samples`) лежит в тех же таблицах, что и данные клиентов, поэтому кабинет
  администратора показывает их одинаково.

## Отступления от schema.dbml

- `users.password_hash`, `staff_users.login` / `password_hash` — вход клиента и сотрудника;
  `users.email` и `users.inn_fl` уникальны.
- Идентификаторы генерирует приложение (`uuid4`), перечисления — нативные типы PostgreSQL с теми же именами.

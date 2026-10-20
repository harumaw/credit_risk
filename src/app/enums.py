"""Перечисления схемы БД (в Postgres — native enum с тем же именем, см. `models.py`)."""

from enum import StrEnum


class UserStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    BLOCKED = "blocked"


class AuthProvider(StrEnum):
    ESIA = "esia"
    PARTNER_BANK = "partner_bank"
    UKEP = "ukep"
    PHONE_OTP = "phone_otp"


class StaffRole(StrEnum):
    UNDERWRITER = "underwriter"
    RISK_ANALYST = "risk_analyst"
    FRAUD_ANALYST = "fraud_analyst"
    ASSESSOR = "assessor"
    ADMIN = "admin"


class CompanyRole(StrEnum):
    DIRECTOR = "director"
    FOUNDER = "founder"
    ACCOUNTANT = "accountant"
    EMPLOYEE_POA = "employee_poa"


class LinkStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REVOKED = "revoked"


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    REORGANIZING = "reorganizing"
    LIQUIDATING = "liquidating"
    LIQUIDATED = "liquidated"
    BANKRUPT = "bankrupt"


class MspCategory(StrEnum):
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    NOT_MSP = "not_msp"


class TaxRegime(StrEnum):
    OSNO = "osno"
    USN_INCOME = "usn_income"
    USN_INCOME_EXPENSE = "usn_income_expense"
    ESHN = "eshn"
    PSN = "psn"
    AUSN = "ausn"


class ZskZone(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class DataSource(StrEnum):
    FNS_EGRUL = "fns_egrul"
    FNS_TAX = "fns_tax"
    GIR_BO = "gir_bo"
    FSSP = "fssp"
    EFRSB = "efrsb"
    KAD_ARBITR = "kad_arbitr"
    CBR_ZSK = "cbr_zsk"
    BKI = "bki"
    RMSP = "rmsp"
    PARTNER_BANK = "partner_bank"
    BANK_INTERNAL = "bank_internal"
    MANUAL = "manual"


class FetchStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"


class ProductType(StrEnum):
    TERM_LOAN = "term_loan"
    CREDIT_LINE = "credit_line"
    OVERDRAFT = "overdraft"
    BANK_GUARANTEE = "bank_guarantee"


class ApplicationStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    DATA_COLLECTION = "data_collection"
    SCORING = "scoring"
    MANUAL_REVIEW = "manual_review"
    APPROVED = "approved"
    OFFER_ACCEPTED = "offer_accepted"
    CONTRACT_SIGNED = "contract_signed"
    ISSUED = "issued"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class ChannelType(StrEnum):
    PAID = "paid"
    ORGANIC = "organic"
    PARTNER = "partner"
    REFERRAL = "referral"
    DIRECT = "direct"
    OFFLINE = "offline"


class EventPlatform(StrEnum):
    WEB = "web"
    IOS = "ios"
    ANDROID = "android"
    BACKEND = "backend"


class LoanTxnType(StrEnum):
    DISBURSEMENT = "disbursement"
    PRINCIPAL_REPAYMENT = "principal_repayment"
    INTEREST_PAYMENT = "interest_payment"
    FEE = "fee"
    PENALTY = "penalty"
    RECOVERY = "recovery"
    WRITE_OFF = "write_off"


class ProvisionStage(StrEnum):
    STAGE_1 = "stage_1"
    STAGE_2 = "stage_2"
    STAGE_3 = "stage_3"


class ConsentType(StrEnum):
    PERSONAL_DATA = "personal_data"
    BKI_REQUEST = "bki_request"
    TAX_SECRET = "tax_secret"
    ESIA_DATA = "esia_data"
    MARKETING = "marketing"


class DecisionType(StrEnum):
    APPROVE = "approve"
    DECLINE = "decline"
    MANUAL_REVIEW = "manual_review"
    COUNTER_OFFER = "counter_offer"


class LoanStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    DEFAULTED = "defaulted"
    WRITTEN_OFF = "written_off"


class DefaultTrigger(StrEnum):
    DPD_90 = "dpd_90"
    BANKRUPTCY = "bankruptcy"
    DISTRESSED_RESTRUCTURING = "distressed_restructuring"
    WRITE_OFF = "write_off"
    UNLIKELY_TO_PAY = "unlikely_to_pay"


class CheckResult(StrEnum):
    PASS = "pass"
    FLAG = "flag"
    FAIL = "fail"


class FraudLabelKind(StrEnum):
    """Enum `fraud_label`; в Python переименован, чтобы не путать с моделью `FraudLabel`."""

    FRAUD = "fraud"
    NOT_FRAUD = "not_fraud"
    SUSPICIOUS = "suspicious"


class ModelStatus(StrEnum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    CHAMPION = "champion"
    CHALLENGER = "challenger"
    RETIRED = "retired"


class StopSeverity(StrEnum):
    HARD = "hard"
    SOFT = "soft"

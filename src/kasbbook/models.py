"""Every model, in one place.

Alembic autogenerate only sees what has been imported. Importing a module for
its side effect is easy to delete by accident, so this file exists to make that
requirement explicit and to give migrations a single, obvious entry point.
"""

from .modules.books.models import Book, Membership, TeamInvitation
from .modules.budgets.models import Budget
from .modules.debts.models import Debt
from .modules.exchange.models import BookCurrency, ConversionAttachment, CurrencyConversion
from .modules.identity.models import (
    ApiKey,
    AccountLoginChallenge,
    AuditEvent,
    Identity,
    LinkToken,
    RefreshToken,
    User,
    WebLoginChallenge,
)
from .modules.capital.models import Asset, CapitalMovement, Fund
from .modules.loans.models import Loan, LoanPayment
from .modules.portfolio.models import FinancialNote, Holding, NoteEntry
from .modules.recurring.models import RecurringOccurrence, RecurringRule
from .modules.ledger.models import (
    Account,
    Category,
    JournalEntry,
    JournalLine,
    Transaction,
    TransactionAttachment,
)
from .modules.payroll.models import (
    Adjustment,
    FinancialPeriod,
    Payment,
    Payslip,
    PerformanceRecord,
    ShareRule,
)
from .modules.treasury.models import (
    TreasuryAllocation,
    TreasuryFund,
    TreasuryRule,
)
from .shared.database import Base

# Everything here is imported for its side effect: Alembic autogenerate only
# sees the tables that have been imported. __all__ is how that intent is
# stated in a way the linter understands, rather than a noqa it ignores.
__all__ = [
    "Base",
    "Account",
    "AccountLoginChallenge",
    "WebLoginChallenge",
    "Category",
    "CurrencyConversion",
    "TeamInvitation",
    "ApiKey",
    "Adjustment",
    "Asset",
    "AuditEvent",
    "Book",
    "BookCurrency",
    "Budget",
    "CapitalMovement",
    "ConversionAttachment",
    "Debt",
    "FinancialNote",
    "FinancialPeriod",
    "Fund",
    "Holding",
    "Identity",
    "JournalEntry",
    "JournalLine",
    "LinkToken",
    "Loan",
    "LoanPayment",
    "Membership",
    "NoteEntry",
    "Payment",
    "Payslip",
    "PerformanceRecord",
    "RefreshToken",
    "RecurringOccurrence",
    "RecurringRule",
    "ShareRule",
    "Transaction",
    "TransactionAttachment",
    "TreasuryAllocation",
    "TreasuryFund",
    "TreasuryRule",
    "User",
]

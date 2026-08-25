"""Every model, in one place.

Alembic autogenerate only sees what has been imported. Importing a module for
its side effect is easy to delete by accident, so this file exists to make that
requirement explicit and to give migrations a single, obvious entry point.
"""

from .modules.books.models import Book, Membership
from .modules.budgets.models import Budget
from .modules.debts.models import Debt
from .modules.identity.models import (
    ApiKey,
    AuditEvent,
    Identity,
    LinkToken,
    RefreshToken,
    User,
)
from .modules.loans.models import Loan, LoanPayment
from .modules.recurring.models import RecurringRule
from .modules.ledger.models import (
    Account,
    JournalEntry,
    JournalLine,
    Transaction,
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
    "ApiKey",
    "Adjustment",
    "AuditEvent",
    "Book",
    "Budget",
    "Debt",
    "FinancialPeriod",
    "Identity",
    "JournalEntry",
    "JournalLine",
    "LinkToken",
    "Loan",
    "LoanPayment",
    "Membership",
    "Payment",
    "Payslip",
    "PerformanceRecord",
    "RefreshToken",
    "RecurringRule",
    "ShareRule",
    "Transaction",
    "TreasuryAllocation",
    "TreasuryFund",
    "TreasuryRule",
    "User",
]

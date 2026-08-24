"""Every model, in one place.

Alembic autogenerate only sees what has been imported. Importing a module for
its side effect is easy to delete by accident, so this file exists to make that
requirement explicit and to give migrations a single, obvious entry point.
"""

from .modules.books.models import Book, Membership  # noqa: F401
from .modules.identity.models import (  # noqa: F401
    AuditEvent,
    Identity,
    LinkToken,
    User,
)
from .modules.ledger.models import (  # noqa: F401
    Account,
    JournalEntry,
    JournalLine,
    Transaction,
)
from .modules.payroll.models import (  # noqa: F401
    Adjustment,
    FinancialPeriod,
    Payment,
    Payslip,
    PerformanceRecord,
    ShareRule,
)
from .modules.treasury.models import (  # noqa: F401
    TreasuryAllocation,
    TreasuryFund,
    TreasuryRule,
)
from .shared.database import Base  # noqa: F401

__all__ = ["Base"]

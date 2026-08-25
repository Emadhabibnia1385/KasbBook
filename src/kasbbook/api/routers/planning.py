"""Budgets, debts and loans — the parts of a book that look forward.

Grouped in one module because they share a shape: a small list per book, each
row carrying a computed status that the caller should not have to recompute.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Query

from ...modules.budgets.models import BudgetKind
from ...modules.budgets.service import BudgetService
from ...modules.debts.models import Direction
from ...modules.debts.service import DebtService
from ...modules.loans.service import LoanService
from ...shared.errors import ValidationError
from ..deps import CurrentUser, SessionDep
from ..schemas import (
    BudgetRequest,
    BudgetResponse,
    DebtRequest,
    DebtResponse,
    LoanRequest,
    LoanResponse,
)

router = APIRouter(prefix="/books/{book_id}", tags=["planning"])


def _as_enum(enum_class, value: str, field: str):
    try:
        return enum_class(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_class)
        raise ValidationError(f"{field} must be one of: {allowed}") from None


# -------------------------------------------------------------- budgets
@router.get("/budgets", response_model=List[BudgetResponse])
async def list_budgets(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[BudgetResponse]:
    """Each budget with what has actually been spent against it this month."""
    return [
        BudgetResponse(
            id=status.budget.id, label=status.label, kind=status.budget.kind.value,
            limit=status.limit, spent=status.spent, remaining=status.remaining,
            percent_used=status.percent,
        )
        for status in await BudgetService(session).status(book_id, user.id)
    ]


@router.put("/budgets", response_model=BudgetResponse)
async def set_budget(
    book_id: uuid.UUID, body: BudgetRequest, user: CurrentUser, session: SessionDep
) -> BudgetResponse:
    """Create or replace. A category has one ceiling, so this is a PUT."""
    budgets = BudgetService(session)
    await budgets.set_budget(
        book_id, user.id, _as_enum(BudgetKind, body.kind, "kind"), body.target, body.amount
    )

    for status in await budgets.status(book_id, user.id):
        if status.budget.target == body.target:
            return BudgetResponse(
                id=status.budget.id, label=status.label, kind=status.budget.kind.value,
                limit=status.limit, spent=status.spent, remaining=status.remaining,
                percent_used=status.percent,
            )
    raise ValidationError("the budget was saved but could not be read back")


@router.delete("/budgets/{budget_id}", status_code=204)
async def delete_budget(
    book_id: uuid.UUID, budget_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await BudgetService(session).delete(book_id, user.id, budget_id)


# ---------------------------------------------------------------- debts
@router.get("/debts", response_model=List[DebtResponse])
async def list_debts(
    book_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    include_settled: bool = Query(default=False),
) -> List[DebtResponse]:
    rows = await DebtService(session).list_debts(book_id, user.id, include_settled)
    return [_debt(row) for row in rows]


@router.post("/debts", response_model=DebtResponse, status_code=201)
async def create_debt(
    book_id: uuid.UUID, body: DebtRequest, user: CurrentUser, session: SessionDep
) -> DebtResponse:
    debt = await DebtService(session).create(
        book_id, user.id, body.person,
        _as_enum(Direction, body.direction, "direction"),
        body.amount, note=body.note, due_on=body.due_on,
    )
    return _debt(debt)


@router.post("/debts/{debt_id}/settle", response_model=DebtResponse)
async def settle_debt(
    book_id: uuid.UUID, debt_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> DebtResponse:
    """Mark it paid. Settling books the matching transaction, which is the point."""
    return _debt(await DebtService(session).settle(book_id, user.id, debt_id))


@router.delete("/debts/{debt_id}", status_code=204)
async def delete_debt(
    book_id: uuid.UUID, debt_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await DebtService(session).delete(book_id, user.id, debt_id)


# ---------------------------------------------------------------- loans
@router.get("/loans", response_model=List[LoanResponse])
async def list_loans(
    book_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> List[LoanResponse]:
    loans = LoanService(session)
    rows = await loans.list_loans(book_id, user.id)
    return [_loan(await loans.progress(book_id, user.id, row)) for row in rows]


@router.post("/loans", response_model=LoanResponse, status_code=201)
async def create_loan(
    book_id: uuid.UUID, body: LoanRequest, user: CurrentUser, session: SessionDep
) -> LoanResponse:
    loans = LoanService(session)
    loan = await loans.create(
        book_id, user.id, body.title, body.installment_amount,
        body.installment_count, body.starts_on,
    )
    return _loan(await loans.progress(book_id, user.id, loan))


@router.post("/loans/{loan_id}/pay", response_model=LoanResponse)
async def pay_installment(
    book_id: uuid.UUID, loan_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> LoanResponse:
    """Record one instalment. It books an expense as well as advancing the loan."""
    loans = LoanService(session)
    loan = await loans.get(book_id, user.id, loan_id)
    await loans.record_payment(book_id, user.id, loan_id)
    return _loan(await loans.progress(book_id, user.id, loan))


@router.delete("/loans/{loan_id}", status_code=204)
async def delete_loan(
    book_id: uuid.UUID, loan_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    await LoanService(session).delete(book_id, user.id, loan_id)


def _debt(row) -> DebtResponse:
    return DebtResponse(
        id=row.id, person=row.person, amount=row.amount,
        direction=row.direction.value, is_settled=row.settled_at is not None,
        due_on=row.due_on, note=row.note,
    )


def _loan(progress) -> LoanResponse:
    loan = progress.loan
    return LoanResponse(
        id=loan.id, title=loan.title,
        installment_amount=loan.installment_amount,
        installment_count=loan.installment_count,
        paid_count=progress.paid_count, paid_amount=progress.paid_amount,
        remaining=progress.remaining_amount, percent_paid=progress.percent,
        next_due_on=progress.next_due,
    )

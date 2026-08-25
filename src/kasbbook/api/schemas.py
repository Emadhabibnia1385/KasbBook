"""Request and response shapes.

Money crosses this boundary as a string, never a number. JSON has one numeric
type and it is a float; 12_500_000.15 does not survive the trip intact, and a
bookkeeping API that loses rials is not a bookkeeping API.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MoneyModel(Model):
    """Base for anything carrying a Decimal, so the rule is applied once."""

    @field_serializer("*", when_used="json")
    def _decimals_as_strings(self, value):
        return str(value) if isinstance(value, Decimal) else value


# ----------------------------------------------------------------- auth
class RegisterRequest(Model):
    display_name: str = Field(min_length=1, max_length=120)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(Model):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(Model):
    refresh_token: str = Field(min_length=1)


class TokenResponse(Model):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class UserResponse(Model):
    id: uuid.UUID
    display_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    locale: str
    timezone: str
    digest_enabled: bool
    digest_hour: int
    reminder_days: int


class SessionResponse(Model):
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None


class ApiKeyRequest(Model):
    name: str = Field(min_length=1, max_length=80)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650)


class ApiKeyResponse(Model):
    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


class ApiKeyCreated(ApiKeyResponse):
    """The only response that ever contains the key itself."""

    key: str


# ----------------------------------------------------------- identities
class IdentityResponse(Model):
    id: uuid.UUID
    provider: str
    external_id: str
    external_username: Optional[str] = None
    display_name: Optional[str] = None
    linked_at: datetime


class StartLinkRequest(Model):
    provider: str


class StartLinkResponse(Model):
    token: str
    expires_at: str
    deep_link: Optional[str] = None


class ClaimLinkRequest(Model):
    code: str = Field(min_length=1, max_length=64)


# ---------------------------------------------------------------- books
class BookRequest(Model):
    name: str = Field(min_length=1, max_length=120)
    type: str
    currency: str = "IRR"


class BookResponse(Model):
    id: uuid.UUID
    name: str
    type: str
    currency: str
    created_at: datetime


class MemberResponse(Model):
    user_id: uuid.UUID
    display_name: str
    role: str


class InviteRequest(Model):
    identifier: str = Field(min_length=1, max_length=320)
    role: str


# --------------------------------------------------------- transactions
class TransactionRequest(MoneyModel):
    flow: str
    category: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0)
    currency: str = "IRR"
    description: Optional[str] = Field(default=None, max_length=500)
    occurred_on: Optional[date] = None
    scope: Optional[str] = None


class TransactionResponse(MoneyModel):
    id: uuid.UUID
    flow: str
    scope: str
    category: str
    original_amount: Decimal
    original_currency: str
    converted_amount: Decimal
    description: Optional[str] = None
    occurred_on: date
    created_at: datetime


class TransactionPage(Model):
    items: List[TransactionResponse]
    total: int
    page: int
    per_page: int


# -------------------------------------------------------------- reports
class SummaryResponse(MoneyModel):
    income: Decimal
    expense: Decimal
    net: Decimal
    transaction_count: int


class CategoryLine(MoneyModel):
    category: str
    total: Decimal
    share_percent: Decimal


# -------------------------------------------------- budgets, debts, loans
class BudgetRequest(MoneyModel):
    target: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0)
    # "category" caps one named category; "flow" caps everything going one way.
    kind: str = "category"


class BudgetResponse(MoneyModel):
    id: uuid.UUID
    label: str
    kind: str
    limit: Decimal
    spent: Decimal
    remaining: Decimal
    percent_used: int


class DebtRequest(MoneyModel):
    person: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0)
    direction: str
    due_on: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=500)


class DebtResponse(MoneyModel):
    id: uuid.UUID
    person: str
    amount: Decimal
    direction: str
    is_settled: bool
    due_on: Optional[date] = None
    note: Optional[str] = None


class LoanRequest(MoneyModel):
    title: str = Field(min_length=1, max_length=120)
    # The amount of one instalment, not the total. That is how the domain
    # models a loan and how a person is told about one: "twelve of 4,000,000".
    installment_amount: Decimal = Field(gt=0)
    installment_count: int = Field(gt=0, le=600)
    starts_on: date


class LoanResponse(MoneyModel):
    id: uuid.UUID
    title: str
    installment_amount: Decimal
    installment_count: int
    paid_count: int
    paid_amount: Decimal
    remaining: Decimal
    percent_paid: int
    next_due_on: Optional[date] = None


class HealthResponse(Model):
    status: str
    database: str
    version: str

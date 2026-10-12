"""Idempotency-Key: a retried request that moves money is answered again, not done again.

Each test counts what was written, not only what was answered: a replay that
returns the right body while booking a second transaction would pass any test
that only read the response.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.modules.idempotency.models import IdempotencyKey
from kasbbook.modules.ledger.models import Transaction
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.security import utcnow
from kasbbook.shared.settings import Settings
from tests.test_api_auth import SECRET, bearer, register

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def _book(api, headers):
    return (await api.post("/api/v1/books", headers=headers,
                           json={"name": "مغازه", "type": "business"})).json()


async def _count(db, book_id):
    async for session in db.session():
        rows = (await session.execute(
            select(Transaction).where(Transaction.book_id == uuid.UUID(book_id))
        )).scalars().all()
        balance = await LedgerService(session).trial_balance(uuid.UUID(book_id))
        return len(rows), balance


SALE = {"flow": "income", "category": "فروش", "amount": "250000"}


# ------------------------------------------------------------------ replay
async def test_a_retry_with_the_same_key_gets_the_first_answer_and_books_once(api, db):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    url = f"/api/v1/books/{book['id']}/transactions"
    keyed = {**headers, "Idempotency-Key": "retry-0001"}

    first = await api.post(url, headers=keyed, json=SALE)
    second = await api.post(url, headers=keyed, json=SALE)

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert second.headers.get("Idempotent-Replay") == "true"
    assert "Idempotent-Replay" not in first.headers
    assert await _count(db, book["id"]) == (1, (Decimal("250000"), Decimal("250000")))


async def test_no_key_means_no_protection_and_no_change(api, db):
    """Optional everywhere but payslip payments: an existing client is unaffected."""
    headers = bearer(await register(api))
    book = await _book(api, headers)
    url = f"/api/v1/books/{book['id']}/transactions"

    for _ in range(2):
        assert (await api.post(url, headers=headers, json=SALE)).status_code == 201
    assert (await _count(db, book["id"]))[0] == 2


# ---------------------------------------------------------------- refusals
async def test_the_same_key_with_a_different_request_is_refused(api, db):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    url = f"/api/v1/books/{book['id']}/transactions"
    keyed = {**headers, "Idempotency-Key": "retry-0002"}

    assert (await api.post(url, headers=keyed, json=SALE)).status_code == 201
    other = await api.post(url, headers=keyed, json={**SALE, "amount": "999999"})

    assert other.status_code == 422
    assert (await _count(db, book["id"]))[0] == 1


@pytest.mark.parametrize("key", ["short", "x" * 65, "has space in it", "has/a/slash/in-it"])
async def test_a_malformed_key_is_refused_before_anything_is_written(api, db, key):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    reply = await api.post(f"/api/v1/books/{book['id']}/transactions",
                           headers={**headers, "Idempotency-Key": key}, json=SALE)
    assert reply.status_code == 400
    assert (await _count(db, book["id"]))[0] == 0


async def test_a_key_whose_first_request_is_still_running_is_refused(db):
    """The first claim is made and not yet answered; a second identical one waits its turn."""
    from kasbbook.modules.idempotency.service import IdempotencyService, KeyInFlight
    from kasbbook.modules.identity.service import IdentityService

    async for session in db.session():
        user = await IdentityService(session).create_user("عماد")
        service = IdempotencyService(session)
        first = await service.claim(user.id, "retry-0003", "POST", "/x", "a" * 64)
        assert first.row is not None and not first.is_replay
        with pytest.raises(KeyInFlight):
            await service.claim(user.id, "retry-0003", "POST", "/x", "a" * 64)


# ------------------------------------------------------------- what is kept
async def test_a_request_that_failed_leaves_its_key_free_to_retry(api, db):
    """A refusal rolls back the reservation with the work, so the key is not burned."""
    headers = bearer(await register(api))
    book = await _book(api, headers)
    url = f"/api/v1/books/{book['id']}/transactions"
    keyed = {**headers, "Idempotency-Key": "retry-0004"}

    # A currency the book never enabled: refused inside the service, after the claim.
    refused = await api.post(url, headers=keyed,
                             json={**SALE, "currency": "USDT", "conversion_rate": "100000"})
    assert refused.status_code == 422

    fixed = await api.post(url, headers=keyed, json=SALE)
    assert fixed.status_code == 201
    assert "Idempotent-Replay" not in fixed.headers
    assert (await _count(db, book["id"]))[0] == 1


async def test_a_key_past_its_window_is_a_new_key(api, db):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    url = f"/api/v1/books/{book['id']}/transactions"
    keyed = {**headers, "Idempotency-Key": "retry-0005"}
    assert (await api.post(url, headers=keyed, json=SALE)).status_code == 201

    async for session in db.session():
        await session.execute(update(IdempotencyKey).values(expires_at=utcnow() - timedelta(seconds=1)))
        await session.commit()

    again = await api.post(url, headers=keyed, json={**SALE, "amount": "1000"})
    assert again.status_code == 201
    assert (await _count(db, book["id"]))[0] == 2


# ---------------------------------------------------------------- isolation
async def test_two_people_using_the_same_key_do_not_share_an_answer(api, db):
    mine = bearer(await register(api))
    theirs = bearer(await register(api, email="other@example.com"))
    my_book, their_book = await _book(api, mine), await _book(api, theirs)

    for headers, book in ((mine, my_book), (theirs, their_book)):
        reply = await api.post(f"/api/v1/books/{book['id']}/transactions",
                               headers={**headers, "Idempotency-Key": "shared-key-1"}, json=SALE)
        assert reply.status_code == 201
        assert "Idempotent-Replay" not in reply.headers

    assert (await _count(db, my_book["id"]))[0] == 1
    assert (await _count(db, their_book["id"]))[0] == 1


# ----------------------------------------------------- where money leaves
async def test_a_payslip_payment_requires_a_key_and_pays_once_per_key(api, db):
    from tests.test_api_payroll import workspace

    headers, book, owner, colleague = await workspace(api, None)
    base = f"/api/v1/books/{book['id']}"
    await api.put(f"{base}/shares", headers=headers,
                  json={"user_id": colleague["id"], "basis": "percent", "value": "100",
                        "effective_from": "2026-01-01"})
    period = (await api.post(f"{base}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()
    slip = (await api.post(f"{base}/periods/{period['id']}/calculate", headers=headers)).json()[0]
    url = f"{base}/payslips/{slip['id']}/payments"

    missing = await api.post(url, headers=headers, json={"amount": "1000000"})
    assert missing.status_code == 400
    assert "Idempotency-Key" in missing.json()["detail"]

    keyed = {**headers, "Idempotency-Key": "payslip-pay-1"}
    first = await api.post(url, headers=keyed, json={"amount": "1000000"})
    second = await api.post(url, headers=keyed, json={"amount": "1000000"})
    assert first.status_code == second.status_code == 201
    assert second.headers.get("Idempotent-Replay") == "true"

    slips = (await api.get(f"{base}/periods/{period['id']}/payslips", headers=headers)).json()
    assert slips[0]["paid"] == "1000000.0000"


async def test_a_loan_payment_retried_with_its_key_pays_one_instalment(api, db):
    headers = bearer(await register(api))
    book = await _book(api, headers)
    loan = (await api.post(f"/api/v1/books/{book['id']}/loans", headers=headers,
                           json={"title": "وام", "installment_amount": "1000",
                                 "installment_count": 6, "starts_on": "2026-01-01"})).json()
    url = f"/api/v1/books/{book['id']}/loans/{loan['id']}/pay"
    keyed = {**headers, "Idempotency-Key": "loan-pay-0001"}

    first = await api.post(url, headers=keyed)
    second = await api.post(url, headers=keyed)

    assert first.status_code == second.status_code == 200
    assert second.json()["paid_count"] == 1
    assert (await _count(db, book["id"]))[0] == 1

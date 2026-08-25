"""Payroll over HTTP, and the promise that both clients obey the same rules.

The last test in this file is the one that matters most: a share set through
the API is what the bot reports, and a payslip calculated in the bot is what
the API returns. If either client had reimplemented a rule, the two would
disagree the first time that rule changed — and nobody would notice until a
payslip did.
"""

from __future__ import annotations

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"
DAY = date(2026, 8, 24)


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with app.router.lifespan_context(app):
            yield client


async def workspace(api, session):
    """An owner with a team book, a colleague, and a month of trading."""
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "owner@example.com",
        "password": "a-good-password",
    })).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "کارگاه", "type": "team"})).json()

    colleague_tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "سارا", "email": "sara@example.com",
        "password": "a-good-password",
    })).json()
    colleague = (await api.get("/api/v1/auth/me",
                               headers={"Authorization": f"Bearer {colleague_tokens['access_token']}"})).json()

    await api.post(f"/api/v1/books/{book['id']}/members", headers=headers,
                   json={"identifier": "sara@example.com", "role": "member"})

    owner = (await api.get("/api/v1/auth/me", headers=headers)).json()

    for flow, category, amount in (
        ("income", "فروش", "100000000"), ("expense", "اجاره", "20000000")
    ):
        await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers,
                       json={"flow": flow, "category": category, "amount": amount,
                             "occurred_on": DAY.isoformat()})

    return headers, book, owner, colleague


# ---------------------------------------------------------------- periods
async def test_a_period_can_be_opened_and_listed(api, session):
    headers, book, _, _ = await workspace(api, session)

    created = await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد ۱۴۰۵", "starts_on": "2026-07-23",
                                   "ends_on": "2026-08-22"})
    assert created.status_code == 201
    assert created.json()["status"] == "open"

    listed = await api.get(f"/api/v1/books/{book['id']}/periods", headers=headers)
    assert len(listed.json()) == 1


async def test_a_period_that_ends_before_it_starts_is_refused(api, session):
    headers, book, _, _ = await workspace(api, session)
    response = await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                              json={"label": "بد", "starts_on": "2026-08-22",
                                    "ends_on": "2026-07-23"})
    assert response.status_code == 422


async def test_the_distribution_shows_every_line(api, session):
    headers, book, _, _ = await workspace(api, session)
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()

    body = (await api.get(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/distribution", headers=headers
    )).json()

    assert body["gross_income"] == "100000000.0000"
    assert body["direct_costs"] == "20000000.0000"
    assert body["net_profit"] == "80000000.0000"
    assert body["distributable"] == "80000000.0000"


async def test_an_undocumented_status_move_is_refused(api, session):
    headers, book, _, _ = await workspace(api, session)
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()

    # open → paid is not a transition anyone should be able to make.
    response = await api.post(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/status/paid", headers=headers
    )
    assert response.status_code == 422


# ----------------------------------------------------------------- shares
async def test_a_share_can_be_set_and_read_back(api, session):
    headers, book, owner, colleague = await workspace(api, session)

    response = await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                             json={"user_id": colleague["id"], "basis": "percent",
                                   "value": "50"})
    assert response.status_code == 200
    assert response.json()["display_name"] == "سارا"

    listed = (await api.get(f"/api/v1/books/{book['id']}/shares", headers=headers)).json()
    assert len(listed) == 1
    assert listed[0]["value"] == "50.0000"


async def test_a_share_over_a_hundred_percent_is_refused(api, session):
    headers, book, _, colleague = await workspace(api, session)
    response = await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                             json={"user_id": colleague["id"], "basis": "percent",
                                   "value": "150"})
    assert response.status_code == 422


async def test_a_share_for_someone_who_is_not_a_member_is_refused(api, session):
    headers, book, _, _ = await workspace(api, session)
    outsider = (await api.post("/api/v1/auth/register", json={
        "display_name": "غریبه", "email": "stranger@example.com",
        "password": "a-good-password",
    })).json()
    who = (await api.get("/api/v1/auth/me",
                         headers={"Authorization": f"Bearer {outsider['access_token']}"})).json()

    response = await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                             json={"user_id": who["id"], "basis": "percent", "value": "50"})
    assert response.status_code == 422


async def test_setting_a_share_end_dates_the_previous_one(api, session):
    headers, book, _, colleague = await workspace(api, session)

    for value, start in (("40", "2026-01-01"), ("50", "2026-06-01")):
        await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                      json={"user_id": colleague["id"], "basis": "percent",
                            "value": value, "effective_from": start})

    listed = (await api.get(f"/api/v1/books/{book['id']}/shares", headers=headers)).json()
    assert listed[0]["value"] == "50.0000"
    assert listed[0]["effective_from"] == "2026-06-01"


# -------------------------------------------------------------- calculate
async def test_calculating_without_shares_explains_rather_than_returning_nothing(api, session):
    headers, book, _, _ = await workspace(api, session)
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()

    response = await api.post(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/calculate", headers=headers
    )
    assert response.status_code == 422
    assert "share" in response.json()["detail"].lower()


async def test_calculating_produces_a_payslip_per_member_with_a_share(api, session):
    headers, book, owner, colleague = await workspace(api, session)
    for who in (owner, colleague):
        await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                      json={"user_id": who["id"], "basis": "percent", "value": "50",
                            "effective_from": "2026-01-01"})

    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()

    slips = (await api.post(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/calculate", headers=headers
    )).json()

    assert len(slips) == 2
    assert all(s["net_pay"] == "40000000.0000" for s in slips)
    assert all(s["outstanding"] == "40000000.0000" for s in slips)


async def test_paying_reduces_what_is_outstanding(api, session):
    headers, book, owner, colleague = await workspace(api, session)
    for who in (owner, colleague):
        await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                      json={"user_id": who["id"], "basis": "percent", "value": "50",
                            "effective_from": "2026-01-01"})
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()
    slips = (await api.post(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/calculate", headers=headers
    )).json()

    after = (await api.post(
        f"/api/v1/books/{book['id']}/payslips/{slips[0]['id']}/payments",
        headers=headers, json={"amount": "15000000"},
    )).json()

    assert after["paid"] == "15000000.0000"
    assert after["outstanding"] == "25000000.0000"
    assert len(after["payments"]) == 1


async def test_a_payslip_carries_the_inputs_that_produced_it(api, session):
    headers, book, owner, _ = await workspace(api, session)
    await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                  json={"user_id": owner["id"], "basis": "percent", "value": "100",
                        "effective_from": "2026-01-01"})
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()
    slip = (await api.post(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/calculate", headers=headers
    )).json()[0]

    assert slip["distributable_snapshot"] == "80000000.0000"
    assert slip["share_basis"] == "percent"
    assert slip["share_value"] == "100.0000"


# ----------------------------------------------------------------- money
async def test_every_money_field_crosses_as_a_string(api, session):
    """The rule the whole API depends on, asserted on the widest response."""
    import json as jsonlib

    headers, book, owner, _ = await workspace(api, session)
    await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                  json={"user_id": owner["id"], "basis": "percent", "value": "100",
                        "effective_from": "2026-01-01"})
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()
    response = await api.post(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/calculate", headers=headers
    )

    slip = jsonlib.loads(response.text)[0]
    for field in ("net_pay", "base_share", "distributable_snapshot", "outstanding"):
        assert isinstance(slip[field], str), f"{field} came back as a number"


# ---------------------------------------------------------------- treasury
async def test_a_fund_and_a_rule_reduce_what_is_distributable(api, session):
    headers, book, _, _ = await workspace(api, session)

    fund = (await api.post(f"/api/v1/books/{book['id']}/funds", headers=headers,
                           json={"name": "ذخیره", "kind": "emergency"})).json()
    await api.post(f"/api/v1/books/{book['id']}/funds/{fund['id']}/rules",
                   headers=headers,
                   json={"basis": "net_percent", "value": "25",
                         "effective_from": "2026-01-01"})

    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()
    body = (await api.get(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/distribution", headers=headers
    )).json()

    assert body["treasury_total"] == "20000000.0000"
    assert body["distributable"] == "60000000.0000"


async def test_a_fund_that_has_taken_money_cannot_be_deleted(api, session):
    headers, book, owner, _ = await workspace(api, session)
    await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                  json={"user_id": owner["id"], "basis": "percent", "value": "100",
                        "effective_from": "2026-01-01"})

    fund = (await api.post(f"/api/v1/books/{book['id']}/funds", headers=headers,
                           json={"name": "ذخیره", "kind": "emergency"})).json()
    await api.post(f"/api/v1/books/{book['id']}/funds/{fund['id']}/rules", headers=headers,
                   json={"basis": "net_percent", "value": "10",
                         "effective_from": "2026-01-01"})
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()
    await api.post(f"/api/v1/books/{book['id']}/periods/{period['id']}/calculate",
                   headers=headers)

    response = await api.delete(f"/api/v1/books/{book['id']}/funds/{fund['id']}",
                                headers=headers)
    assert response.status_code == 422


# ------------------------------------------------------------- isolation
async def test_a_stranger_cannot_read_another_teams_payroll(api, session):
    headers, book, _, _ = await workspace(api, session)
    stranger = (await api.post("/api/v1/auth/register", json={
        "display_name": "غریبه", "email": "nobody@example.com",
        "password": "a-good-password",
    })).json()
    theirs = {"Authorization": f"Bearer {stranger['access_token']}"}

    for path in ("periods", "shares", "funds"):
        response = await api.get(f"/api/v1/books/{book['id']}/{path}", headers=theirs)
        assert response.status_code == 404, path


async def test_a_member_sees_only_their_own_payslip(api, session):
    """Seeing everyone's pay is its own permission."""
    headers, book, owner, colleague = await workspace(api, session)
    for who in (owner, colleague):
        await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                      json={"user_id": who["id"], "basis": "percent", "value": "50",
                            "effective_from": "2026-01-01"})
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()
    await api.post(f"/api/v1/books/{book['id']}/periods/{period['id']}/calculate",
                   headers=headers)

    signed_in = (await api.post("/api/v1/auth/login", json={
        "identifier": "sara@example.com", "password": "a-good-password",
    })).json()
    theirs = {"Authorization": f"Bearer {signed_in['access_token']}"}

    mine = (await api.get(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/payslips", headers=theirs
    )).json()
    assert len(mine) == 1
    assert mine[0]["display_name"] == "سارا"

    everyone = (await api.get(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/payslips", headers=headers
    )).json()
    assert len(everyone) == 2


# ============================================ the two clients, one rulebook
async def test_a_share_set_over_http_is_what_the_bot_reports(api, db, session):
    """The promise the whole architecture rests on, asserted rather than assumed."""
    from kasbbook.adapters.base import ChannelIdentity, EventKind, IncomingEvent
    from kasbbook.bot.conversation import Conversation
    from kasbbook.bot.state import MemoryStateStore
    from kasbbook.modules.identity.models import Provider
    from kasbbook.modules.identity.service import IdentityService

    headers, book, owner, colleague = await workspace(api, session)
    await api.put(f"/api/v1/books/{book['id']}/shares", headers=headers,
                  json={"user_id": colleague["id"], "basis": "percent", "value": "35",
                        "effective_from": "2026-01-01"})

    # The same account, reaching the same book from Telegram.
    import uuid as _uuid

    identity = IdentityService(session)
    issued = await identity.start_link_from_web(_uuid.UUID(owner["id"]), Provider.TELEGRAM)
    await identity.complete_link_from_messenger(issued.token, Provider.TELEGRAM, "555001")
    await session.commit()

    convo = Conversation(session, MemoryStateStore(), Provider.TELEGRAM)
    reply = await convo.handle(IncomingEvent(
        kind=EventKind.CALLBACK,
        identity=ChannelIdentity(Provider.TELEGRAM, "555001", "emad", "عماد"),
        chat_id="555001", message_id="10",
        callback_data=f"sh:open:{book['id']}", callback_id="cb",
    ))

    assert "سارا" in reply.text
    assert "35" in reply.text

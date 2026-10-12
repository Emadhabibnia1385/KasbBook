"""The bot and the API obey the same rules, because the rules live in services.

Each section here is a rule that once lived in one client only, so the other
client either broke it or never had it. The tests pin the rule at the service
and then show that both doors reach it.
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.models import SCOPE_FOR_BOOK, Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.settings import Settings
from tests.test_api_auth import SECRET, bearer, register
from tests.test_api_payroll import paying, tether_payslip, workspace

pytestmark = pytest.mark.asyncio

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "kasbbook"


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


# ------------------------------------------------------------ default scope
@pytest.mark.parametrize("book_type, expected", [
    (BookType.PERSONAL, Scope.PERSONAL),
    (BookType.BUSINESS, Scope.WORK),
    (BookType.TEAM, Scope.TEAM),
    (BookType.ORGANIZATION, Scope.TEAM),
])
async def test_an_entry_with_no_scope_takes_its_books(session, book_type, expected):
    user = await IdentityService(session).create_user("عماد")
    book = await BookService(session).create_book(user.id, "دفتر", book_type)

    tx = await LedgerService(session).record(book.id, user.id, Flow.INCOME, None,
                                             "فروش", "1000")

    assert tx.scope is expected
    assert await LedgerService(session).trial_balance(book.id) == (Decimal("1000"),
                                                                  Decimal("1000"))


async def test_a_named_scope_still_wins(session):
    user = await IdentityService(session).create_user("عماد")
    book = await BookService(session).create_book(user.id, "تیم", BookType.TEAM)

    tx = await LedgerService(session).record(book.id, user.id, Flow.EXPENSE,
                                             Scope.PERSONAL, "قسط", "1000")

    assert tx.scope is Scope.PERSONAL


async def test_every_book_type_has_a_default_scope():
    assert set(SCOPE_FOR_BOOK) == set(BookType)


@pytest.mark.parametrize("book_type, expected", [
    ("personal", "personal"), ("business", "work"), ("team", "team"),
])
async def test_the_api_defaults_the_scope_as_the_bot_does(api, book_type, expected):
    headers = bearer(await register(api))
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "دفتر", "type": book_type})).json()

    made = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers,
                          json={"flow": "income", "category": "فروش", "amount": "1000"})

    assert made.status_code == 201, made.text
    assert made.json()["scope"] == expected


async def test_a_stranger_recording_without_a_scope_still_gets_404(api):
    """The route used to look the book up to pick a scope; now the service does, behind its gate."""
    owner = bearer(await register(api))
    book = (await api.post("/api/v1/books", headers=owner,
                           json={"name": "دفتر", "type": "business"})).json()
    stranger = bearer(await register(api, email="other@example.com"))

    made = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=stranger,
                          json={"flow": "income", "category": "فروش", "amount": "1000"})

    assert made.status_code == 404


def _assignments_of(name: str):
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(node, ast.AnnAssign) else [])
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                yield path.relative_to(SRC).as_posix()


async def test_the_scope_table_is_defined_once():
    """It was copied into the bot, the API router and the recurring loop."""
    assert list(_assignments_of("SCOPE_FOR_BOOK")) == ["modules/ledger/models.py"]


# --------------------------------------------------- paying a payslip's worth
def _payments(book, slip):
    return f"/api/v1/books/{book['id']}/payslips/{slip['id']}/payments"


async def test_part_of_a_payslip_paid_in_tether_is_rounded_up_by_the_service(api, session):
    """10,000,000 toman at 300,000 is 33.3333… tether: 33.3334 is handed over, as the bot does."""
    headers, book, _, slip = await tether_payslip(api, session)

    reply = await api.post(_payments(book, slip), headers=paying(headers),
                           json={"settles": "10000000", "currency": "USDT",
                                 "conversion_rate": "300000"})

    assert reply.status_code == 201, reply.text
    after = reply.json()
    assert after["payments"][0]["amount"] == "33.3334"
    assert after["paid"] == "10000020.0000"
    assert after["outstanding"] == "39999980.0000"


async def test_the_rest_in_tether_settles_the_payslip_and_is_not_an_overpayment(api, session):
    headers, book, _, slip = await tether_payslip(api, session)

    after = (await api.post(_payments(book, slip), headers=paying(headers),
                            json={"rest": True, "currency": "USDT",
                                  "conversion_rate": "600000"})).json()

    assert after["payments"][0]["amount"] == "83.3334"     # 50,000,000 / 600,000, up
    # 40 toman past the figure: inside the one-unit allowance, so settled, and
    # not reported as an overpayment.
    assert after["outstanding"] == "-40.0000"
    assert after["overpaid"] == "0.0000"


async def test_the_rest_in_the_payslips_own_currency_is_exactly_what_was_owed(api, session):
    headers, book, _, slip = await tether_payslip(api, session)
    await api.post(_payments(book, slip), headers=paying(headers), json={"amount": "1000"})

    after = (await api.post(_payments(book, slip), headers=paying(headers),
                            json={"rest": True})).json()

    assert sorted(p["amount"] for p in after["payments"]) == ["1000.0000", "49999000.0000"]
    assert after["outstanding"] == "0.0000"


async def test_the_rest_of_a_settled_payslip_is_refused(api, session):
    headers, book, _, slip = await tether_payslip(api, session)
    await api.post(_payments(book, slip), headers=paying(headers), json={"rest": True})

    again = await api.post(_payments(book, slip), headers=paying(headers), json={"rest": True})

    assert again.status_code == 422
    assert "چیزی مانده نیست" in again.json()["detail"]


@pytest.mark.parametrize("body", [
    {},
    {"amount": "1000", "rest": True},
    {"amount": "1000", "settles": "1000"},
    {"settles": "1000", "rest": True},
])
async def test_exactly_one_way_of_saying_how_much(api, session, body):
    headers, book, period, slip = await tether_payslip(api, session)

    reply = await api.post(_payments(book, slip), headers=paying(headers), json=body)

    assert reply.status_code == 422
    listed = (await api.get(f"/api/v1/books/{book['id']}/periods/{period['id']}/payslips",
                            headers=headers)).json()
    assert next(s for s in listed if s["id"] == slip["id"])["paid"] == "0.0000"


async def test_a_tether_worth_without_a_rate_is_refused(api, session):
    headers, book, _, slip = await tether_payslip(api, session)

    reply = await api.post(_payments(book, slip), headers=paying(headers),
                           json={"settles": "1000", "currency": "USDT"})

    assert reply.status_code == 422


# ----------------------------------------------------------- one payslip
async def _colleague(api):
    tokens = (await api.post("/api/v1/auth/login", json={
        "identifier": "sara@example.com", "password": "a-good-password"})).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_a_member_reads_their_own_payslip_and_not_anyone_elses(api, session):
    headers, book, period, mine = await tether_payslip(api, session)
    slips = (await api.get(f"/api/v1/books/{book['id']}/periods/{period['id']}/payslips",
                           headers=headers)).json()
    theirs = next(s for s in slips if s["id"] != mine["id"])
    colleague = await _colleague(api)

    own = await api.get(f"/api/v1/books/{book['id']}/payslips/{theirs['id']}",
                        headers=colleague)
    others = await api.get(f"/api/v1/books/{book['id']}/payslips/{mine['id']}",
                           headers=colleague)
    owner_reads = await api.get(f"/api/v1/books/{book['id']}/payslips/{theirs['id']}",
                                headers=headers)

    assert own.status_code == 200 and own.json()["id"] == theirs["id"]
    # Not 403: a payslip someone may not see does not exist for them.
    assert others.status_code == 404
    assert owner_reads.status_code == 200


async def test_a_stranger_and_the_wrong_book_both_get_404_for_a_payslip(api, session):
    headers, book, _, slip = await tether_payslip(api, session)
    other = (await api.post("/api/v1/books", headers=headers,
                            json={"name": "دیگری", "type": "team"})).json()
    stranger = bearer(await register(api, email="stranger@example.com"))

    assert (await api.get(f"/api/v1/books/{book['id']}/payslips/{slip['id']}",
                          headers=stranger)).status_code == 404
    assert (await api.get(f"/api/v1/books/{other['id']}/payslips/{slip['id']}",
                          headers=headers)).status_code == 404
    assert (await api.get(f"/api/v1/books/{book['id']}/payslips/{uuid.uuid4()}",
                          headers=headers)).status_code == 404


async def test_the_service_hides_another_members_payslip(session):
    from kasbbook.modules.books.models import Role
    from kasbbook.modules.payroll.models import ShareBasis
    from kasbbook.modules.payroll.service import PayrollService
    from kasbbook.shared.errors import NotFound

    day = date(2026, 8, 24)
    identity = IdentityService(session)
    owner = await identity.create_user("عماد")
    member = await identity.create_user("سارا")
    books = BookService(session)
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)
    await books.add_member(owner.id, book.id, member.id, Role.MEMBER)
    await LedgerService(session).record(book.id, owner.id, Flow.INCOME, None, "پروژه",
                                        "1000", occurred_on=day)
    payroll = PayrollService(session)
    for who in (owner, member):
        await payroll.set_share(book.id, owner.id, who.id, ShareBasis.PERCENT, 50,
                                effective_from=day)
    period = await payroll.open_period(owner.id, book.id, "مرداد", day, day)
    slips = {s.user_id: s for s in await payroll.calculate(owner.id, period.id)}

    assert (await payroll.get_payslip(member.id, slips[member.id].id)).id == slips[member.id].id
    with pytest.raises(NotFound):
        await payroll.get_payslip(member.id, slips[owner.id].id)
    assert (await payroll.get_payslip(owner.id, slips[member.id].id)).id == slips[member.id].id


# ------------------------------------------------- a period in the wrong book
async def test_a_period_cannot_be_reached_through_another_books_path(api, session):
    """The service authorizes the period's own book; the path must name that book."""
    headers, book, owner, colleague = await workspace(api, session)
    other = (await api.post("/api/v1/books", headers=headers,
                            json={"name": "دیگری", "type": "team"})).json()
    period = (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                             json={"label": "مرداد", "starts_on": "2026-08-01",
                                   "ends_on": "2026-08-31"})).json()
    adjustment = (await api.post(
        f"/api/v1/books/{book['id']}/periods/{period['id']}/adjustments",
        headers=headers,
        json={"user_id": colleague["id"], "kind": "bonus", "mode": "amount",
              "value": "1000"})).json()
    wrong = f"/api/v1/books/{other['id']}/periods/{period['id']}"

    for method, path, body in (
        ("POST", f"{wrong}/adjustments/{adjustment['id']}/approve", None),
        ("POST", f"{wrong}/adjustments", {"user_id": colleague["id"], "kind": "bonus",
                                          "mode": "amount", "value": "1"}),
        ("GET", f"{wrong}/adjustments", None),
        ("GET", f"{wrong}/payslips", None),
        ("GET", f"{wrong}/performance", None),
        ("POST", f"{wrong}/calculate", None),
        ("POST", f"{wrong}/close", None),
        ("POST", f"{wrong}/status/calculating", None),
    ):
        reply = await api.request(method, path, headers=headers, json=body)
        assert reply.status_code == 404, (path, reply.status_code, reply.text)

    listed = (await api.get(f"/api/v1/books/{book['id']}/periods/{period['id']}/adjustments",
                            headers=headers)).json()
    assert [row["is_approved"] for row in listed] == [False]
    assert len(listed) == 1


async def test_an_adjustment_cannot_be_approved_under_another_period(api, session):
    """Approved by an accountant: whoever records an adjustment may not approve it."""
    from kasbbook.modules.books.models import Role

    headers, book, owner, colleague = await workspace(api, session)
    await BookService(session).change_role(uuid.UUID(owner["id"]), uuid.UUID(book["id"]),
                                           uuid.UUID(colleague["id"]), Role.ACCOUNTANT)
    await session.commit()
    accountant = await _colleague(api)
    periods = [
        (await api.post(f"/api/v1/books/{book['id']}/periods", headers=headers,
                        json={"label": label, "starts_on": start, "ends_on": end})).json()
        for label, start, end in (("مرداد", "2026-08-01", "2026-08-31"),
                                  ("شهریور", "2026-09-01", "2026-09-30"))
    ]
    adjustment = (await api.post(
        f"/api/v1/books/{book['id']}/periods/{periods[0]['id']}/adjustments",
        headers=headers,
        json={"user_id": colleague["id"], "kind": "bonus", "mode": "amount",
              "value": "1000"})).json()

    wrong = await api.post(f"/api/v1/books/{book['id']}/periods/{periods[1]['id']}"
                           f"/adjustments/{adjustment['id']}/approve", headers=accountant)

    assert wrong.status_code == 404
    listed = (await api.get(
        f"/api/v1/books/{book['id']}/periods/{periods[0]['id']}/adjustments",
        headers=headers)).json()
    assert [row["is_approved"] for row in listed] == [False]
    right = await api.post(f"/api/v1/books/{book['id']}/periods/{periods[0]['id']}"
                           f"/adjustments/{adjustment['id']}/approve", headers=accountant)
    assert right.status_code == 200 and right.json()["is_approved"] is True


# ------------------------------------------------------------------ API keys
async def test_replacing_keys_revokes_every_open_one_and_says_how_many(session):
    from kasbbook.modules.identity.auth import AuthService

    user = await IdentityService(session).create_user("عماد")
    auth = AuthService(session, secret_key=SECRET)
    first = await auth.issue_api_key(user.id, "nightly")
    second = await auth.issue_api_key(user.id, "shop")

    issued, replaced = await auth.replace_api_keys(user.id, "bot")

    assert replaced == 2
    assert [key.id for key in await auth.list_api_keys(user.id)] == [issued.record.id]
    for old in (first, second):
        assert await auth.user_for_api_key(old.key) is None
    assert (await auth.user_for_api_key(issued.key)).id == user.id


async def test_the_api_issues_alongside_and_both_keys_work(api):
    headers = bearer(await register(api))

    keys = [(await api.post("/api/v1/auth/api-keys", headers=headers,
                            json={"name": name})).json()["key"]
            for name in ("nightly", "shop")]

    for key in keys:
        reply = await api.get("/api/v1/books", headers={"X-API-Key": key})
        assert reply.status_code == 200
    assert len((await api.get("/api/v1/auth/api-keys", headers=headers)).json()) == 2


async def test_the_bot_no_longer_revokes_keys_itself():
    """The rule is AuthService.replace_api_keys; the bot only calls it."""
    source = (SRC / "bot" / "features" / "account.py").read_text(encoding="utf-8")
    assert "revoke_api_key" not in source
    assert "replace_api_keys" in source


# -------------------------------------------------------- roles and owners
def _role_of(members, user_id):
    return next(m["role"] for m in members if m["user_id"] == user_id)


async def test_the_owner_changes_a_members_role_over_http(api, session):
    headers, book, _, colleague = await workspace(api, session)
    url = f"/api/v1/books/{book['id']}/members/{colleague['id']}"

    reply = await api.patch(url, headers=headers, json={"role": "accountant"})

    assert reply.status_code == 200, reply.text
    assert reply.json() == {"user_id": colleague["id"], "display_name": "سارا",
                            "role": "accountant"}
    members = (await api.get(f"/api/v1/books/{book['id']}/members", headers=headers)).json()
    assert _role_of(members, colleague["id"]) == "accountant"


@pytest.mark.parametrize("role", ["owner", "boss"])
async def test_a_role_that_is_not_given_this_way_is_refused(api, session, role):
    headers, book, _, colleague = await workspace(api, session)

    reply = await api.patch(f"/api/v1/books/{book['id']}/members/{colleague['id']}",
                            headers=headers, json={"role": role})

    assert reply.status_code == 422


async def test_the_owners_own_role_is_not_changed_this_way(api, session):
    headers, book, owner, _ = await workspace(api, session)

    reply = await api.patch(f"/api/v1/books/{book['id']}/members/{owner['id']}",
                            headers=headers, json={"role": "viewer"})

    assert reply.status_code == 422
    members = (await api.get(f"/api/v1/books/{book['id']}/members", headers=headers)).json()
    assert _role_of(members, owner["id"]) == "owner"


async def test_a_member_cannot_change_roles_and_a_stranger_gets_404(api, session):
    headers, book, owner, colleague = await workspace(api, session)
    member = await _colleague(api)
    stranger = bearer(await register(api, email="stranger@example.com"))

    as_member = await api.patch(f"/api/v1/books/{book['id']}/members/{colleague['id']}",
                                headers=member, json={"role": "admin"})
    as_stranger = await api.patch(f"/api/v1/books/{book['id']}/members/{colleague['id']}",
                                  headers=stranger, json={"role": "admin"})

    assert as_member.status_code == 403
    assert as_stranger.status_code == 404
    members = (await api.get(f"/api/v1/books/{book['id']}/members", headers=headers)).json()
    assert _role_of(members, colleague["id"]) == "member"


async def test_someone_who_left_cannot_be_given_a_role(api, session):
    headers, book, _, colleague = await workspace(api, session)
    url = f"/api/v1/books/{book['id']}/members/{colleague['id']}"
    assert (await api.delete(url, headers=headers)).status_code == 204

    reply = await api.patch(url, headers=headers, json={"role": "admin"})

    assert reply.status_code == 404
    assert await _colleague(api)        # still an account, just not on this book
    assert (await api.get(f"/api/v1/books/{book['id']}",
                          headers=await _colleague(api))).status_code == 404


async def test_the_owner_hands_the_book_over_and_stays_as_an_admin(api, session):
    headers, book, owner, colleague = await workspace(api, session)

    reply = await api.put(f"/api/v1/books/{book['id']}/owner", headers=headers,
                          json={"user_id": colleague["id"]})

    assert reply.status_code == 200, reply.text
    assert _role_of(reply.json(), colleague["id"]) == "owner"
    assert _role_of(reply.json(), owner["id"]) == "admin"
    # The new owner can do what only an owner can; the old one no longer can.
    new_owner = await _colleague(api)
    back = await api.put(f"/api/v1/books/{book['id']}/owner", headers=headers,
                         json={"user_id": owner["id"]})
    assert back.status_code == 403
    assert (await api.put(f"/api/v1/books/{book['id']}/owner", headers=new_owner,
                          json={"user_id": owner["id"]})).status_code == 200


@pytest.mark.parametrize("who", ["self", "stranger", "nobody"])
async def test_a_book_is_only_handed_to_another_active_member(api, session, who):
    headers, book, owner, _ = await workspace(api, session)
    stranger = (await api.get("/api/v1/auth/me", headers=bearer(
        await register(api, email="stranger@example.com")))).json()
    target = {"self": owner["id"], "stranger": stranger["id"],
              "nobody": str(uuid.uuid4())}[who]

    reply = await api.put(f"/api/v1/books/{book['id']}/owner", headers=headers,
                          json={"user_id": target})

    assert reply.status_code == 422
    members = (await api.get(f"/api/v1/books/{book['id']}/members", headers=headers)).json()
    assert _role_of(members, owner["id"]) == "owner"


async def test_a_stranger_cannot_take_a_book(api, session):
    headers, book, owner, _ = await workspace(api, session)
    stranger_headers = bearer(await register(api, email="stranger@example.com"))
    stranger = (await api.get("/api/v1/auth/me", headers=stranger_headers)).json()

    reply = await api.put(f"/api/v1/books/{book['id']}/owner", headers=stranger_headers,
                          json={"user_id": stranger["id"]})

    assert reply.status_code == 404

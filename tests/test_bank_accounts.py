"""Bank accounts: one account in several books, and balances that cannot disagree.

The properties that matter, each written as the thing a person would notice if it broke:

  * an account shared by two books has one real balance, and it equals what the two books' own
    transactions put into it, worked out two independent ways (journal and transactions);
  * every book's trial balance stays closed on its own, because a book never writes against
    another book's ledger account;
  * a member of one book never learns what another book did with the same account.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from kasbbook.modules.banks.models import BankAccountLink
from kasbbook.modules.banks.service import clean_card, clean_sheba
from kasbbook.modules.ledger.models import JournalEntry, JournalLine
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.shared.errors import ValidationError
from tests.test_api_auth import bearer, register

pytestmark = pytest.mark.asyncio

DAY = "2026-08-24"
V1 = "/api/v1"


def card(prefix: str = "603799725500876") -> str:
    """The prefix plus the Luhn digit that makes it a card number."""
    for check in range(10):
        number = f"{prefix}{check}"
        total = 0
        for index, char in enumerate(reversed(number)):
            digit = int(char)
            if index % 2 == 1:
                digit = digit * 2 - 9 if digit * 2 > 9 else digit * 2
            total += digit
        if total % 10 == 0:
            return number
    raise AssertionError


def sheba(body: str = "0170000000100324200001") -> str:
    """`IR`, two check digits that satisfy ISO 7064, and 22 more digits."""
    for check in range(100):
        digits = f"{check:02d}{body}"
        if int(digits[2:] + "1827" + digits[:2]) % 97 == 1:
            return "IR" + digits
    raise AssertionError


async def owner_with_two_books(api, db):
    tokens = await register(api)
    headers = bearer(tokens)
    personal = (await api.get(f"{V1}/books", headers=headers)).json()[0]
    business = (await api.post(f"{V1}/books", headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": personal["currency"],
    })).json()
    return headers, personal, business


async def make_bank(api, headers, books=(), **fields):
    body = {"bank_name": "ملی", "holder_name": "علی رضایی", "book_ids": [b["id"] for b in books]}
    body.update(fields)
    reply = await api.post(f"{V1}/bank-accounts", headers=headers, json=body)
    assert reply.status_code == 201, reply.text
    return reply.json()


async def record(api, headers, book, flow, amount, **extra):
    reply = await api.post(f"{V1}/books/{book['id']}/transactions", headers=headers, json={
        "flow": flow, "category": "فروش" if flow == "income" else "اجاره", "amount": str(amount),
        "occurred_on": DAY, **extra,
    })
    assert reply.status_code == 201, reply.text
    return reply.json()


async def balanced(db, book_id):
    async for session in db.session():
        debit, credit = await LedgerService(session).trial_balance(uuid.UUID(str(book_id)))
        return debit == credit


# ------------------------------------------------------------------ the fields
async def test_only_the_bank_and_the_holder_are_required(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    assert bank["title"] == "ملی علی رضایی"
    assert bank["card_number"] is None and bank["sheba"] is None and bank["account_number"] is None

    for missing in ("bank_name", "holder_name"):
        body = {"bank_name": "ملی", "holder_name": "علی رضایی"}
        body.pop(missing)
        assert (await api.post(f"{V1}/bank-accounts", headers=headers, json=body)).status_code == 422
    blank = await api.post(f"{V1}/bank-accounts", headers=headers,
                           json={"bank_name": "  ", "holder_name": "علی"})
    assert blank.status_code == 422


async def test_the_shown_name_is_the_given_one_or_the_bank_and_the_holder(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal], display_name="حساب جاری")
    assert bank["title"] == "حساب جاری"

    cleared = (await api.patch(f"{V1}/bank-accounts/{bank['id']}", headers=headers,
                               json={"display_name": None})).json()
    assert cleared["title"] == "ملی علی رضایی"

    renamed = (await api.patch(f"{V1}/bank-accounts/{bank['id']}", headers=headers,
                               json={"bank_name": "ملت"})).json()
    assert renamed["title"] == "ملت علی رضایی"
    # The book's list, and the name beside a transaction, follow the rename.
    listed = (await api.get(f"{V1}/books/{personal['id']}/bank-accounts", headers=headers)).json()
    assert listed[0]["title"] == "ملت علی رضایی"


async def test_numbers_are_checked_and_persian_digits_are_read(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    persian = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    bank = await make_bank(api, headers, [personal], card_number=card().translate(persian),
                           sheba=sheba().lower(), account_number="۱۲۳.۴۵.۶۷۸")
    assert bank["card_number"] == card()
    assert bank["sheba"] == sheba()
    assert bank["account_number"] == "123.45.678"

    for field, bad in (("card_number", "6037997255008765"), ("card_number", "1234"),
                       ("sheba", "IR000000000000000000000000"), ("account_number", "abc")):
        reply = await api.post(f"{V1}/bank-accounts", headers=headers, json={
            "bank_name": "ملی", "holder_name": "علی", field: bad})
        assert reply.status_code == 422, (field, bad)

    assert clean_card(" ") is None and clean_sheba("") is None
    with pytest.raises(ValidationError):
        clean_sheba("IR12")


# ----------------------------------------------------------- recording through one
async def test_the_first_account_is_the_default_and_a_transaction_uses_it(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    listed = (await api.get(f"{V1}/books/{personal['id']}/bank-accounts", headers=headers)).json()
    assert [row["is_default"] for row in listed] == [True]

    tx = await record(api, headers, personal, "income", 100)
    assert tx["bank_account_id"] == bank["id"]
    assert tx["bank_account_title"] == "ملی علی رضایی"
    assert await balanced(db, personal["id"])


async def test_choosing_none_records_without_an_account(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    await make_bank(api, headers, [personal])
    tx = await record(api, headers, personal, "income", 100, bank_account_id=None)
    assert tx["bank_account_id"] is None
    summary = (await api.get(f"{V1}/bank-accounts", headers=headers)).json()[0]
    assert Decimal(summary["total_balance"]) == 0
    assert await balanced(db, personal["id"])


async def test_an_account_can_be_chosen_per_transaction_and_changed_after(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی")
    second = await make_bank(api, headers, [personal], bank_name="ملت")
    tx = await record(api, headers, personal, "expense", 40, bank_account_id=second["id"])
    assert tx["bank_account_id"] == second["id"]

    moved = await api.patch(f"{V1}/books/{personal['id']}/transactions/{tx['id']}", headers=headers,
                            json={"bank_account_id": first["id"]})
    assert moved.json()["bank_account_id"] == first["id"]
    cleared = await api.patch(f"{V1}/books/{personal['id']}/transactions/{tx['id']}", headers=headers,
                              json={"bank_account_id": None})
    assert cleared.json()["bank_account_id"] is None

    by_id = {b["id"]: b["total_balance"] for b in (await api.get(f"{V1}/bank-accounts", headers=headers)).json()}
    assert {k: Decimal(v) for k, v in by_id.items()} == {first["id"]: 0, second["id"]: 0}
    assert await balanced(db, personal["id"])


# --------------------------------------------------- one account, several books
async def test_a_shared_account_has_one_balance_split_by_book(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal, business], opening_balance="500")

    await record(api, headers, personal, "income", 100)
    await record(api, headers, business, "expense", 30)
    await record(api, headers, business, "income", 250)

    summary = (await api.get(f"{V1}/bank-accounts/{bank['id']}", headers=headers)).json()
    assert Decimal(summary["total_balance"]) == 820  # 500 opening + 100 - 30 + 250
    shares = {s["book_id"]: s["balance"] for s in summary["shares"]}
    assert {k: Decimal(v) for k, v in shares.items()} == {personal["id"]: 100, business["id"]: 220}

    check = (await api.get(f"{V1}/bank-accounts/{bank['id']}/reconciliation", headers=headers)).json()
    assert check["consistent"] is True
    assert Decimal(check["from_journal"]) == Decimal(check["from_transactions"]) == 820
    # Each book's own books still close, even though they share the account.
    assert await balanced(db, personal["id"]) and await balanced(db, business["id"])


async def test_the_default_is_per_book(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal, business], bank_name="ملی")
    second = await make_bank(api, headers, [personal, business], bank_name="ملت")

    switched = await api.patch(f"{V1}/books/{business['id']}/bank-accounts/{second['id']}",
                               headers=headers, json={"is_default": True})
    assert switched.json()["is_default"] is True

    in_personal = {r["id"]: r["is_default"] for r in
                   (await api.get(f"{V1}/books/{personal['id']}/bank-accounts", headers=headers)).json()}
    in_business = {r["id"]: r["is_default"] for r in
                   (await api.get(f"{V1}/books/{business['id']}/bank-accounts", headers=headers)).json()}
    assert in_personal == {first["id"]: True, second["id"]: False}
    assert in_business == {first["id"]: False, second["id"]: True}
    assert (await record(api, headers, business, "income", 5))["bank_account_id"] == second["id"]
    assert (await record(api, headers, personal, "income", 5))["bank_account_id"] == first["id"]


async def test_the_database_allows_one_default_per_book(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    await make_bank(api, headers, [personal], bank_name="ملی")
    await make_bank(api, headers, [personal], bank_name="ملت")
    async for session in db.session():
        links = (await session.scalars(select(BankAccountLink).where(
            BankAccountLink.book_id == uuid.UUID(personal["id"])))).all()
        for link in links:
            link.is_default = True
        with pytest.raises(Exception):
            await session.flush()
        await session.rollback()


# ----------------------------------------------------------------- switching off
async def test_an_inactive_account_is_not_offered_but_stays_on_old_transactions(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    tx = await record(api, headers, personal, "income", 10)

    off = await api.patch(f"{V1}/books/{personal['id']}/bank-accounts/{bank['id']}", headers=headers,
                          json={"is_active": False})
    assert off.json()["is_active"] is False and off.json()["is_default"] is False

    refused = await api.post(f"{V1}/books/{personal['id']}/transactions", headers=headers, json={
        "flow": "income", "category": "فروش", "amount": "5", "bank_account_id": bank["id"]})
    assert refused.status_code == 422
    # With no default left, a transaction that names nothing is recorded without an account.
    assert (await record(api, headers, personal, "income", 5))["bank_account_id"] is None
    old = (await api.get(f"{V1}/books/{personal['id']}/transactions/{tx['id']}", headers=headers)).json()
    assert old["bank_account_id"] == bank["id"]

    again = await api.patch(f"{V1}/books/{personal['id']}/bank-accounts/{bank['id']}",
                            headers=headers, json={"is_default": True})
    assert again.status_code == 422


async def test_switching_the_account_off_everywhere_stops_it_in_every_book(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal, business])
    await api.patch(f"{V1}/bank-accounts/{bank['id']}", headers=headers, json={"is_active": False})
    assert (await record(api, headers, personal, "income", 5))["bank_account_id"] is None
    assert (await record(api, headers, business, "income", 5))["bank_account_id"] is None


async def test_an_account_in_use_is_switched_off_not_removed(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    await record(api, headers, personal, "income", 10)

    assert (await api.delete(f"{V1}/bank-accounts/{bank['id']}", headers=headers)).status_code == 422
    assert (await api.delete(f"{V1}/books/{personal['id']}/bank-accounts/{bank['id']}",
                             headers=headers)).status_code == 422

    unused = await make_bank(api, headers, [personal], bank_name="ملت")
    assert (await api.delete(f"{V1}/books/{personal['id']}/bank-accounts/{unused['id']}",
                             headers=headers)).status_code == 204
    assert (await api.delete(f"{V1}/bank-accounts/{unused['id']}", headers=headers)).status_code == 204


# ------------------------------------------------------------------- isolation
async def test_a_member_sees_only_their_books_share_and_no_numbers(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal, business], card_number=card(), sheba=sheba(),
                           opening_balance="1000")
    await record(api, headers, personal, "income", 700)
    await record(api, headers, business, "income", 50)

    colleague = await register(api, email="colleague@example.com")
    added = await api.post(f"{V1}/books/{business['id']}/members", headers=headers,
                           json={"identifier": "colleague@example.com", "role": "member"})
    assert added.status_code == 201, added.text

    seen = (await api.get(f"{V1}/books/{business['id']}/bank-accounts", headers=bearer(colleague))).json()
    assert len(seen) == 1
    row = seen[0]
    assert Decimal(row["balance"]) == 50  # the business share, not 1750 and not the personal 700
    assert row["card_last4"] == "•••• " + card()[-4:]
    assert row["card_number"] is None and row["sheba"] is None and row["account_number"] is None
    assert row["is_owner"] is False

    mine = (await api.get(f"{V1}/books/{business['id']}/bank-accounts", headers=headers)).json()[0]
    assert mine["card_number"] == card() and mine["is_owner"] is True

    # What they cannot reach at all: the owner's own account, its total, its reconciliation.
    assert (await api.get(f"{V1}/bank-accounts", headers=bearer(colleague))).json() == []
    for path in (f"{V1}/bank-accounts/{bank['id']}", f"{V1}/bank-accounts/{bank['id']}/reconciliation"):
        assert (await api.get(path, headers=bearer(colleague))).status_code == 404
    assert (await api.patch(f"{V1}/bank-accounts/{bank['id']}", headers=bearer(colleague),
                            json={"bank_name": "x"})).status_code == 404
    assert (await api.delete(f"{V1}/bank-accounts/{bank['id']}", headers=bearer(colleague))).status_code == 404


async def test_a_stranger_cannot_use_or_link_someone_elses_account(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])

    stranger = await register(api, email="stranger@example.com")
    theirs = (await api.get(f"{V1}/books", headers=bearer(stranger))).json()[0]
    # Not their account to link, and a transaction cannot name it either.
    assert (await api.put(f"{V1}/books/{theirs['id']}/bank-accounts/{bank['id']}", headers=bearer(stranger),
                          json={})).status_code == 404
    refused = await api.post(f"{V1}/books/{theirs['id']}/transactions", headers=bearer(stranger), json={
        "flow": "income", "category": "فروش", "amount": "5", "bank_account_id": bank["id"]})
    assert refused.status_code == 404
    # A book of the owner's that the account is not linked to refuses it the same way.
    other = await api.post(f"{V1}/books/{business['id']}/transactions", headers=headers, json={
        "flow": "income", "category": "فروش", "amount": "5", "bank_account_id": bank["id"]})
    assert other.status_code == 404


async def test_a_viewer_cannot_manage_accounts(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    viewer = await register(api, email="viewer@example.com")
    await api.post(f"{V1}/books/{personal['id']}/members", headers=headers,
                   json={"identifier": "viewer@example.com", "role": "viewer"})
    for method, body in (("patch", {"is_active": False}), ("delete", None)):
        reply = await api.request(method.upper(), f"{V1}/books/{personal['id']}/bank-accounts/{bank['id']}",
                                  headers=bearer(viewer), json=body)
        assert reply.status_code == 403


# ------------------------------------------------------------ other rules
async def test_another_currency_cannot_use_an_account(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    await api.put(f"{V1}/books/{personal['id']}/currencies/USDT", headers=headers, json={"enabled": True})
    await record(api, headers, personal, "income", 10, currency="USDT", conversion_rate="100000",
                 bank_account_id=None)

    named = await api.post(f"{V1}/books/{personal['id']}/transactions", headers=headers, json={
        "flow": "income", "category": "فروش", "amount": "5", "currency": "USDT",
        "conversion_rate": "100000", "bank_account_id": bank["id"]})
    assert named.status_code == 422
    # Naming nothing is not an error: the default simply does not apply to another currency.
    assert (await record(api, headers, personal, "income", 5, currency="USDT",
                         conversion_rate="100000"))["bank_account_id"] is None


async def test_a_book_in_another_base_currency_cannot_link_it(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    dollars = (await api.post(f"{V1}/books", headers=headers, json={
        "name": "دلاری", "type": "business", "currency": "USD"})).json()
    reply = await api.put(f"{V1}/books/{dollars['id']}/bank-accounts/{bank['id']}", headers=headers, json={})
    assert reply.status_code == 422


async def test_moving_a_transaction_keeps_the_account_only_where_it_is_linked(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    shared = await make_bank(api, headers, [personal, business], bank_name="ملی")
    only_here = await make_bank(api, headers, [personal], bank_name="ملت")

    kept = await record(api, headers, personal, "income", 10, bank_account_id=shared["id"])
    dropped = await record(api, headers, personal, "income", 20, bank_account_id=only_here["id"])
    for tx in (kept, dropped):
        moved = await api.patch(f"{V1}/books/{personal['id']}/transactions/{tx['id']}", headers=headers,
                                json={"book_id": business["id"]})
        assert moved.status_code == 200, moved.text

    listing = (await api.get(f"{V1}/books/{business['id']}/transactions", headers=headers)).json()["items"]
    by_amount = {row["original_amount"]: row["bank_account_id"] for row in listing}
    assert {Decimal(k): v for k, v in by_amount.items()} == {10: shared["id"], 20: None}
    for bank in (await api.get(f"{V1}/bank-accounts", headers=headers)).json():
        check = (await api.get(f"{V1}/bank-accounts/{bank['id']}/reconciliation", headers=headers)).json()
        assert check["consistent"] is True
    assert await balanced(db, personal["id"]) and await balanced(db, business["id"])


async def test_transactions_can_be_filtered_by_account(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal, business], bank_name="ملی")
    second = await make_bank(api, headers, [personal, business], bank_name="ملت")
    await record(api, headers, personal, "income", 10, bank_account_id=first["id"])
    await record(api, headers, personal, "income", 20, bank_account_id=second["id"])
    await record(api, headers, business, "income", 30, bank_account_id=second["id"])

    one = (await api.get(f"{V1}/books/{personal['id']}/transactions", headers=headers,
                         params={"bank_account_id": second["id"]})).json()
    assert [Decimal(r["original_amount"]) for r in one["items"]] == [20]
    everywhere = (await api.get(f"{V1}/transactions", headers=headers,
                                params={"bank_account_id": second["id"]})).json()
    assert sorted(Decimal(r["original_amount"]) for r in everywhere["items"]) == [20, 30]
    assert all(r["bank_account_title"] == "ملت علی رضایی" for r in everywhere["items"])


async def test_reconciliation_notices_a_balance_that_was_tampered_with(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    await record(api, headers, personal, "income", 100)
    ok = (await api.get(f"{V1}/bank-accounts/{bank['id']}/reconciliation", headers=headers)).json()
    assert ok["consistent"] is True

    # Something writes against the account's ledger without a transaction behind it.
    async for session in db.session():
        link = await session.scalar(select(BankAccountLink))
        entry = JournalEntry(book_id=link.book_id, occurred_on=datetime.date(2026, 8, 24),
                             memo="stray")
        entry.lines.append(JournalLine(account_id=link.ledger_account_id, debit=Decimal("7"), credit=Decimal("0")))
        session.add(entry)
        await session.commit()
    broken = (await api.get(f"{V1}/bank-accounts/{bank['id']}/reconciliation", headers=headers)).json()
    assert broken["consistent"] is False
    assert Decimal(broken["from_journal"]) == 107 and Decimal(broken["from_transactions"]) == 100


async def test_deleting_a_transaction_returns_its_money_to_the_account(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal, business], opening_balance="10")
    tx = await record(api, headers, personal, "income", 90)
    async def total():
        reply = await api.get(f"{V1}/bank-accounts/{bank['id']}", headers=headers)
        return Decimal(reply.json()["total_balance"])

    assert await total() == 100
    await api.delete(f"{V1}/books/{personal['id']}/transactions/{tx['id']}", headers=headers)
    assert await total() == 10


# ------------------------------------------------------------------ transfers
async def transfer(api, headers, book, source, target, amount, **extra):
    return await api.post(f"{V1}/books/{book['id']}/bank-transfers", headers=headers, json={
        "from_bank_account_id": source["id"], "to_bank_account_id": target["id"],
        "amount": str(amount), "occurred_on": DAY, **extra,
    })


async def totals(api, headers):
    return {b["id"]: Decimal(b["total_balance"]) for b in (await api.get(f"{V1}/bank-accounts", headers=headers)).json()}


async def test_a_transfer_moves_money_between_accounts_without_touching_income_or_expense(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی", opening_balance="1000")
    second = await make_bank(api, headers, [personal], bank_name="ملت")
    await record(api, headers, personal, "income", 400, bank_account_id=first["id"])

    reply = await transfer(api, headers, personal, first, second, 300, note="جابه‌جایی")
    assert reply.status_code == 201, reply.text
    assert reply.json()["from_title"] == "ملی علی رضایی" and reply.json()["to_title"] == "ملت علی رضایی"

    assert await totals(api, headers) == {first["id"]: 1100, second["id"]: 300}
    # Neither income nor expense moved, so no report or share could notice.
    listing = (await api.get(f"{V1}/books/{personal['id']}/transactions", headers=headers)).json()
    assert Decimal(listing["total_income"]) == 400 and Decimal(listing["total_expense"]) == 0
    for bank in (first, second):
        check = (await api.get(f"{V1}/bank-accounts/{bank['id']}/reconciliation", headers=headers)).json()
        assert check["consistent"] is True
    assert await balanced(db, personal["id"])


async def test_a_transfer_can_be_edited_and_removed(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی")
    second = await make_bank(api, headers, [personal], bank_name="ملت")
    made = (await transfer(api, headers, personal, first, second, 100)).json()

    edited = await api.patch(f"{V1}/books/{personal['id']}/bank-transfers/{made['id']}", headers=headers,
                             json={"amount": "250", "note": "اصلاح"})
    assert edited.status_code == 200, edited.text
    assert Decimal(edited.json()["amount"]) == 250 and edited.json()["note"] == "اصلاح"
    assert await totals(api, headers) == {first["id"]: -250, second["id"]: 250}

    reversed_ = await api.patch(f"{V1}/books/{personal['id']}/bank-transfers/{made['id']}", headers=headers,
                                json={"from_bank_account_id": second["id"], "to_bank_account_id": first["id"]})
    assert reversed_.status_code == 200
    assert await totals(api, headers) == {first["id"]: 250, second["id"]: -250}
    assert await balanced(db, personal["id"])

    assert (await api.delete(f"{V1}/books/{personal['id']}/bank-transfers/{made['id']}", headers=headers)).status_code == 204
    assert await totals(api, headers) == {first["id"]: 0, second["id"]: 0}
    assert (await api.get(f"{V1}/books/{personal['id']}/bank-transfers", headers=headers)).json() == []
    assert await balanced(db, personal["id"])


async def test_a_transfer_between_the_same_account_or_a_foreign_one_is_refused(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی")
    elsewhere = await make_bank(api, headers, [business], bank_name="ملت")
    assert (await transfer(api, headers, personal, first, first, 10)).status_code == 422
    # An account that is not linked to this book is not found, whoever owns it.
    assert (await transfer(api, headers, personal, first, elsewhere, 10)).status_code == 404
    assert (await transfer(api, headers, personal, first, first, 0)).status_code == 422


async def test_an_account_with_a_transfer_is_switched_off_not_removed(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی")
    second = await make_bank(api, headers, [personal], bank_name="ملت")
    await transfer(api, headers, personal, first, second, 10)
    assert (await api.delete(f"{V1}/bank-accounts/{second['id']}", headers=headers)).status_code == 422
    assert (await api.delete(f"{V1}/books/{personal['id']}/bank-accounts/{second['id']}",
                             headers=headers)).status_code == 422


async def test_only_account_managers_move_money_and_a_member_can_read_them(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی")
    second = await make_bank(api, headers, [personal], bank_name="ملت")
    member = bearer(await register(api, email="member@example.com"))
    await api.post(f"{V1}/books/{personal['id']}/members", headers=headers,
                   json={"identifier": "member@example.com", "role": "member"})
    assert (await transfer(api, member, personal, first, second, 5)).status_code == 403
    await transfer(api, headers, personal, first, second, 5)
    assert (await api.get(f"{V1}/books/{personal['id']}/bank-transfers", headers=member)).status_code == 200


async def test_a_stranger_cannot_reach_a_books_transfers(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی")
    second = await make_bank(api, headers, [personal], bank_name="ملت")
    made = (await transfer(api, headers, personal, first, second, 5)).json()
    stranger = bearer(await register(api, email="stranger2@example.com"))
    assert (await api.get(f"{V1}/books/{personal['id']}/bank-transfers", headers=stranger)).status_code == 404
    assert (await transfer(api, stranger, personal, first, second, 5)).status_code == 404
    assert (await api.delete(f"{V1}/books/{personal['id']}/bank-transfers/{made['id']}",
                             headers=stranger)).status_code == 404


# --------------------------------------------------------------------- assign
async def test_old_transactions_can_be_put_on_an_account_and_the_books_stay_balanced(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    # Recorded before the book had any account: they sit on «نقد و بانک».
    await record(api, headers, personal, "income", 300)
    await record(api, headers, personal, "expense", 80)
    bank = await make_bank(api, headers, [personal])
    await record(api, headers, personal, "income", 1000, bank_account_id=None)

    done = await api.post(f"{V1}/books/{personal['id']}/bank-accounts/{bank['id']}/assign",
                          headers=headers, json={})
    assert done.status_code == 200, done.text
    assert done.json() == {"moved": 3, "left": 0}
    assert (await totals(api, headers))[bank["id"]] == 1220
    check = (await api.get(f"{V1}/bank-accounts/{bank['id']}/reconciliation", headers=headers)).json()
    assert check["consistent"] is True
    assert await balanced(db, personal["id"])
    # Nothing is left to assign the second time.
    again = await api.post(f"{V1}/books/{personal['id']}/bank-accounts/{bank['id']}/assign",
                           headers=headers, json={})
    assert again.json() == {"moved": 0, "left": 0}


async def test_assigning_can_be_limited_to_a_range_and_skips_other_currencies(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    await api.put(f"{V1}/books/{personal['id']}/currencies/USDT", headers=headers, json={"enabled": True})
    await record(api, headers, personal, "income", 10, currency="USDT", conversion_rate="100000")
    await record(api, headers, personal, "income", 50, occurred_on="2026-01-02")
    await record(api, headers, personal, "income", 70, occurred_on="2026-06-02")
    bank = await make_bank(api, headers, [personal])
    # Made after the transactions, so the default does not apply to them.
    done = await api.post(f"{V1}/books/{personal['id']}/bank-accounts/{bank['id']}/assign",
                          headers=headers, json={"since": "2026-05-01"})
    assert done.json() == {"moved": 1, "left": 0}
    assert (await totals(api, headers))[bank["id"]] == 70
    assert await balanced(db, personal["id"])

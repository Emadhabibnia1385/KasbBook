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


# ------------------------------------------- the other things that move money
async def everything_agrees(api, db, headers, books):
    for bank in (await api.get(f"{V1}/bank-accounts", headers=headers)).json():
        check = (await api.get(f"{V1}/bank-accounts/{bank['id']}/reconciliation", headers=headers)).json()
        assert check["consistent"] is True, check
    for book in books:
        assert await balanced(db, book["id"])


async def test_a_recurring_rule_keeps_the_account_it_was_made_with(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی")
    second = await make_bank(api, headers, [personal], bank_name="ملت")
    made = await api.post(f"{V1}/books/{personal['id']}/recurring", headers=headers, json={
        "flow": "expense", "category": "اجاره", "amount": "100", "period": "monthly",
        "starts_on": DAY, "mode": "ask", "bank_account_id": second["id"]})
    assert made.status_code == 201, made.text
    assert made.json()["bank_account_id"] == second["id"]

    # Changing the book's default later does not move a rule that was made earlier.
    await api.patch(f"{V1}/books/{personal['id']}/bank-accounts/{second['id']}", headers=headers,
                    json={"is_default": True})
    pending = (await api.get(f"{V1}/books/{personal['id']}/recurring/pending", headers=headers)).json()
    assert pending == []  # nothing due yet: the job has not run

    left_out = await api.post(f"{V1}/books/{personal['id']}/recurring", headers=headers, json={
        "flow": "expense", "category": "برق", "amount": "50", "period": "monthly",
        "starts_on": DAY, "mode": "ask"})
    assert left_out.json()["bank_account_id"] == second["id"]  # the default at that moment
    none = await api.post(f"{V1}/books/{personal['id']}/recurring", headers=headers, json={
        "flow": "expense", "category": "آب", "amount": "20", "period": "monthly",
        "starts_on": DAY, "mode": "ask", "bank_account_id": None})
    assert none.json()["bank_account_id"] is None

    changed = await api.patch(f"{V1}/books/{personal['id']}/recurring/{made.json()['id']}",
                              headers=headers, json={"bank_account_id": first["id"]})
    assert changed.json()["bank_account_id"] == first["id"]
    # An account used by a rule is switched off, not unlinked.
    assert (await api.delete(f"{V1}/books/{personal['id']}/bank-accounts/{first['id']}",
                             headers=headers)).status_code == 422


async def test_a_confirmed_recurring_date_goes_through_the_rules_account(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    rule = (await api.post(f"{V1}/books/{personal['id']}/recurring", headers=headers, json={
        "flow": "expense", "category": "اجاره", "amount": "100", "period": "monthly",
        "starts_on": "2020-01-01", "mode": "ask"})).json()
    async for session in db.session():
        from kasbbook.modules.recurring.service import RecurringService
        await RecurringService(session).run_due()
        await session.commit()
    pending = (await api.get(f"{V1}/books/{personal['id']}/recurring/pending", headers=headers)).json()
    assert pending and rule["bank_account_id"] == bank["id"]
    await api.post(f"{V1}/books/{personal['id']}/recurring/occurrences/{pending[0]['id']}/confirm",
                   headers=headers, json={})
    listing = (await api.get(f"{V1}/books/{personal['id']}/transactions", headers=headers)).json()["items"]
    assert listing and all(row["bank_account_id"] == bank["id"] for row in listing)
    await everything_agrees(api, db, headers, [personal])


async def test_a_loan_installment_is_paid_from_the_chosen_account(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی")
    second = await make_bank(api, headers, [personal], bank_name="ملت")
    loan = (await api.post(f"{V1}/books/{personal['id']}/loans", headers=headers, json={
        "title": "وام", "installment_amount": "100", "installment_count": 4, "starts_on": DAY})).json()

    await api.post(f"{V1}/books/{personal['id']}/loans/{loan['id']}/pay", headers=headers,
                   params={"bank_account_id": second["id"]})
    await api.post(f"{V1}/books/{personal['id']}/loans/{loan['id']}/pay", headers=headers)
    await api.post(f"{V1}/books/{personal['id']}/loans/{loan['id']}/pay", headers=headers,
                   params={"bank_account_id": "none"})
    by_id = await totals(api, headers)
    assert by_id[second["id"]] == -100 and by_id[first["id"]] == -100  # the default is the first account
    bad = await api.post(f"{V1}/books/{personal['id']}/loans/{loan['id']}/pay", headers=headers,
                         params={"bank_account_id": "not-an-id"})
    assert bad.status_code == 422
    await everything_agrees(api, db, headers, [personal])


async def test_assets_and_funds_move_cash_through_an_account_and_still_agree(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal], opening_balance="10000")
    other = await make_bank(api, headers, [personal], bank_name="ملت")

    asset = (await api.post(f"{V1}/books/{personal['id']}/capital/assets", headers=headers, json={
        "name": "طلا", "kind": "gold", "cost": "3000", "acquired_on": DAY})).json()
    assert (await totals(api, headers))[bank["id"]] == 7000

    sold = await api.post(f"{V1}/books/{personal['id']}/capital/assets/{asset['id']}/sell", headers=headers,
                          json={"price": "3500", "sold_on": DAY, "bank_account_id": other["id"]})
    assert sold.status_code == 200, sold.text
    # The cost and the gain both arrive in the account chosen for the sale.
    assert (await totals(api, headers))[other["id"]] == 3500

    fund = (await api.post(f"{V1}/books/{personal['id']}/capital/funds", headers=headers, json={
        "name": "صندوق", "monthly_amount": "200", "months": 3, "payout_amount": "600",
        "starts_on": DAY})).json()
    await api.post(f"{V1}/books/{personal['id']}/capital/funds/{fund['id']}/contribute", headers=headers,
                   json={"on": DAY})
    await api.post(f"{V1}/books/{personal['id']}/capital/funds/{fund['id']}/receive", headers=headers,
                   json={"on": DAY, "bank_account_id": other["id"]})
    after = await totals(api, headers)
    assert after[bank["id"]] == 6800 and after[other["id"]] == 4100
    await everything_agrees(api, db, headers, [personal])
    # Used by a movement: switched off, never removed.
    assert (await api.delete(f"{V1}/bank-accounts/{other['id']}", headers=headers)).status_code == 422


async def test_a_purchase_paid_wholly_on_a_loan_touches_no_account(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal], opening_balance="500")
    bought = await api.post(f"{V1}/books/{personal['id']}/capital/assets", headers=headers, json={
        "name": "ماشین", "kind": "other", "cost": "1000", "acquired_on": DAY,
        "installment_amount": "100", "installment_count": 10, "down_payment": "0"})
    assert bought.status_code == 201, bought.text
    assert (await totals(api, headers))[bank["id"]] == 500
    await everything_agrees(api, db, headers, [personal])


# ----------------------------------------------------- transfers between books
async def book_transfer(api, headers, source, target, from_bank, to_bank, amount, **extra):
    return await api.post(f"{V1}/book-transfers", headers=headers, json={
        "from_book_id": source["id"], "to_book_id": target["id"],
        "from_bank_account_id": from_bank["id"], "to_bank_account_id": to_bank["id"],
        "amount": str(amount), "occurred_on": DAY, **extra,
    })


async def test_money_moves_between_two_books_and_each_stays_balanced(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    mine = await make_bank(api, headers, [personal], bank_name="شخصی", opening_balance="100")
    shop = await make_bank(api, headers, [business], bank_name="کسب‌وکار")
    await record(api, headers, business, "income", 1000)

    reply = await book_transfer(api, headers, business, personal, shop, mine, 400, note="برداشت")
    assert reply.status_code == 201, reply.text
    assert reply.json()["direction"] == "out" and reply.json()["other_book_name"] == personal["name"]

    assert await totals(api, headers) == {mine["id"]: 500, shop["id"]: 600}
    # Not income and not an expense in either book.
    for book, income in ((business, 1000), (personal, 0)):
        listing = (await api.get(f"{V1}/books/{book['id']}/transactions", headers=headers)).json()
        assert Decimal(listing["total_income"]) == income and Decimal(listing["total_expense"]) == 0
    await everything_agrees(api, db, headers, [personal, business])

    mine_side = (await api.get(f"{V1}/books/{personal['id']}/book-transfers", headers=headers)).json()
    assert [(row["direction"], Decimal(row["amount"])) for row in mine_side] == [("in", 400)]
    assert (await api.get(f"{V1}/books/{business['id']}/book-transfers", headers=headers)).json()[0]["direction"] == "out"


async def test_one_shared_account_only_changes_who_it_belongs_to(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    shared = await make_bank(api, headers, [personal, business], opening_balance="50")
    await record(api, headers, business, "income", 300)

    reply = await book_transfer(api, headers, business, personal, shared, shared, 120)
    assert reply.status_code == 201, reply.text
    summary = (await api.get(f"{V1}/bank-accounts/{shared['id']}", headers=headers)).json()
    # The account itself holds the same; 120 of it now counts for the personal book.
    assert Decimal(summary["total_balance"]) == 350
    shares = {s["book_id"]: Decimal(s["balance"]) for s in summary["shares"]}
    assert shares == {business["id"]: 180, personal["id"]: 120}
    await everything_agrees(api, db, headers, [personal, business])


async def test_a_transfer_between_books_is_taken_back_from_both(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    mine = await make_bank(api, headers, [personal], bank_name="شخصی")
    shop = await make_bank(api, headers, [business], bank_name="کسب‌وکار")
    made = (await book_transfer(api, headers, business, personal, shop, mine, 70)).json()

    gone = await api.delete(f"{V1}/books/{personal['id']}/book-transfers/{made['pair_id']}", headers=headers)
    assert gone.status_code == 204
    assert await totals(api, headers) == {mine["id"]: 0, shop["id"]: 0}
    for book in (personal, business):
        assert (await api.get(f"{V1}/books/{book['id']}/book-transfers", headers=headers)).json() == []
    await everything_agrees(api, db, headers, [personal, business])


async def test_between_books_the_rules_hold(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    mine = await make_bank(api, headers, [personal], bank_name="شخصی")
    shop = await make_bank(api, headers, [business], bank_name="کسب‌وکار")
    dollars = (await api.post(f"{V1}/books", headers=headers, json={
        "name": "دلاری", "type": "business", "currency": "USD"})).json()
    cash = await make_bank(api, headers, [dollars], bank_name="دلار", currency="USD")

    assert (await book_transfer(api, headers, business, business, shop, shop, 5)).status_code == 422
    assert (await book_transfer(api, headers, business, dollars, shop, cash, 5)).status_code == 422
    assert (await book_transfer(api, headers, business, personal, shop, mine, 0)).status_code == 422
    # An account that is not linked to the book it is named for is not found.
    assert (await book_transfer(api, headers, business, personal, mine, shop, 5)).status_code == 404
    # In use by a transfer: switched off, never removed.
    await book_transfer(api, headers, business, personal, shop, mine, 5)
    assert (await api.delete(f"{V1}/bank-accounts/{shop['id']}", headers=headers)).status_code == 422
    assert (await api.delete(f"{V1}/books/{business['id']}/bank-accounts/{shop['id']}",
                             headers=headers)).status_code == 422


async def test_a_stranger_or_a_viewer_cannot_move_money_between_books(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    mine = await make_bank(api, headers, [personal], bank_name="شخصی")
    shop = await make_bank(api, headers, [business], bank_name="کسب‌وکار")
    stranger = bearer(await register(api, email="stranger3@example.com"))
    assert (await book_transfer(api, stranger, business, personal, shop, mine, 5)).status_code == 404

    member = bearer(await register(api, email="member3@example.com"))
    await api.post(f"{V1}/books/{business['id']}/members", headers=headers,
                   json={"identifier": "member3@example.com", "role": "member"})
    assert (await book_transfer(api, member, business, personal, shop, mine, 5)).status_code in (403, 404)


async def test_the_other_books_name_is_not_told_to_someone_outside_it(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    mine = await make_bank(api, headers, [personal], bank_name="شخصی")
    shop = await make_bank(api, headers, [business], bank_name="کسب‌وکار")
    await book_transfer(api, headers, business, personal, shop, mine, 5)

    colleague = bearer(await register(api, email="colleague3@example.com"))
    await api.post(f"{V1}/books/{business['id']}/members", headers=headers,
                   json={"identifier": "colleague3@example.com", "role": "viewer"})
    seen = (await api.get(f"{V1}/books/{business['id']}/book-transfers", headers=colleague)).json()
    assert len(seen) == 1 and seen[0]["other_book_name"] is None
    # And they cannot take it back: that needs account management in both books.
    gone = await api.delete(f"{V1}/books/{business['id']}/book-transfers/{seen[0]['pair_id']}", headers=colleague)
    assert gone.status_code == 403


async def test_deleting_one_book_leaves_the_other_consistent(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    mine = await make_bank(api, headers, [personal], bank_name="شخصی")
    shop = await make_bank(api, headers, [business], bank_name="کسب‌وکار")
    await book_transfer(api, headers, business, personal, shop, mine, 90)
    me = (await api.get(f"{V1}/auth/me", headers=headers)).json()
    from kasbbook.modules.books.service import BookService
    async for session in db.session():
        await BookService(session).delete_book(uuid.UUID(me["id"]), uuid.UUID(business["id"]))
        await session.commit()
    check = (await api.get(f"{V1}/bank-accounts/{mine['id']}/reconciliation", headers=headers)).json()
    assert check["consistent"] is True and Decimal(check["from_journal"]) == 90
    assert await balanced(db, personal["id"])


# ----------------------------------------- pay to members, and exchanging currency
async def team_with_pay(api, db):
    """A team book of one with a bank account, a 100% share, an income and a calculated period."""
    tokens = await register(api, email="payer@example.com")
    headers = bearer(tokens)
    me = (await api.get(f"{V1}/auth/me", headers=headers)).json()
    book = (await api.post(f"{V1}/books", headers=headers, json={"name": "تیم", "type": "team"})).json()
    bank = await make_bank(api, headers, [book], opening_balance="5000")
    await api.put(f"{V1}/books/{book['id']}/shares", headers=headers, json={
        "user_id": me["id"], "basis": "percent", "value": "100", "effective_from": "2026-01-01"})
    await record(api, headers, book, "income", 1000, bank_account_id=bank["id"])
    period = (await api.post(f"{V1}/books/{book['id']}/periods", headers=headers, json={
        "label": "مرداد", "starts_on": "2026-08-01", "ends_on": "2026-08-31"})).json()
    slip = (await api.post(f"{V1}/books/{book['id']}/periods/{period['id']}/calculate",
                           headers=headers)).json()[0]
    return headers, book, bank, slip


async def test_paying_a_member_takes_the_money_off_the_account_and_voiding_puts_it_back(api, db):
    headers, book, bank, slip = await team_with_pay(api, db)
    assert (await totals(api, headers))[bank["id"]] == 6000  # 5000 opening + 1000 income

    paid = await api.post(f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments", headers=headers,
                          json={"amount": "300", "paid_on": DAY})
    assert paid.status_code == 201, paid.text
    payment = paid.json()["payments"][0]
    assert payment["bank_account_id"] == bank["id"]  # the book's default, left out of the request
    assert (await totals(api, headers))[bank["id"]] == 5700
    await everything_agrees(api, db, headers, [book])

    # Not an expense of the book: its report of income and expense did not move.
    page = (await api.get(f"{V1}/books/{book['id']}/transactions", headers=headers)).json()
    assert Decimal(page["total_expense"]) == 0

    voided = await api.delete(
        f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments/{payment['id']}", headers=headers)
    assert voided.status_code == 200, voided.text
    assert (await totals(api, headers))[bank["id"]] == 6000
    await everything_agrees(api, db, headers, [book])


async def test_a_payment_can_name_no_account_and_another_currency_cannot_name_one(api, db):
    headers, book, bank, slip = await team_with_pay(api, db)
    none = await api.post(f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments", headers=headers,
                          json={"amount": "100", "paid_on": DAY, "bank_account_id": None})
    assert none.status_code == 201, none.text
    assert none.json()["payments"][0]["bank_account_id"] is None
    assert (await totals(api, headers))[bank["id"]] == 6000

    await api.put(f"{V1}/books/{book['id']}/currencies/USDT", headers=headers, json={"enabled": True})
    await record(api, headers, book, "income", 50, currency="USDT", conversion_rate="100",
                 bank_account_id=None)
    refused = await api.post(f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments", headers=headers,
                             json={"amount": "1", "currency": "USDT", "conversion_rate": "100",
                                   "paid_on": DAY, "bank_account_id": bank["id"]})
    assert refused.status_code == 422
    # Naming nothing is fine: the default does not apply to another currency.
    ok = await api.post(f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments", headers=headers,
                        json={"amount": "1", "currency": "USDT", "conversion_rate": "100", "paid_on": DAY})
    assert ok.status_code == 201, ok.text
    await everything_agrees(api, db, headers, [book])


async def test_a_member_paid_through_an_account_blocks_removing_it(api, db):
    headers, book, bank, slip = await team_with_pay(api, db)
    await api.post(f"{V1}/books/{book['id']}/payslips/{slip['id']}/payments", headers=headers,
                   json={"amount": "10", "paid_on": DAY})
    assert (await api.delete(f"{V1}/bank-accounts/{bank['id']}", headers=headers)).status_code == 422
    assert (await api.delete(f"{V1}/books/{book['id']}/bank-accounts/{bank['id']}",
                             headers=headers)).status_code == 422


async def exchange(api, headers, book, **fields):
    body = {"from_currency": "IRT", "from_amount": "1000", "to_currency": "USDT", "to_amount": "10",
            "occurred_on": DAY, **fields}
    return await api.post(f"{V1}/books/{book['id']}/conversions", headers=headers, json=body)


async def test_exchanging_the_books_currency_moves_an_account_both_ways(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    # The book's own currency is held as what came in minus what went out, so there is something to exchange.
    await record(api, headers, personal, "income", 5000)
    await api.put(f"{V1}/books/{personal['id']}/currencies/USDT", headers=headers, json={"enabled": True})

    bought = await exchange(api, headers, personal)
    assert bought.status_code == 201, bought.text
    assert bought.json()["bank_account_id"] == bank["id"]
    assert (await totals(api, headers))[bank["id"]] == 4000  # 1000 toman left for 10 USDT

    sold = await exchange(api, headers, personal, from_currency="USDT", from_amount="4",
                          to_currency="IRT", to_amount="500")
    assert sold.status_code == 201, sold.text
    assert (await totals(api, headers))[bank["id"]] == 4500  # 500 toman arrived
    await everything_agrees(api, db, headers, [personal])

    # Correcting it rebuilds the entry; taking it back returns the account.
    fixed = await api.patch(f"{V1}/books/{personal['id']}/conversions/{sold.json()['id']}", headers=headers,
                            json={"to_amount": "600"})
    assert fixed.status_code == 200, fixed.text
    assert (await totals(api, headers))[bank["id"]] == 4600
    assert (await api.delete(f"{V1}/books/{personal['id']}/conversions/{sold.json()['id']}",
                             headers=headers)).status_code == 204
    assert (await totals(api, headers))[bank["id"]] == 4000
    await everything_agrees(api, db, headers, [personal])
    # Not income and not an expense: only the 5000 recorded above is income.
    page = (await api.get(f"{V1}/books/{personal['id']}/transactions", headers=headers)).json()
    assert Decimal(page["total_income"]) == 5000 and Decimal(page["total_expense"]) == 0


async def test_an_exchange_between_two_other_currencies_has_no_account(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    for code in ("USDT", "TON"):
        await api.put(f"{V1}/books/{personal['id']}/currencies/{code}", headers=headers, json={"enabled": True})
    await record(api, headers, personal, "income", 20, currency="USDT", conversion_rate="100",
                 bank_account_id=None)
    swap = await exchange(api, headers, personal, from_currency="USDT", from_amount="5",
                          to_currency="TON", to_amount="3", base_value="500")
    assert swap.status_code == 201, swap.text
    assert swap.json()["bank_account_id"] is None
    refused = await exchange(api, headers, personal, from_currency="USDT", from_amount="1",
                             to_currency="TON", to_amount="1", base_value="100", bank_account_id=bank["id"])
    assert refused.status_code == 422
    await everything_agrees(api, db, headers, [personal])


async def test_a_conversion_can_choose_the_account_or_none(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    first = await make_bank(api, headers, [personal], bank_name="ملی", opening_balance="1000")
    second = await make_bank(api, headers, [personal], bank_name="ملت", opening_balance="1000")
    await api.put(f"{V1}/books/{personal['id']}/currencies/USDT", headers=headers, json={"enabled": True})
    await exchange(api, headers, personal, bank_account_id=second["id"])
    await exchange(api, headers, personal, bank_account_id=None)
    after = await totals(api, headers)
    assert after[first["id"]] == 1000 and after[second["id"]] == 0
    await everything_agrees(api, db, headers, [personal])


# --------------------------------------------------- lending, borrowing, being paid back
async def debt(api, headers, book, **fields):
    body = {"person": "علی", "amount": "1000", "direction": "owed_to_me", "occurred_on": DAY, **fields}
    reply = await api.post(f"{V1}/books/{book['id']}/debts", headers=headers, json=body)
    assert reply.status_code == 201, reply.text
    return reply.json()


async def test_lending_and_being_paid_back_move_an_account_and_never_an_expense(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal], opening_balance="5000")

    lent = await debt(api, headers, personal, bank_account_id=bank["id"])
    assert (await totals(api, headers))[bank["id"]] == 4000  # 1000 left the account
    base = f"{V1}/books/{personal['id']}/debts/{lent['id']}"

    more = await api.post(f"{base}/increase", headers=headers, json={
        "amount": "300", "occurred_on": DAY, "bank_account_id": bank["id"], "note": "دوباره دادم"})
    assert more.status_code == 200, more.text
    assert Decimal(more.json()["amount"]) == 1300
    assert (await totals(api, headers))[bank["id"]] == 3700

    back = await api.post(f"{base}/settle", headers=headers, json={
        "amount": "400", "occurred_on": DAY, "bank_account_id": bank["id"]})
    assert back.status_code == 200, back.text
    assert Decimal(back.json()["remaining"]) == 900
    assert (await totals(api, headers))[bank["id"]] == 4100  # 400 arrived

    history = (await api.get(f"{base}/movements", headers=headers)).json()
    assert sorted((m["kind"], Decimal(m["amount"])) for m in history) == [
        ("increase", 300), ("increase", 1000), ("payment", 400)]
    assert all(m["bank_account_id"] == bank["id"] for m in history)
    page = (await api.get(f"{V1}/books/{personal['id']}/transactions", headers=headers)).json()
    assert Decimal(page["total_income"]) == 0 and Decimal(page["total_expense"]) == 0
    await everything_agrees(api, db, headers, [personal])


async def test_borrowing_and_paying_back_move_the_other_way(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    owed = await debt(api, headers, personal, direction="i_owe", amount="500", bank_account_id=bank["id"])
    assert (await totals(api, headers))[bank["id"]] == 500  # borrowed money arrived
    await api.post(f"{V1}/books/{personal['id']}/debts/{owed['id']}/settle", headers=headers,
                   json={"amount": "200", "bank_account_id": bank["id"], "occurred_on": DAY})
    assert (await totals(api, headers))[bank["id"]] == 300
    await everything_agrees(api, db, headers, [personal])


async def test_a_debt_with_no_account_moves_no_cash(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal], opening_balance="100")
    owed = await debt(api, headers, personal)  # a credit sale: left out means none moved
    await api.post(f"{V1}/books/{personal['id']}/debts/{owed['id']}/settle", headers=headers,
                   json={"amount": "250"})
    assert (await totals(api, headers))[bank["id"]] == 100
    await everything_agrees(api, db, headers, [personal])


async def test_settling_as_income_uses_the_books_account_and_adds_no_second_entry(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    owed = await debt(api, headers, personal, amount="800")
    done = await api.post(f"{V1}/books/{personal['id']}/debts/{owed['id']}/settle", headers=headers,
                          json={"record_transaction": True, "amount": "800", "occurred_on": DAY})
    assert done.status_code == 200, done.text
    page = (await api.get(f"{V1}/books/{personal['id']}/transactions", headers=headers)).json()
    assert Decimal(page["total_income"]) == 800
    assert (await totals(api, headers))[bank["id"]] == 800  # once, through the transaction
    await everything_agrees(api, db, headers, [personal])


async def test_a_movement_can_be_taken_back_and_a_debt_with_cash_asks_before_it_goes(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal], opening_balance="1000")
    lent = await debt(api, headers, personal, amount="400", bank_account_id=bank["id"])
    base = f"{V1}/books/{personal['id']}/debts/{lent['id']}"
    await api.post(f"{base}/settle", headers=headers, json={
        "amount": "100", "bank_account_id": bank["id"], "occurred_on": DAY})
    paid_row = next(m for m in (await api.get(f"{base}/movements", headers=headers)).json()
                    if m["kind"] == "payment")

    gone = await api.delete(f"{base}/movements/{paid_row['id']}", headers=headers)
    assert gone.status_code == 200, gone.text
    assert Decimal(gone.json()["remaining"]) == 400
    assert (await totals(api, headers))[bank["id"]] == 600  # only the lending is left

    assert (await api.delete(base, headers=headers)).status_code == 422
    assert (await api.delete(base, headers=headers, params={"undo_cash": "true"})).status_code == 204
    assert (await totals(api, headers))[bank["id"]] == 1000
    await everything_agrees(api, db, headers, [personal])


async def test_an_added_amount_cannot_be_taken_back_below_what_was_paid(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    lent = await debt(api, headers, personal, amount="100", bank_account_id=bank["id"])
    base = f"{V1}/books/{personal['id']}/debts/{lent['id']}"
    await api.post(f"{base}/increase", headers=headers, json={"amount": "100", "bank_account_id": bank["id"]})
    await api.post(f"{base}/settle", headers=headers, json={"amount": "150", "bank_account_id": bank["id"]})
    grown = next(m for m in (await api.get(f"{base}/movements", headers=headers)).json()
                 if m["kind"] == "increase" and Decimal(m["amount"]) == 100 and m["note"] is None)
    # 100 + 100 added, 150 already paid: taking one 100 back would leave 100 against 150 paid.
    refused = await api.delete(f"{base}/movements/{grown['id']}", headers=headers)
    assert refused.status_code == 422


async def test_a_settled_debt_that_grows_is_open_again(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    owed = await debt(api, headers, personal, amount="100", bank_account_id=bank["id"])
    base = f"{V1}/books/{personal['id']}/debts/{owed['id']}"
    await api.post(f"{base}/settle", headers=headers, json={"bank_account_id": bank["id"]})
    assert (await api.get(f"{V1}/books/{personal['id']}/debts", headers=headers)).json() == []
    again = await api.post(f"{base}/increase", headers=headers, json={"amount": "50", "bank_account_id": bank["id"]})
    assert again.json()["is_settled"] is False and Decimal(again.json()["remaining"]) == 50


async def test_debt_cash_stays_inside_the_book_and_inside_the_currency(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    mine = await make_bank(api, headers, [personal])
    # An account of another book is not found; a stranger cannot reach the movements.
    other = await api.post(f"{V1}/books/{business['id']}/debts", headers=headers, json={
        "person": "علی", "amount": "10", "direction": "owed_to_me", "bank_account_id": mine["id"]})
    assert other.status_code == 404
    owed = await debt(api, headers, personal)
    stranger = bearer(await register(api, email="stranger9@example.com"))
    assert (await api.get(f"{V1}/books/{personal['id']}/debts/{owed['id']}/movements",
                          headers=stranger)).status_code == 404


async def test_the_real_balance_sets_the_opening_balance_to_what_the_books_do_not_explain(api, db):
    headers, personal, business = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal, business], opening_balance="999")
    await record(api, headers, business, "income", 3000)
    await record(api, headers, personal, "expense", 500)

    # The bank says 10,000 now; the books explain +3000 and -500, so 7,500 was there before them.
    done = await api.patch(f"{V1}/bank-accounts/{bank['id']}", headers=headers,
                           json={"current_balance": "10000"})
    assert done.status_code == 200, done.text
    assert Decimal(done.json()["opening_balance"]) == 7500
    assert Decimal(done.json()["total_balance"]) == 10000
    shares = {s["book_id"]: Decimal(s["balance"]) for s in done.json()["shares"]}
    assert shares == {business["id"]: 3000, personal["id"]: -500}  # each book keeps its own share
    await everything_agrees(api, db, headers, [personal, business])

    # Later entries move the total; saying the bank's figure again re-settles it.
    await record(api, headers, business, "income", 100)
    again = await api.patch(f"{V1}/bank-accounts/{bank['id']}", headers=headers,
                            json={"current_balance": "10000"})
    assert Decimal(again.json()["opening_balance"]) == 7400
    assert Decimal(again.json()["total_balance"]) == 10000


async def test_the_real_balance_and_an_opening_balance_are_not_both_accepted(api, db):
    headers, personal, _ = await owner_with_two_books(api, db)
    bank = await make_bank(api, headers, [personal])
    both = await api.patch(f"{V1}/bank-accounts/{bank['id']}", headers=headers,
                           json={"current_balance": "10", "opening_balance": "5"})
    assert both.status_code == 422
    stranger = bearer(await register(api, email="stranger10@example.com"))
    assert (await api.patch(f"{V1}/bank-accounts/{bank['id']}", headers=stranger,
                            json={"current_balance": "10"})).status_code == 404

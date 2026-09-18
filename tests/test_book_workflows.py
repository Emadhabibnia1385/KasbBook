"""Managed categories, complete transaction entry, invitations and account switching."""

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from kasbbook.adapters.base import Attachment, ChannelIdentity, EventKind, IncomingEvent
from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.bot.conversation import Conversation
from kasbbook.bot.delivery import deliver_invitations
from kasbbook.bot.state import MemoryStateStore, conversation_key
from kasbbook.modules.books.invitations import InvitationService
from kasbbook.modules.books.models import BookType, Role
from kasbbook.modules.books.service import BookService
from kasbbook.modules.identity.login import AccountLoginService
from kasbbook.modules.identity.models import AccountLoginChallenge, Provider
from kasbbook.modules.identity.service import IdentityService
from kasbbook.modules.ledger.categories import CategoryService
from kasbbook.modules.ledger.models import Flow, JournalEntry, Scope
from kasbbook.modules.ledger.service import LedgerService
from kasbbook.modules.loans.service import LoanService
from kasbbook.modules.budgets.models import BudgetKind
from kasbbook.modules.budgets.service import BudgetService
from kasbbook.modules.recurring.models import Period as RecurringPeriod
from kasbbook.modules.recurring.service import RecurringService
from kasbbook.modules.payroll.models import PeriodStatus
from kasbbook.modules.payroll.service import PayrollService
from kasbbook.shared.errors import NotFound, PermissionDenied, ValidationError
from kasbbook.shared.security import token_digest, utcnow
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio
DAY = date(2026, 8, 24)
TG = Provider.TELEGRAM
SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"


def event(external="100", provider=TG, **kwargs):
    kind = EventKind.MESSAGE
    if "callback_data" in kwargs:
        kind = EventKind.CALLBACK
    elif "command" in kwargs:
        kind = EventKind.COMMAND
    elif "attachment" in kwargs:
        kind = EventKind.ATTACHMENT
    return IncomingEvent(kind, ChannelIdentity(provider, external, "u" + external, "کاربر " + external),
                         chat_id=external, message_id="10", **kwargs)


async def account(session, external="100", provider=TG):
    convo = Conversation(session, MemoryStateStore(), provider)
    reply = await convo.handle(event(external, provider, command="start"))
    assert "⚠️" not in reply.text
    user = await IdentityService(session).user_for_identity(provider, external)
    return user, convo


async def begin_entry(convo, book, amount="۲۵۰ک", external="100", provider=TG):
    await convo.handle(event(external, provider, callback_data=f"tx:book:{book.id}"))
    await convo.handle(event(external, provider, callback_data="tx:flow:income"))
    await convo.handle(event(external, provider, text="فروش"))
    return await convo.handle(event(external, provider, text=amount))


@pytest.mark.parametrize("provider", [TG, Provider.BALE, Provider.RUBIKA])
async def test_new_account_and_captioned_receipt_complete_one_balanced_transaction(session, provider):
    user, convo = await account(session, provider=provider)
    book = await BookService(session).create_book(user.id, "دفتر", BookType.BUSINESS)
    reply = await begin_entry(convo, book, provider=provider)
    assert "توضیحات" in reply.text and "همراه" in reply.text
    assert any(b.data == "tx:skip" for row in reply.buttons for b in row)
    ledger = LedgerService(session)
    assert await ledger.transactions(book.id, user.id) == []
    reply = await convo.handle(event(provider=provider, text="رسید فروش امروز",
                                    attachment=Attachment("photo", "PHOTO-1")))
    (tx,) = await ledger.transactions(book.id, user.id)
    assert tx.description == "رسید فروش امروز"
    assert tx.receipt_file_id == "PHOTO-1" and tx.receipt_provider == provider.value
    assert tx.converted_amount == Decimal("250000") and tx.category_id is not None
    assert reply.forward_file_id == "PHOTO-1"
    assert [b.text for b in reply.buttons[0]] == ["ویرایش دسته", "ویرایش مبلغ", "ویرایش توضیحات"]
    debit, credit = await ledger.trial_balance(book.id)
    assert debit == credit == Decimal("250000")
    # A subsequent unrelated account must never inherit this receipt.
    stranger, _ = await account(session, "200", provider)
    reply = await convo.handle(event("200", provider, command="start"))
    assert stranger.id != user.id and reply.forward_file_id is None


async def test_description_refusal_cancel_and_skip_do_not_partially_record(session):
    user, convo = await account(session)
    book = await BookService(session).create_book(user.id, "دفتر", BookType.BUSINESS)
    ledger = LedgerService(session)
    await begin_entry(convo, book)
    reply = await convo.handle(event(text="x" * 501, attachment=Attachment("photo", "P")))
    assert "⚠️" in reply.text
    assert await ledger.transactions(book.id, user.id) == []
    await convo.handle(event(command="cancel"))
    await convo.handle(event(callback_data="tx:skip"))
    assert await ledger.transactions(book.id, user.id) == []
    await begin_entry(convo, book)
    await convo.handle(event(callback_data="tx:skip"))
    (tx,) = await ledger.transactions(book.id, user.id)
    assert tx.description is None and tx.receipt_file_id is None


async def test_member_can_attach_a_receipt_during_creation_without_editing_permission(session):
    owner, _ = await account(session)
    member, convo = await account(session, "200")
    book = await BookService(session).create_book(owner.id, "تیم", BookType.TEAM)
    await BookService(session).add_member(owner.id, book.id, member.id, Role.MEMBER)
    await begin_entry(convo, book, external="200")
    reply = await convo.handle(event("200", text="فروش تیم", attachment=Attachment("document", "PDF", "invoice.pdf")))
    assert "ثبت شد" in reply.text
    (tx,) = await LedgerService(session).transactions(book.id, owner.id)
    assert tx.actor_user_id == member.id and tx.receipt_file_name == "invoice.pdf"


async def test_category_management_is_reachable_and_used_categories_cannot_be_deleted(session):
    user, convo = await account(session)
    book = await BookService(session).create_book(user.id, "دفتر", BookType.BUSINESS)
    menu = await convo.handle(event(callback_data=f"book:open:{book.id}"))
    assert any(b.data == f"cg:list:{book.id}" for row in menu.buttons for b in row)
    await convo.handle(event(callback_data=f"cg:new:{book.id}"))
    await convo.handle(event(text="اجاره"))
    service = CategoryService(session)
    (category,) = await service.list(book.id, user.id)
    listing = await convo.handle(event(callback_data=f"cg:list:{book.id}"))
    assert "افزودن" in listing.buttons[0][0].text
    assert [b.text for b in listing.buttons[1]] == ["اجاره", "ویرایش", "حذف"]
    await convo.handle(event(callback_data=f"cg:edit:{category.id}"))
    await convo.handle(event(text="کرایه"))
    assert category.name == "کرایه"
    tx = await LedgerService(session).record(book.id, user.id, Flow.EXPENSE, Scope.WORK, category.name, "125.15", occurred_on=DAY)
    reply = await convo.handle(event(callback_data=f"cg:delok:{category.id}"))
    assert "قابل حذف نیست" in reply.text
    await LedgerService(session).delete(book.id, user.id, tx.id)
    await convo.handle(event(callback_data=f"cg:delok:{category.id}"))
    assert await service.list(book.id, user.id) == []
    assert await LedgerService(session).trial_balance(book.id) == (Decimal("0"), Decimal("0"))


async def test_category_duplicates_and_cross_book_callbacks_are_refused(session):
    owner, _ = await account(session)
    stranger, convo = await account(session, "200")
    book = await BookService(session).create_book(owner.id, "راز دفتر", BookType.BUSINESS)
    service = CategoryService(session)
    category = await service.create(book.id, owner.id, "راز دسته")
    with pytest.raises(ValidationError):
        await service.create(book.id, owner.id, " راز دسته ")
    for callback in (f"book:open:{book.id}", f"cg:list:{book.id}", f"cg:new:{book.id}", f"cg:edit:{category.id}", f"cg:delok:{category.id}"):
        reply = await convo.handle(event("200", callback_data=callback))
        assert "⚠️" in reply.text and "راز دفتر" not in reply.text and "راز دسته" not in reply.text
    with pytest.raises(NotFound):
        await service.rename(book.id, stranger.id, category.id, "x")
    assert category.name == "راز دسته"


async def test_category_rename_preserves_budget_recurring_and_journal_meaning(session):
    user, _ = await account(session)
    book = await BookService(session).create_book(user.id, "دفتر", BookType.BUSINESS)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.EXPENSE, Scope.WORK, "قدیمی", "10", occurred_on=DAY)
    categories = CategoryService(session)
    (category,) = await categories.list(book.id, user.id)
    budgets = BudgetService(session)
    budget = await budgets.set_budget(book.id, user.id, BudgetKind.CATEGORY, "قدیمی", "100")
    rule = await RecurringService(session).create(book.id, user.id, Flow.EXPENSE, "قدیمی", "10", RecurringPeriod.MONTHLY, DAY)
    await categories.rename(book.id, user.id, category.id, "جدید")
    assert tx.category == budget.target == rule.category == "جدید"
    assert (await session.scalar(select(JournalEntry).where(JournalEntry.transaction_id == tx.id))).memo == "expense: جدید"
    assert await ledger.trial_balance(book.id) == (Decimal("10"), Decimal("10"))
    await budgets.set_budget(book.id, user.id, BudgetKind.CATEGORY, "مقصد", "10")
    with pytest.raises(ValidationError):
        await categories.rename(book.id, user.id, category.id, "مقصد")
    assert tx.category == category.name == "جدید"


async def test_loan_payment_amount_cannot_be_changed_as_an_ordinary_transaction(session):
    user, _ = await account(session)
    book = await BookService(session).create_book(user.id, "دفتر", BookType.PERSONAL)
    loans = LoanService(session)
    loan = await loans.create(book.id, user.id, "وام", "10.15", 2, DAY)
    tx = await loans.record_payment(book.id, user.id, loan.id, on=DAY)
    with pytest.raises(ValidationError, match="قسط"):
        await LedgerService(session).update(book.id, user.id, tx.id, amount="20")
    assert tx.converted_amount == Decimal("10.15")


async def test_transaction_edits_preserve_id_rate_receipt_and_balanced_journal(session):
    user, convo = await account(session)
    book = await BookService(session).create_book(user.id, "دفتر", BookType.BUSINESS)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "قدیمی", "10.15",
                             occurred_on=DAY, currency="USD", conversion_rate="123.4567",
                             receipt_file_id="PHOTO", receipt_provider="telegram", receipt_kind="photo")
    await convo.handle(event(callback_data=f"td:ec:{tx.id}"))
    await convo.handle(event(text="جدید"))
    await convo.handle(event(callback_data=f"td:ea:{tx.id}"))
    await convo.handle(event(text="20.25"))
    await convo.handle(event(callback_data=f"td:ed:{tx.id}"))
    await convo.handle(event(text="شرح تازه"))
    assert tx.category == "جدید" and tx.description == "شرح تازه"
    assert tx.original_amount == Decimal("20.25") and tx.converted_amount == Decimal("2499.9982")
    assert tx.conversion_rate == Decimal("123.4567") and tx.receipt_file_id == "PHOTO"
    (entry,) = (await session.scalars(select(JournalEntry).where(JournalEntry.transaction_id == tx.id))).all()
    assert entry.memo == "income: جدید" and entry.total_debit == tx.converted_amount
    assert await ledger.trial_balance(book.id) == (tx.converted_amount, tx.converted_amount)
    await convo.handle(event(callback_data=f"td:ed:{tx.id}"))
    await convo.handle(event(callback_data="td:clear_description"))
    assert tx.description is None
    with pytest.raises(ValidationError):
        await ledger.update(book.id, user.id, tx.id, amount="-1")
    assert tx.converted_amount == Decimal("2499.9982")


async def test_amount_rounding_to_zero_never_leaves_a_partial_financial_write(session):
    user, _ = await account(session)
    book = await BookService(session).create_book(user.id, "دفتر", BookType.BUSINESS)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", "10",
                             currency="USD", conversion_rate="0.0001", occurred_on=DAY)
    before = await ledger.trial_balance(book.id)
    with pytest.raises(ValidationError):
        await ledger.update(book.id, user.id, tx.id, amount="0.0001", category="جدید")
    assert tx.original_amount == Decimal("10") and tx.category == "فروش"
    assert await ledger.trial_balance(book.id) == before


async def test_calculated_and_locked_periods_refuse_financial_mutations(session):
    user, _ = await account(session)
    book = await BookService(session).create_book(user.id, "تیم", BookType.TEAM)
    ledger = LedgerService(session)
    tx = await ledger.record(book.id, user.id, Flow.INCOME, Scope.TEAM, "فروش", "10", occurred_on=DAY)
    payroll = PayrollService(session)
    period = await payroll.open_period(user.id, book.id, "دوره", DAY, DAY)
    await payroll.advance_period(user.id, period.id, PeriodStatus.CALCULATING)
    for operation in (lambda: ledger.update(book.id, user.id, tx.id, amount="20"),
                      lambda: ledger.delete(book.id, user.id, tx.id),
                      lambda: ledger.record(book.id, user.id, Flow.EXPENSE, Scope.TEAM, "هزینه", "1", occurred_on=DAY)):
        with pytest.raises(PermissionDenied):
            await operation()
    assert tx.original_amount == Decimal("10")
    assert await ledger.trial_balance(book.id) == (Decimal("10"), Decimal("10"))


async def test_receipt_is_not_forwarded_to_a_different_provider(session):
    user, _ = await account(session)
    identity = IdentityService(session)
    issued = await identity.start_link_from_web(user.id, Provider.BALE)
    await identity.complete_link_from_messenger(issued.token, Provider.BALE, "100")
    book = await BookService(session).create_book(user.id, "دفتر", BookType.BUSINESS)
    tx = await LedgerService(session).record(book.id, user.id, Flow.INCOME, Scope.WORK, "فروش", "1",
        occurred_on=DAY, receipt_file_id="TG-PHOTO", receipt_provider="telegram", receipt_kind="photo")
    bale = Conversation(session, MemoryStateStore(), Provider.BALE)
    reply = await bale.handle(event(provider=Provider.BALE, callback_data=f"td:open:{tx.id}"))
    assert reply.forward_file_id is None and "پیام‌رسانی" in reply.text


async def test_team_invitation_needs_consent_and_is_bound_to_recipient_and_provider(session):
    owner, convo = await account(session)
    recipient, recipient_convo = await account(session, "200")
    bale_user, _ = await account(session, "200", Provider.BALE)
    stranger, _ = await account(session, "300")
    books = BookService(session)
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)
    await convo.handle(event(callback_data=f"iv:new:{book.id}"))
    await convo.handle(event(text="@u200"))
    invitations = InvitationService(session)
    (invitation,) = await invitations.incoming(recipient.id)
    assert await books.membership(book.id, recipient.id) is None
    assert await invitations.incoming(bale_user.id) == []
    with pytest.raises(NotFound):
        await invitations.respond(invitation.id, stranger.id, True)
    class Adapter:
        provider = TG
        messages = []

        async def send_message(self, message):
            self.messages.append(message)
            return "1"
    adapter = Adapter()
    assert await deliver_invitations(session, adapter) == 1
    assert adapter.messages[0].chat_id == "200"
    assert await deliver_invitations(session, adapter) == 0
    reply = await recipient_convo.handle(event("200", callback_data=f"iv:yes:{invitation.id}"))
    assert "تیم" in reply.text
    assert (await books.membership(book.id, recipient.id)).role is Role.MEMBER
    with pytest.raises(ValidationError):
        await invitations.respond(invitation.id, recipient.id, True)


async def test_invitation_decline_and_sender_permission_loss_do_not_grant_membership(session):
    owner, _ = await account(session)
    admin, _ = await account(session, "200")
    recipient, _ = await account(session, "300")
    books = BookService(session)
    book = await books.create_book(owner.id, "تیم", BookType.TEAM)
    await books.add_member(owner.id, book.id, admin.id, Role.ADMIN)
    invitations = InvitationService(session)
    declined = await invitations.create(book.id, admin.id, TG, "300")
    await invitations.respond(declined.id, recipient.id, False)
    assert await books.membership(book.id, recipient.id) is None
    row = await invitations.create(book.id, admin.id, TG, "300")
    await books.deactivate_member(owner.id, book.id, admin.id)
    with pytest.raises(NotFound):
        await invitations.respond(row.id, recipient.id, True)
    assert await books.membership(book.id, recipient.id) is None


async def login_setup(session):
    source, convo = await account(session)
    target, _ = await account(session, "200")
    identity = IdentityService(session)
    await identity.set_contact(target.id, email="target@example.com")
    requester = await identity.find_identity(TG, "100")
    return source, target, requester, convo


async def test_login_code_is_delivered_only_to_existing_account_and_switches_no_books(session):
    source, target, requester, convo = await login_setup(session)
    identity = IdentityService(session)
    await identity.set_contact(source.id, email="source@example.com")
    await identity.set_password(source.id, "a-good-password")
    books = BookService(session)
    source_book = await books.create_book(source.id, "قبلی", BookType.BUSINESS)
    target_book = await books.create_book(target.id, "مقصد", BookType.BUSINESS)
    tx = await LedgerService(session).record(source_book.id, source.id, Flow.INCOME, Scope.WORK, "فروش", "12.15", occurred_on=DAY)
    await convo.handle(event(callback_data="acc:login"))
    reply = await convo.handle(event(text="target@example.com"))
    assert len(reply.notifications) == 1 and reply.notifications[0].chat_id == "200"
    code = re.search(r"[A-Z2-9]{10}", reply.notifications[0].text).group()
    assert code not in reply.text
    draft = await convo.state.get(conversation_key("telegram", "100"))
    assert code not in str(draft)
    challenge = await session.get(AccountLoginChallenge, uuid.UUID(draft["challenge_id"]))
    assert challenge.token_digest == token_digest(code) and challenge.consumed_at is None
    reply = await convo.handle(event(text=code))
    assert "⚠️" not in reply.text and not reply.notifications
    assert requester.user_id == target.id
    assert [b.id for b in await books.books_for_user(target.id)] == [target_book.id]
    assert [b.id for b in await books.books_for_user(source.id)] == [source_book.id]
    assert tx.actor_user_id == source.id and tx.converted_amount == Decimal("12.15")
    assert source.token_generation == target.token_generation == 1
    assert await convo.state.get(conversation_key("telegram", "100")) == {}
    assert await AccountLoginService(session).complete(target.id, requester.id, challenge.id, code) is None


async def test_login_wrong_codes_exhaust_budget_expire_and_cannot_be_claimed_by_another_user(session):
    source, target, requester, _ = await login_setup(session)
    service = AccountLoginService(session)
    issued = await service.request(source.id, requester.id, "target@example.com")
    stranger, _ = await account(session, "300")
    with pytest.raises(NotFound):
        await service.complete(stranger.id, requester.id, issued.challenge_id, issued.code)
    for _ in range(5):
        assert await service.complete(source.id, requester.id, issued.challenge_id, "WRONG") is None
    assert await service.complete(source.id, requester.id, issued.challenge_id, issued.code) is None
    assert requester.user_id == source.id and target.id != source.id
    second = await service.request(source.id, requester.id, "target@example.com")
    row = await session.get(AccountLoginChallenge, second.challenge_id)
    row.expires_at = utcnow() - timedelta(minutes=1)
    await session.flush()
    assert await service.complete(source.id, requester.id, second.challenge_id, second.code) is None


async def test_login_unknown_and_cross_provider_destinations_have_identical_response(session):
    source, target, requester, convo = await login_setup(session)
    await convo.handle(event(callback_data="acc:login"))
    known = await convo.handle(event(text="target@example.com"))
    await convo.handle(event(callback_data="acc:login"))
    unknown = await convo.handle(event(text="unknown@example.com"))
    assert known.text == unknown.text and unknown.notifications == []
    bale, _ = await account(session, "300", Provider.BALE)
    await IdentityService(session).set_contact(bale.id, email="bale@example.com")
    issued = await AccountLoginService(session).request(source.id, requester.id, "bale@example.com")
    assert issued.destination_external_id is None
    assert target.id != bale.id


async def test_login_refuses_to_strand_source_books_and_limits_requests(session):
    source, _, requester, _ = await login_setup(session)
    await BookService(session).create_book(source.id, "دفتر", BookType.BUSINESS)
    service = AccountLoginService(session)
    with pytest.raises(ValidationError, match="قابل دسترسی"):
        await service.request(source.id, requester.id, "target@example.com")
    identity = IdentityService(session)
    await identity.set_contact(source.id, email="source@example.com")
    await identity.set_password(source.id, "a-good-password")
    for _ in range(5):
        await service.request(source.id, requester.id, "unknown@example.com")
    with pytest.raises(ValidationError, match="درخواست"):
        await service.request(source.id, requester.id, "unknown@example.com")


@pytest.fixture
async def api(db):
    app = create_app(Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET), db, MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def api_user(api, email):
    response = await api.post("/api/v1/auth/register", json={
        "display_name": "کاربر", "email": email, "password": "a-good-password"})
    assert response.status_code == 201
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    me = (await api.get("/api/v1/auth/me", headers=headers)).json()
    return headers, uuid.UUID(me["id"])


async def test_api_categories_and_transaction_edits_share_bot_state_and_exact_money(api, session):
    headers, user_id = await api_user(api, "owner@example.com")
    book = (await api.post("/api/v1/books", headers=headers, json={"name": "دفتر", "type": "business"})).json()
    path = f"/api/v1/books/{book['id']}"
    category = await api.post(path + "/categories", headers=headers, json={"name": "فروش"})
    assert category.status_code == 201
    tx = (await api.post(path + "/transactions", headers=headers, json={
        "flow": "income", "category": "فروش", "amount": "12345678.9999", "currency": "IRR", "occurred_on": DAY.isoformat()})).json()
    changed = await api.patch(path + f"/transactions/{tx['id']}", headers=headers,
                              json={"amount": "0.15", "description": "شرح"})
    assert changed.status_code == 200
    assert changed.json()["converted_amount"] == "0.1500"
    renamed = await api.patch(path + f"/categories/{category.json()['id']}", headers=headers, json={"name": "جدید"})
    assert renamed.status_code == 200
    row = await LedgerService(session).get_transaction(uuid.UUID(book["id"]), user_id, uuid.UUID(tx["id"]))
    assert row.category == "جدید" and row.description == "شرح"
    assert await LedgerService(session).trial_balance(uuid.UUID(book["id"])) == (Decimal("0.15"), Decimal("0.15"))
    assert (await api.delete(path + f"/categories/{category.json()['id']}", headers=headers)).status_code == 422
    for changes in ({"amount": None}, {"category": None}, {}, {"amount": "-1"}):
        assert (await api.patch(path + f"/transactions/{tx['id']}", headers=headers, json=changes)).status_code == 422
    cleared = await api.patch(path + f"/transactions/{tx['id']}", headers=headers, json={"description": None})
    assert cleared.status_code == 200 and cleared.json()["description"] is None


async def test_api_cross_user_book_and_transaction_changes_return_not_found(api):
    owner, _ = await api_user(api, "owner@example.com")
    stranger, _ = await api_user(api, "stranger@example.com")
    book = (await api.post("/api/v1/books", headers=owner, json={"name": "راز", "type": "business"})).json()
    path = f"/api/v1/books/{book['id']}"
    category = (await api.post(path + "/categories", headers=owner, json={"name": "فروش"})).json()
    tx = (await api.post(path + "/transactions", headers=owner, json={"flow": "income", "category": "فروش", "amount": "1"})).json()
    assert (await api.get(path + "/categories", headers=stranger)).status_code == 404
    assert (await api.post(path + "/categories", headers=stranger, json={"name": "x"})).status_code == 404
    assert (await api.patch(path + f"/categories/{category['id']}", headers=stranger, json={"name": "x"})).status_code == 404
    assert (await api.delete(path + f"/categories/{category['id']}", headers=stranger)).status_code == 404
    assert (await api.patch(path + f"/transactions/{tx['id']}", headers=stranger, json={"amount": "2"})).status_code == 404
    assert (await api.post(path + "/invitations", headers=stranger, json={"provider": "telegram", "identifier": "100"})).status_code == 404


async def test_api_invitation_requires_recipient_consent(api, session):
    owner, _ = await api_user(api, "owner@example.com")
    recipient, recipient_id = await api_user(api, "recipient@example.com")
    stranger, _ = await api_user(api, "stranger@example.com")
    identities = IdentityService(session)
    issued = await identities.start_link_from_web(recipient_id, Provider.BALE)
    await identities.complete_link_from_messenger(issued.token, Provider.BALE, "200")
    await session.commit()
    book = (await api.post("/api/v1/books", headers=owner, json={"name": "تیم", "type": "team"})).json()
    response = await api.post(f"/api/v1/books/{book['id']}/invitations", headers=owner,
                              json={"provider": "bale", "identifier": "200"})
    assert response.status_code == 201
    invitation = response.json()
    assert (await api.get(f"/api/v1/books/{book['id']}", headers=recipient)).status_code == 404
    path = f"/api/v1/invitations/{invitation['id']}/respond"
    assert (await api.post(path, headers=stranger, json={"accept": True})).status_code == 404
    assert (await api.get("/api/v1/invitations", headers=recipient)).json()[0]["id"] == invitation["id"]
    assert (await api.post(path, headers=recipient, json={"accept": True})).json()["status"] == "accepted"
    assert (await api.get(f"/api/v1/books/{book['id']}", headers=recipient)).status_code == 200
    assert (await api.post(path, headers=recipient, json={"accept": True})).status_code == 422


async def test_api_account_login_delivers_proof_only_to_existing_identity(api, session):
    source_headers, source_id = await api_user(api, "source@example.com")
    target_headers, target_id = await api_user(api, "target@example.com")
    identities = IdentityService(session)
    for user_id, external in ((source_id, "100"), (target_id, "200")):
        link = await identities.start_link_from_web(user_id, Provider.TELEGRAM)
        await identities.complete_link_from_messenger(link.token, Provider.TELEGRAM, external)
    requester = (await identities.list_identities(source_id))[0]
    await session.commit()
    class Adapter:
        def __init__(self):
            self.sent = []
        async def send_message(self, message):
            self.sent.append(message)
            return "1"
        async def aclose(self):
            pass
    adapter = Adapter()
    api._transport.app.state.adapters = {"telegram": adapter}
    path = "/api/v1/identities/account-login"
    body = {"identity_id": str(requester.id), "identifier": "target@example.com"}
    assert (await api.post(path + "/request", headers=target_headers, json=body)).status_code == 404
    response = await api.post(path + "/request", headers=source_headers, json=body)
    assert response.status_code == 201
    assert set(response.json()) == {"challenge_id", "expires_in"}
    assert len(adapter.sent) == 1 and adapter.sent[0].chat_id == "200"
    code = re.search(r"[A-Z0-9]{10}", adapter.sent[0].text).group()
    complete = {"identity_id": str(requester.id), "challenge_id": response.json()["challenge_id"], "code": "WRONG"}
    assert (await api.post(path + "/complete", headers=source_headers, json=complete)).json() == {"success": False}
    row = await session.get(AccountLoginChallenge, uuid.UUID(complete["challenge_id"]))
    await session.refresh(row)
    assert row.attempts == 1
    complete["code"] = code
    assert (await api.post(path + "/complete", headers=source_headers, json=complete)).json() == {"success": True}
    assert (await api.get("/api/v1/auth/me", headers=source_headers)).status_code == 401
    assert (await api.get("/api/v1/auth/me", headers=target_headers)).status_code == 401
    await session.refresh(requester)
    assert requester.user_id == target_id

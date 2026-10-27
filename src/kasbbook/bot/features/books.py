"""Books in the bot: listing and opening them, creating one, its categories, and inviting a teammate.

A book is the unit everything else hangs off, so this is where a person arrives
before any entry, report or plan; the permission checks themselves stay in the
services.
"""

from __future__ import annotations

import uuid

from ...modules.books.models import BookType, Permission
from ...shared.parsing import to_ascii_digits
from .. import screens
from ..state import DEFAULT_TTL_SECONDS
from .base import BOOK_NAME_LIMIT, Feature


class BooksFeature(Feature):
    prefixes = ("book", "cg", "iv")
    flows = ("new_book", "category_manage", "team_invite")

    async def callback(self, area, parts, user, key, event):
        action = parts[1] if len(parts) > 1 else ""
        argument = parts[2] if len(parts) > 2 else ""
        if area == "book":
            return await self._book_callback(action, argument, user, key)
        if area == "cg":
            # «➕ افزودن دستهٔ هزینه» names the type in a fourth part, so the
            # create path no longer has to ask for a tap already made.
            tail = parts[3] if len(parts) > 3 else ""
            return await self._category_callback(action, argument, user, key, tail)
        if area == "iv":
            return await self._invitation_callback(action, argument, user, key)
        raise AssertionError(area)

    async def text(self, text, draft, user, key, event):
        if draft.get("flow") == "new_book":
            return await self._new_book_text(text, draft, user, key)
        if draft.get("flow") == "category_manage":
            return await self._category_text(text, draft, user, key)
        if draft.get("flow") == "team_invite":
            return await self._team_invite_text(text, draft, user, key)
        raise AssertionError(draft.get("flow"))

    # --------------------------------------------------------------- books
    async def _book_callback(self, action: str, argument: str, user, key: str):
        if action == "list":
            return screens.book_list(await self.ctx.books.books_for_user(user.id))

        if action == "new":
            return screens.new_book_type()

        if action == "type":
            book_type = BookType(argument)
            await self.ctx.state.set(
                key, {"flow": "new_book", "type": book_type.value}, DEFAULT_TTL_SECONDS
            )
            return screens.ask_book_name(book_type)

        if action == "open":
            await self.ctx.books.require(uuid.UUID(argument), user.id, Permission.VIEW_TRANSACTIONS)
            book = await self.ctx.books.get_book(uuid.UUID(argument))
            return screens.book_menu(book)

        return screens.book_list(await self.ctx.books.books_for_user(user.id))

    async def _category_text(self, text: str, draft: dict, user, key: str):
        draft["name"] = self.ctx.categories.name(text)
        if draft.get("direction") and not draft.get("category_id"):
            # The type arrived with the button that opened this flow, so the
            # name was the last thing missing: record it instead of asking.
            book_id = uuid.UUID(draft["book_id"])
            await self.ctx.categories.create(book_id, user.id, draft["name"], draft["direction"])
            await self.ctx.state.clear(key)
            return await self._category_screen(book_id, user)
        draft["stage"] = "type"
        await self.ctx.state.set(key, draft)
        return screens.ask_category_flow(draft.get("book_name", ""), draft["name"])

    async def _team_invite_text(self, text: str, draft: dict, user, key: str):
        row = await self.ctx.invitations.create(uuid.UUID(draft["book_id"]), user.id, self.ctx.provider,
                                             to_ascii_digits(text))
        await self.ctx.state.clear(key)
        person = await self.ctx.identity.get_user(row.recipient_user_id)
        return screens.invitation_queued(person.display_name, row.book_id)

    async def _new_book_text(self, text: str, draft: dict, user, key: str):
        book_type = BookType(draft["type"])
        name = " ".join(text.split())
        if not name:
            return screens.ask_book_name(book_type, "اسم دفتر خالی است.")
        if len(name) > BOOK_NAME_LIMIT:
            return screens.ask_book_name(
                book_type,
                f"اسم دفتر {len(name)} حرف است؛ حداکثر {BOOK_NAME_LIMIT} حرف بنویس.",
            )
        book = await self.ctx.books.create_book(user.id, name, book_type)
        await self.ctx.state.clear(key)
        first = len(await self.ctx.books.books_for_user(user.id)) == 1
        return screens.book_created(book, first)

    async def _category_screen(self, book_id, user):
        rows = await self.ctx.categories.list(book_id, user.id)
        return screens.category_list(await self.ctx.books.get_book(book_id), rows)

    async def _category_callback(self, action, argument, user, key, tail=""):
        if action in ("keep", "type"):
            draft = await self.ctx.state.get(key)
            # A refusal here has a parent: the list this draft belongs to. Only
            # a draft from some other flow leaves nothing to go back to, and
            # then error() falls back to the main menu on its own.
            book_id = draft.get("book_id")
            back = f"cg:list:{book_id}" if book_id else None
            if draft.get("flow") != "category_manage":
                return screens.error("ابتدا «افزودن دسته» یا «ویرایش» را بزن.", back)
            if action == "keep":
                if not draft.get("category_id") or not draft.get("name"):
                    return screens.error("نام دسته را بنویس؛ مثلاً: اجاره.", back)
                draft["stage"] = "type"
                await self.ctx.state.set(key, draft)
                return screens.ask_category_flow(draft.get("book_name", ""), draft["name"])
            if draft.get("stage") != "type":
                return screens.error("ابتدا نام دسته را بنویس؛ مثلاً: اجاره.", back)
            book_id = uuid.UUID(draft["book_id"])
            if draft.get("category_id"):
                await self.ctx.categories.update(book_id, user.id, uuid.UUID(draft["category_id"]),
                                             name=draft["name"], flow=argument)
            else:
                await self.ctx.categories.create(book_id, user.id, draft["name"], argument)
            await self.ctx.state.clear(key)
            return await self._category_screen(book_id, user)
        if action in ("list", "new"):
            book_id = uuid.UUID(argument)
            if action == "list":
                await self.ctx.state.clear(key)
                return await self._category_screen(book_id, user)
            await self.ctx.categories.require_create(book_id, user.id)
            book = await self.ctx.books.get_book(book_id)
            draft = {"flow": "category_manage", "book_id": argument, "book_name": book.name}
            # `stage` stays unset: the name is still missing, and a stale
            # «درآمد/هزینه» button must not be able to create a nameless
            # category just because its type is already known.
            if tail in ("income", "expense"):
                draft["direction"] = tail
            await self.ctx.state.set(key, draft)
            return screens.ask_category_name(book_name=book.name,
                                             direction=draft.get("direction", ""))
        for book in await self.ctx.books.books_for_user(user.id):
            rows = await self.ctx.categories.list(book.id, user.id)
            row = next((r for r in rows if str(r.id) == argument), None)
            if row is None:
                continue
            if action == "del":
                return screens.confirm_delete(row.name, f"cg:delok:{row.id}", f"cg:list:{book.id}")
            if action == "delok":
                await self.ctx.categories.delete(book.id, user.id, row.id)
                return await self._category_screen(book.id, user)
            if action == "edit":
                await self.ctx.books.require(book.id, user.id, Permission.EDIT_TRANSACTION)
                await self.ctx.state.set(key, {"flow": "category_manage", "book_id": str(book.id),
                                          "book_name": book.name,
                                          "category_id": str(row.id), "name": row.name})
                return screens.ask_category_name(row.name, book.name)
            return await self._category_screen(book.id, user)
        # No book of this person's owns that id, so there is no category list to
        # send them back to; their own books are the nearest real parent.
        return screens.error("این دسته دیگر وجود ندارد؛ شاید حذف شده است.", "book:list")

    async def _invitation_callback(self, action, argument, user, key):
        if action == "new":
            await self.ctx.books.require(uuid.UUID(argument), user.id, Permission.MANAGE_MEMBERS)
            await self.ctx.state.set(key, {"flow": "team_invite", "book_id": argument})
            return screens.ask_teammate()
        if action in ("yes", "no"):
            row = await self.ctx.invitations.respond(uuid.UUID(argument), user.id, action == "yes")
            await self.ctx.state.clear(key)
            if action == "yes":
                return screens.book_menu(await self.ctx.books.get_book(row.book_id))
            return screens.invitation_declined()
        rows = await self.ctx.invitations.incoming(user.id)
        if action == "open":
            row = next((r for r in rows if str(r.id) == argument), None)
            if row is None:
                return screens.error("دعوت پیدا نشد.", "iv:inbox")
            return screens.team_invitation(await self.ctx.books.get_book(row.book_id), row)
        books = {row.book_id: await self.ctx.books.get_book(row.book_id) for row in rows}
        return screens.invitation_inbox(rows, books)

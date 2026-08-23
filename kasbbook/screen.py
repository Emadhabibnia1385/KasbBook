"""One screen per chat.

Menus and prompts are screens, not messages. In single-message mode the bot
keeps exactly one message per chat — the anchor — and edits it in place, while
the lines the user types are removed once they have been read. The chat stays a
control panel instead of turning into a transcript.

Everything that shows a screen goes through `render`, so there is one place that
decides whether to edit or post, and one place that recovers when the anchor is
gone.
"""

from typing import Optional

from telegram import InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from .config import ZWSP
from .store import get_setting
from .text import safe_edit

ANCHOR_KEY = "anchor_id"


def single_message_on() -> bool:
    try:
        return get_setting("single_message") == "1"
    except Exception:
        return True


def _is_private(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


async def drop_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the line the user just typed, once it has been acted on."""
    if not single_message_on() or not _is_private(update):
        return

    msg = update.message
    if not msg:
        return

    try:
        await msg.delete()
    except Exception:
        # Older than Telegram's 48h window, or already gone. Not worth
        # failing a flow the user completed successfully.
        pass


async def reset_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forget the current anchor, deleting it so the next render starts clean."""
    old = context.chat_data.pop(ANCHOR_KEY, None)
    if not old or not single_message_on() or not _is_private(update):
        return

    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old)
    except Exception:
        pass


async def render(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Show a screen: edit the anchor if there is one, otherwise post it."""
    chat = update.effective_chat
    q = update.callback_query

    # A button press already carries the message to edit.
    if q is not None and q.message is not None:
        context.chat_data[ANCHOR_KEY] = q.message.message_id
        await safe_edit(q, text, reply_markup=reply_markup)
        return

    await drop_user_message(update, context)

    anchor = context.chat_data.get(ANCHOR_KEY) if single_message_on() else None
    if anchor is not None:
        try:
            await context.bot.edit_message_text(
                chat_id=chat.id,
                message_id=anchor,
                text=text,
                reply_markup=reply_markup,
            )
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
            # The anchor was deleted, is too old to edit, or belonged to another
            # kind of message. Fall through and start a fresh one.
            context.chat_data.pop(ANCHOR_KEY, None)
        except Exception:
            context.chat_data.pop(ANCHOR_KEY, None)

    sent = await chat.send_message(text, reply_markup=reply_markup)
    context.chat_data[ANCHOR_KEY] = sent.message_id


async def notify(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    """A standalone message that is not a screen — kept out of the anchor.

    Used for things the user should be able to scroll back to, like a file
    caption, rather than for anything that belongs on the control panel.
    """
    await update.effective_chat.send_message(text)


async def clear_reply_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Retire any reply keyboard an older version of the bot left behind.

    Telegram only removes one as a side effect of sending a message, so this
    sends an invisible marker and immediately deletes it again — otherwise the
    marker itself would be the clutter we are trying to avoid.
    """
    try:
        marker = await update.effective_chat.send_message(ZWSP, reply_markup=ReplyKeyboardRemove())
    except Exception:
        return

    try:
        await marker.delete()
    except Exception:
        pass

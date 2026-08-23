"""Handler registration and the entry point."""

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from .access import access_allowed, deny, is_primary_admin
from .backups import schedule_backup_job
from .config import BOT_TOKEN, DB_PATH, PROJECT_NAME, logger
from .handlers.admin import adm_add_name, adm_add_uid, admin_panel_cb
from .handlers.categories import cat_add_name, cat_rename_name, cats_cb
from .handlers.common import access_cb, cancel_cmd, main_cb, on_error, settings_cb, setup_commands, start, unknown_callback
from .handlers.database import currency_cb, currency_custom_input, db_cb, db_interval_entry, db_restore_entry, db_restore_wait_doc, db_set_interval_input, db_set_target_id_input, db_target_choice_cb, reminder_days_input, reminder_hour_input, reminders_cb
from .handlers.finance import budget_amount_input, budget_catname_input, budgets_cb, debt_amount_input, debt_dir_cb, debt_due_input, debt_due_skip, debt_note_input, debt_note_skip, debt_person_input, debts_cb, loan_amount_input, loan_count_input, loan_start_input, loan_title_input, loans_cb, rc_amount_input, rc_cat_input, rc_desc_input, rc_desc_skip, rc_period_cb, rc_start_input, rc_ttype_cb, recurring_cb
from .handlers.quick import quick_entry, quick_entry_cb
from .handlers.reports import range_end_input, range_entry, range_start_input, report_cb, search_entry, search_page_cb, search_query_input, trend_cb
from .handlers.transactions import daily_cb, dl_date_g_input, dl_date_j_input, dtx_cb, edit_amount_input, edit_date_g_input, edit_date_j_input, edit_date_menu_cb, edit_desc_input, receipt_wait, tx_amount_input, tx_cat_add_name_input, tx_cat_pick_cb, tx_date_g_input, tx_date_j_input, tx_date_menu_cb, tx_desc_input, tx_desc_skip, tx_entry_from_daily, tx_entry_from_menu, tx_ttype_cb
from .menus import access_menu, main_menu, start_text
from .recurring import schedule_recurring_job
from .reminders import schedule_digest_job
from .states import ADM_ADD_NAME, ADM_ADD_UID, BG_AMOUNT, BG_CATNAME, BG_PICK, CAT_ADD_NAME, CAT_RENAME_NAME, CU_CUSTOM, DB_RESTORE_WAIT_DOC, DB_SET_INTERVAL, DB_SET_TARGET_ID, DL_DATE_G, DL_DATE_J, DL_DATE_MENU, DT_AMOUNT, DT_DIR, DT_DUE, DT_NOTE, DT_PERSON, ED_AMOUNT, ED_DATE_G, ED_DATE_J, ED_DATE_MENU, ED_DESC, LN_AMOUNT, LN_COUNT, LN_START, LN_TITLE, RCP_WAIT, RC_AMOUNT, RC_CAT, RC_DESC, RC_PERIOD, RC_START, RC_TTYPE, RG_END, RG_START, RM_DAYS, RM_HOUR, SR_QUERY, TX_AMOUNT, TX_CAT_ADD_NAME, TX_CAT_PICK, TX_DATE_G, TX_DATE_J, TX_DATE_MENU, TX_DESC, TX_TTYPE
from .store import init_db
from .text import rtl, safe_edit

# =========================
# Build app (Handlers OK)
# =========================
def build_app() -> Application:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    async def _post_init(application: Application) -> None:
        await setup_commands(application)
        schedule_backup_job(application)
        schedule_recurring_job(application)
        schedule_digest_job(application)

    app.post_init = _post_init

    # Every conversation can be escaped with /start or /cancel.
    common_fallbacks = [CommandHandler("start", start), CommandHandler("cancel", cancel_cmd)]

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # Main
    app.add_handler(CallbackQueryHandler(main_cb, pattern=r"^m:(home|tx|st|report|noop)$"))

    # Settings / Access
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^st:(cats|access|cur|db)$"))
    app.add_handler(CallbackQueryHandler(access_cb, pattern=r"^ac:(mode:(admin_only|public)|share)$"))

    async def ac_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        user = update.effective_user
        if not access_allowed(user.id):
            await deny(update)
            return
        await q.answer()
        if is_primary_admin(user.id):
            await safe_edit(q, rtl("🔐 دسترسی ربات:"), reply_markup=access_menu(user.id))
        else:
            await safe_edit(q, rtl(start_text()), reply_markup=main_menu())

    app.add_handler(CallbackQueryHandler(ac_noop, pattern=r"^ac:noop$"))

    # Admin panel (view/page/delete) - "add" is a conversation entry point
    app.add_handler(
        CallbackQueryHandler(
            admin_panel_cb,
            pattern=r"^ad:(panel|noop|page:\d+|del:\d+|delok:\d+)$",
        )
    )

    adm_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_panel_cb, pattern=r"^ad:add$")],
        states={
            ADM_ADD_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_uid)],
            ADM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_add_name)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(adm_conv)

    # Categories (view/page/delete) - "add"/"rename" are conversation entry points
    app.add_handler(
        CallbackQueryHandler(
            cats_cb,
            pattern=(
                r"^ct:(grp:(work_in|work_out|personal_in|personal_out)"
                r"|page:(work_in|work_out|personal_in|personal_out):\d+"
                r"|del:\d+|delok:\d+|noop)$"
            ),
        )
    )

    cat_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:add:(work_in|work_out|personal_in|personal_out)$")],
        states={CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_add_name)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(cat_conv)

    cat_rename_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cats_cb, pattern=r"^ct:ren:\d+$")],
        states={
            CAT_RENAME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cat_rename_name)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(cat_rename_conv)

    # Daily list (date picker conversation)
    dl_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(daily_cb, pattern=r"^dl:pick$")],
        states={
            DL_DATE_MENU: [CallbackQueryHandler(daily_cb, pattern=r"^dl:d:(today|g|j)$")],
            DL_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, dl_date_g_input)],
            DL_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, dl_date_j_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(dl_conv)

    # Daily non-conversation callbacks (including per-section paging)
    app.add_handler(
        CallbackQueryHandler(
            daily_cb,
            pattern=(
                r"^dl:(d:(today|g|j)"
                r"|show:\d{4}-\d{2}-\d{2}"
                r"|page:\d{4}-\d{2}-\d{2}(?::\d+)+"
                r"|noop)$"
            ),
        )
    )

    # Transaction creation conversation
    tx_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(tx_entry_from_menu, pattern=r"^tx:new$"),
            CallbackQueryHandler(tx_entry_from_daily, pattern=r"^dl:add:\d{4}-\d{2}-\d{2}:(work_in|work_out|personal_in|personal_out)$"),
        ],
        states={
            TX_DATE_MENU: [CallbackQueryHandler(tx_date_menu_cb, pattern=r"^tx:date:(today|g|j)$")],
            TX_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_g_input)],
            TX_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_date_j_input)],
            TX_TTYPE: [CallbackQueryHandler(tx_ttype_cb, pattern=r"^tx:tt:(work_in|work_out|personal_in|personal_out)$")],
            TX_CAT_PICK: [CallbackQueryHandler(tx_cat_pick_cb, pattern=r"^tx:(cat:\d+|catp:\d+|cat_add)$")],
            TX_CAT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_cat_add_name_input)],
            TX_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, tx_amount_input)],
            TX_DESC: [
                CommandHandler("skip", tx_desc_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, tx_desc_input),
            ],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(tx_conv)

    # TX details (view / delete-with-confirm / category picker)
    app.add_handler(
        CallbackQueryHandler(
            dtx_cb,
            pattern=r"^dtx:(open|del|delok|undo|cat|rcpv|rcpd):\d{4}-\d{2}-\d{2}:\d+$",
        )
    )
    app.add_handler(CallbackQueryHandler(dtx_cb, pattern=r"^dtx:catp:\d{4}-\d{2}-\d{2}:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(dtx_cb, pattern=r"^dtx:setcat:\d{4}-\d{2}-\d{2}:\d+:\d+$"))

    # Edit amount conversation
    edit_amt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:amt:\d{4}-\d{2}-\d{2}:\d+$")],
        states={ED_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_amount_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(edit_amt_conv)

    # Edit description conversation
    edit_desc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:desc:\d{4}-\d{2}-\d{2}:\d+$")],
        states={ED_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_desc_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(edit_desc_conv)

    # Edit date conversation ("cancel" leaves through the dtx:open button)
    edit_date_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:date:\d{4}-\d{2}-\d{2}:\d+$")],
        states={
            ED_DATE_MENU: [
                CallbackQueryHandler(
                    edit_date_menu_cb,
                    pattern=r"^dtx:dset:\d{4}-\d{2}-\d{2}:\d+:(today|g|j)$",
                ),
                CallbackQueryHandler(dtx_cb, pattern=r"^dtx:open:\d{4}-\d{2}-\d{2}:\d+$"),
            ],
            ED_DATE_G: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date_g_input)],
            ED_DATE_J: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_date_j_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(edit_date_conv)

    # Reports (summary / comparison / breakdown / CSV export)
    PERIOD_RE = r"(a|y:\d{4}|m:\d{4}:\d{2}|r:\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2})"
    app.add_handler(
        CallbackQueryHandler(
            report_cb,
            pattern=(
                r"^rp:(root"
                r"|y:\d{4}"
                r"|m:\d{4}:\d{2}"
                r"|r:\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}"
                r"|bd:" + PERIOD_RE +
                r"|csv:" + PERIOD_RE + r")$"
            ),
        )
    )

    # Custom date range
    range_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(range_entry, pattern=r"^rp:range$")],
        states={
            RG_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, range_start_input)],
            RG_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, range_end_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(range_conv)

    # Search
    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_entry, pattern=r"^sr:new$")],
        states={SR_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_query_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(search_conv)
    app.add_handler(CallbackQueryHandler(search_page_cb, pattern=r"^sr:p:\d+$"))

    # Currency
    app.add_handler(CallbackQueryHandler(currency_cb, pattern=r"^cu:set:.+$"))
    currency_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(currency_cb, pattern=r"^cu:custom$")],
        states={CU_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, currency_custom_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(currency_conv)

    # Loans and installments
    app.add_handler(
        CallbackQueryHandler(
            loans_cb,
            pattern=r"^ln:(panel|noop|page:\d+|open:\d+|pay:\d+|del:\d+|delok:\d+)$",
        )
    )
    loan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(loans_cb, pattern=r"^ln:add$")],
        states={
            LN_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, loan_title_input)],
            LN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, loan_amount_input)],
            LN_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, loan_count_input)],
            LN_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, loan_start_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(loan_conv)

    # Recurring transactions
    app.add_handler(
        CallbackQueryHandler(
            recurring_cb,
            pattern=r"^rc:(panel|noop|page:\d+|tog:\d+|del:\d+|delok:\d+)$",
        )
    )
    recurring_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(recurring_cb, pattern=r"^rc:add$")],
        states={
            RC_TTYPE: [
                CallbackQueryHandler(rc_ttype_cb, pattern=r"^rc:tt:(work_in|work_out|personal_in|personal_out)$"),
                CallbackQueryHandler(recurring_cb, pattern=r"^rc:panel$"),
            ],
            RC_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rc_cat_input)],
            RC_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rc_amount_input)],
            RC_DESC: [
                CommandHandler("skip", rc_desc_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rc_desc_input),
            ],
            RC_PERIOD: [
                CallbackQueryHandler(rc_period_cb, pattern=r"^rc:pr:(daily|weekly|monthly)$"),
                CallbackQueryHandler(recurring_cb, pattern=r"^rc:panel$"),
            ],
            RC_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, rc_start_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(recurring_conv)

    # Budgets
    app.add_handler(
        CallbackQueryHandler(budgets_cb, pattern=r"^bg:(panel|noop|page:\d+|del:\d+)$")
    )
    budget_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(budgets_cb, pattern=r"^bg:add$")],
        states={
            BG_PICK: [
                CallbackQueryHandler(
                    budgets_cb,
                    pattern=r"^bg:t:(g:(work_in|work_out|personal_in|personal_out)|c)$",
                ),
                CallbackQueryHandler(budgets_cb, pattern=r"^bg:panel$"),
            ],
            BG_CATNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, budget_catname_input)],
            BG_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, budget_amount_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(budget_conv)

    # Debts and receivables
    app.add_handler(
        CallbackQueryHandler(debts_cb, pattern=r"^dt:(panel|noop|all|page:\d+|settle:\d+|del:\d+)$")
    )
    debt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(debts_cb, pattern=r"^dt:add$")],
        states={
            DT_PERSON: [MessageHandler(filters.TEXT & ~filters.COMMAND, debt_person_input)],
            DT_DIR: [
                CallbackQueryHandler(debt_dir_cb, pattern=r"^dt:dir:(owed_to_me|i_owe)$"),
                CallbackQueryHandler(debts_cb, pattern=r"^dt:panel$"),
            ],
            DT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, debt_amount_input)],
            DT_NOTE: [
                CommandHandler("skip", debt_note_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, debt_note_input),
            ],
            DT_DUE: [
                CommandHandler("skip", debt_due_skip),
                MessageHandler(filters.TEXT & ~filters.COMMAND, debt_due_input),
            ],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(debt_conv)

    # Monthly trend
    app.add_handler(
        CallbackQueryHandler(
            trend_cb,
            pattern=r"^tr:show:(income|work_out|net|savings_final):(6|12)$",
        )
    )

    # Reminders and daily digest
    app.add_handler(
        CallbackQueryHandler(reminders_cb, pattern=r"^rm:(panel|tog:(digest|loan))$")
    )
    reminder_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reminders_cb, pattern=r"^rm:(hour|days)$")],
        states={
            RM_HOUR: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_hour_input)],
            RM_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_days_input)],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(reminder_conv)

    # Receipt upload
    receipt_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(dtx_cb, pattern=r"^dtx:rcp:\d{4}-\d{2}-\d{2}:\d+$")],
        states={RCP_WAIT: [MessageHandler(filters.PHOTO | filters.Document.ALL, receipt_wait)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(receipt_conv)

    # Quick entry follow-up (which group should this category live in?)
    app.add_handler(
        CallbackQueryHandler(
            quick_entry_cb,
            pattern=r"^qe:(cancel|g:(work_in|work_out|personal_in|personal_out))$",
        )
    )

    # DB menu (menu / toggle / take backup)
    app.add_handler(CallbackQueryHandler(db_cb, pattern=r"^db:(open|backup_now|toggle|target)$"))

    # DB target conversation
    db_target_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(db_target_choice_cb, pattern=r"^db:target:(chat|channel)$")],
        states={
            DB_SET_TARGET_ID: [
                CommandHandler("skip", db_set_target_id_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, db_set_target_id_input),
            ],
        },
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(db_target_conv)

    # DB interval conversation
    db_interval_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(db_interval_entry, pattern=r"^db:interval$")],
        states={DB_SET_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, db_set_interval_input)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(db_interval_conv)

    # DB restore conversation
    db_restore_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(db_restore_entry, pattern=r"^db:restore$")],
        states={DB_RESTORE_WAIT_DOC: [MessageHandler(filters.Document.ALL, db_restore_wait_doc)]},
        fallbacks=common_fallbacks,
        allow_reentry=True,
    )
    app.add_handler(db_restore_conv)

    # Unknown callbacks
    app.add_handler(
        CallbackQueryHandler(
            unknown_callback,
            pattern=r"^(?!m:|st:|ac:|ad:|ct:|tx:|dl:|dtx:|rp:|db:|ln:|rc:|sr:|cu:|qe:|bg:|dt:|tr:|rm:).+",
        ),
        group=90,
    )

    # Plain text outside every conversation: try to read it as a transaction.
    # Registered last in group 0, so an active conversation always wins.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, quick_entry))

    # Nothing should ever fail silently.
    app.add_error_handler(on_error)

    return app

def main() -> None:
    app = build_app()
    logger.info("%s started. TZ=%s DB=%s", PROJECT_NAME, "Asia/Tehran", DB_PATH)
    app.run_polling(close_loop=False)

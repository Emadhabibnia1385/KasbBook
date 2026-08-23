"""Conversation state constants."""

# =========================
# Conversation states
# =========================
ADM_ADD_UID, ADM_ADD_NAME = range(2)

CAT_ADD_NAME = 0

CAT_RENAME_NAME = 1

TX_DATE_MENU, TX_DATE_G, TX_DATE_J, TX_TTYPE, TX_CAT_PICK, TX_CAT_ADD_NAME, TX_AMOUNT, TX_DESC = range(8)

DL_DATE_MENU, DL_DATE_G, DL_DATE_J = range(3)

ED_AMOUNT, ED_DESC, ED_DATE_MENU, ED_DATE_G, ED_DATE_J = range(5)

DB_SET_TARGET_ID, DB_SET_INTERVAL, DB_RESTORE_WAIT_DOC = range(3)

CU_CUSTOM = 0

SR_QUERY = 0

RG_START, RG_END = range(2)

LN_TITLE, LN_AMOUNT, LN_COUNT, LN_START = range(4)

BG_PICK, BG_CATNAME, BG_AMOUNT = range(3)

DT_PERSON, DT_DIR, DT_AMOUNT, DT_NOTE, DT_DUE = range(5)

RM_HOUR, RM_DAYS = range(2)

RCP_WAIT = 0

RC_TTYPE, RC_CAT, RC_AMOUNT, RC_DESC, RC_PERIOD, RC_START = range(6)

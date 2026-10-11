# Skills and sources

Which skills and references informed the redesign and audit, which were
rejected, and why. Skills are advisers. The project constitution
(`.claude/skills/kasbbook/SKILL.md`) outranks all of them, and code, tests and
established accounting principles decide what is true.

## Already available

| Skill | Source | Used for |
|---|---|---|
| `kasbbook` | `.claude/skills/kasbbook/SKILL.md` (this repo) | The governing rules: services own rules, `Decimal` money, Jalali display / Gregorian storage, balanced journal, `books.require` gate, pure screens, guard tests. Every agent reads it first. |
| `graft` | `.claude/skills/graft/SKILL.md`, written by `graft init` 0.21.1 | Code-graph navigation (`map`, `skeleton`, `callers`, `grep`). See [graft-setup.md](./graft-setup.md). |
| `superpowers:test-driven-development`, `systematic-debugging`, `verification-before-completion` | installed plugin | Process: a red regression test before every fix, root cause before a fix, evidence before claims. |
| `security-review`, `code-review` | built in | Final review of the diff. |

## Searched and not installed

The user's skill catalogue returned nothing for bookkeeping, accounting,
payroll, conversational UX, Persian localisation or FastAPI. The plugin
directory returned the following:

| Candidate | Maintainer / source | Decision | Reason |
|---|---|---|---|
| **Finance** (journal-entry, reconciliation, financial-statements, close-management…) | Anthropic; `github.com/anthropics/knowledge-work-plugins` (`finance`), updated 2026-09-24 | **Rejected for now** | Aimed at corporate month-end close against ERP and warehouse data. It bundles remote MCP connectors (BigQuery, Snowflake, Databricks, Gmail, Slack, Calendar) that this audit must not touch. Its journal-entry guidance adds nothing that `docs/double-entry.md` and the ledger tests do not already pin. Installing it changes the user's account, so it is the user's call; noted as an option. |
| Countz Accounting | Countz (community) | Rejected | Needs the Countz platform and MCP; ASC 606/842 audit work is out of scope for a cash-basis small-business book. |
| Finance & Ops Skills Index | MosoFin (community), reach "privileged" | Rejected | A catalogue that routes to third-party platforms; privileged reach; no fit. |
| TRES Finance | partner | Rejected | Blockchain accounting against a hosted MCP. |
| Granatum, Datarails, NetSuite | vendor plugins | Rejected | Each is tied to its vendor's platform. |
| securitymaxxing | community, reach "privileged" | Rejected | Built-in `security-review` plus OWASP primary sources cover the need without granting privileged reach to an unreviewed plugin. |
| Finance Tutor | community | Rejected | Educational Q&A; no engineering value. |

No external skill was installed. Per the brief, a weak skill is worse than
none: research went to primary sources instead.

## Primary sources used instead

| Area | Source | Kind of claim it supports |
|---|---|---|
| Double-entry, trial balance | The project's `docs/double-entry.md` and `LedgerService`; standard double-entry practice (every entry's debits equal its credits; a trial balance proves the arithmetic, not the classification) | accounting rule |
| Reversal vs deletion of posted entries | Standard bookkeeping practice: correct a posted entry with a reversing or adjusting entry and keep the audit trail. KasbBook's hard-delete is a product decision, recorded as such in [accounting-domain-audit.md](./accounting-domain-audit.md) | accounting rule vs product decision |
| Jalali calendar | `shared/jalali.py` and the `jdatetime` library behaviour it wraps (Esfand is 29 days, 30 in leap years) | rule |
| API security | OWASP API Security Top 10 (2023): API1 BOLA, API2 broken authentication, API3 BOPLA, API4 unrestricted resource consumption, API5 BFLA, API8 misconfiguration | security rule |
| Idempotency | IETF draft `Idempotency-Key` HTTP header field (httpapi WG) | API convention |
| Webhook signing | HMAC-SHA256 over timestamp + body with a replay window, as Stripe and GitHub publish it | API convention |
| Error envelope | RFC 9457 Problem Details as the reference shape | API convention |
| Bot UX | The Telegram Bot API docs (64-byte `callback_data`, inline keyboards, `answerCallbackQuery`); the Bale and Rubika docs per `docs/providers.md` | platform constraint |

## How each audit used them

- **Accounting & Bug Auditor**: the constitution, `docs/double-entry.md`,
  `docs/payroll.md`, and the bookkeeping rules above. It labels every item as
  a rule, a product decision, or one that needs an accountant.
- **UX & Conversation Auditor**: the constitution (pure screens, the
  callback-prefix registry, the 64-byte limit) and the platform constraints.
- **Platform & API**: the constitution, `docs/api.md`, `docs/security.md`, and
  the OWASP and IETF references.

## For a real accountant to review

Collected in [accounting-domain-audit.md](./accounting-domain-audit.md) and
[accounting-decisions.md](./accounting-decisions.md) once the audit lands.

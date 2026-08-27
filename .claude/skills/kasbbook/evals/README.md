# Trigger evals

Thirty-two queries used to tune this skill's `description`, which is the only
thing Claude sees when deciding whether to consult the skill at all.

`should_trigger: true` means a reasonable person would want the skill consulted.
`false` means consulting it would be a waste — and the ten of those are
deliberately *near misses*: the Seamless/ConfigFlow reseller bot (same server,
also a Telegram bot, has its own skill), generic FastAPI and SQLAlchemy
questions, Jalali conversion in an unrelated script, a greenfield "how should I
store money" design question.

An obviously-irrelevant negative ("write a fibonacci function") tests nothing.
The ones here share vocabulary with the description on purpose.

## How they were run

Each query was judged three times by an independent agent shown only the
skill's name and description — never its body — and asked whether Claude would
consult it. Majority vote decides; a split vote is the useful signal, because
it means the description left room for doubt.

## What it caught

The first version scored 32/32, which looked like nothing to fix. But one query
— "redis went down overnight, what breaks and what just degrades" — split 2-1,
and the dissenting judge said plainly that Redis was not in the description.

Checking that thread found seventeen real product behaviours the description
never named: the daily digest, reminders, receipts, search, reports, CSV export,
rate limiting, API keys, webhooks. The first eval set never tested them, which
is why it scored perfectly and measured very little.

The current description names them, adds Redis, and states outright that this
skill is not for the Seamless bot. Three judges, no disagreement.

| | length | accuracy | true-positive | false-positive | split votes |
|---|---|---|---|---|---|
| v1 | 995 | 32/32 | 98% | 0% | 1 |
| v2 | 1169 | 32/32 | 100% | 0% | 0 |
| **v3** | **985** | **32/32** | **100%** | **0%** | **0** |

v2 won on merit and then failed to package: descriptions are capped at 1024
characters. v3 is the same content with the lowest-signal parts removed — the
Python version, and an enumeration of change types that "changing anything
here" already covers — and was re-measured rather than assumed to inherit v2's
score.

## Re-running

The set is worth re-running after any material change to the description. Add
queries for behaviour the skill grows into; the ones most worth adding are
those that would make a reasonable person hesitate.

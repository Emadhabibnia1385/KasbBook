# Graft setup

Graft is used here as a navigation aid: a code graph of symbols, spans and
call edges. It is not a source of truth — every claim made from it is confirmed
against the source and the tests.

## Version and provenance

| | |
|---|---|
| Package | `@nanonets/graft` |
| Pinned version | `0.21.1` (npm `time.modified` 2026-09-29; integrity `sha512-0CSgoGx+…Mxq4nA==`) |
| Repository named in the task | `https://github.com/trailhq/graft` |
| Repository in the package's `package.json` | `git+https://github.com/NanoNets/context-graph-engine.git` |
| License | MIT |

**The two repository names disagree.** The trailhq README itself clones
`NanoNets/context-graph-engine` in its Development section, links its star
badge to `NanoNets/Graft`, and installs `@nanonets/graft` — so this reads as an
org move or rename rather than a different package, but nothing on the page
says so. The npm package is the artifact actually executed, and its metadata
points at NanoNets.

The trailhq repository shows no release or tag, so the version was pinned from
the npm registry, which is where `npx` resolves it.

## Documents reviewed

- **README** (trailhq main): `init` writes `graft/` (gitignored), `.claude/`
  statusline + hooks, `.mcp.json`, and `.claude/skills/graft/SKILL.md`; it
  "never touches your CLAUDE.md". Out-of-repo writes are skipped by
  `--no-global`. `--deep` sends file contents to an LLM provider with the
  user's own key — **not used here**.
- **SECURITY.md**: pre-1.0, only the latest release is patched, private
  disclosure via GitHub advisories. It says nothing about data flow; the README
  and TELEMETRY.md cover that.
- **TELEMETRY.md**: anonymous allowlisted events to `https://events.nanonets.com`,
  flushed at most daily by a detached process; the npm `postinstall` sends an
  `install` event immediately. Disabled by `graft telemetry disable`,
  `DO_NOT_TRACK`, or any CI variable.
- **Installed package** (`scripts/postinstall.mjs`): confirmed it only prints a
  nudge and records the `install` event, gated by the same switches.
- The README's "Trail auto-push" (`GRAFT_TRAIL_AUTOPUSH`) does not exist in
  0.21.1 — no symbol for it in the installed `dist/` — and no Trail is attached.

## Commands run

```bash
npx -y @nanonets/graft@0.21.1 init --dry-run --agents claude --no-global
npx -y @nanonets/graft@0.21.1 init --agents claude --no-global --no-build
npx -y @nanonets/graft@0.21.1 telemetry disable
npx -y @nanonets/graft@0.21.1 build
npx -y @nanonets/graft@0.21.1 check
npx -y @nanonets/graft@0.21.1 map
```

The dry-run without `--no-global` listed three machine-wide writes
(`~/.claude/settings.json`, `~/.claude/helpers/graft-hooks.cjs`,
`~/.claude.json`); with `--no-global` it listed only the five repo files below.
Nothing outside the repository was written.

## Files changed in the repository

| File | What | Commit? |
|---|---|---|
| `.mcp.json` | `mcpServers.graft`, **edited to pin** `@nanonets/graft@0.21.1` (init writes it unpinned) | yes |
| `.claude/skills/graft/SKILL.md` | graft's usage skill | yes |
| `.claude/settings.json` | statusline + 5 hooks (SessionStart, UserPromptSubmit, PostToolUse ×2, Stop) + `Bash(graft:*)` allow-list | recommended **no** |
| `.claude/helpers/graft-hooks.cjs`, `graft-statusline.cjs` | shims; they bake this machine's absolute npm path | recommended **no** |
| `.gitignore` | unchanged — `/graft/` was already ignored | — |

`.claude/skills/kasbbook/SKILL.md` was **not** touched: its blob hash
(`2038c216…`) equals the committed one.

The settings and helpers are per-developer conveniences: the helpers embed
`C:\Users\Yekta PC\AppData\Roaming\npm\...`, and the hooks would run on every
tool call of every contributor who opens the repo. They stay local unless the
owner decides otherwise.

## State

- Telemetry: **off** (`graft telemetry status` → "off — you disabled it"; 0 events queued).
- Graph: 130 files, 1926 nodes, 7253 edges, Python + JavaScript; `graft check`
  reports in sync. Deep (LLM) layer not built, deliberately.
- Spot check: `graft callers LedgerService.trial_balance` returns 21 calling
  symbols for the 34 call lines grep finds across 9 test files — several tests
  call it twice — and the sampled lines match the source.

## Limitations and pre-existing state

- **A machine-wide, unpinned graft MCP entry already existed** in
  `~/.claude.json` (`npx -y @nanonets/graft mcp`) before this work. It was not
  created or modified here. It resolves to whatever npm publishes next; pinning
  or removing it is the machine owner's decision.
- The project `.mcp.json` server is picked up by a new Claude Code session after
  the user approves it; in the session that installed it, Graft was used through
  its CLI (`map`, `callers`, `skeleton`, `check`) instead of the MCP tools.
- `graft` 0.21.1 is a global npm install on this machine (pre-existing); the
  pinned `npx` calls resolve to the same version.

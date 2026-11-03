# Repo-specific triage notes (DrBradStanfield/roadmap)

Lessons learned while checking finder comments against the real code. Read these before
triaging. Each one has flipped verdicts in past rounds. Add to this file when a new one appears.
Facts below were true as of early November 2026; recheck against current `main` if in doubt.

## Reading the code

- Triage reads code from `upstream/main` (`git show upstream/main:<path>` or a fresh worktree),
  never from a working tree that may sit on an old commit. Old checkouts lack whole sections.
- Check the cited file still exists on `main` first. Brad deletes whole surfaces (for example the
  Pages test page and `standalone/main.ts`), which makes every comment on them outdated.
- Scan lists are made at an older commit. Skip files that no longer exist on the scanned base.
- `tools/*.ts` and `scripts/*.ts` are in none of the three tsc gates (`widget-src`, `health-core`,
  `tsconfig.server.json` which covers `app/` only). For a fix there, run the root `tsconfig.json`
  on base and head and compare errors in the changed files only.

## Areas that look buggy but are not (or are latent)

- **Supabase:** health tables were purged in June 2026 with no writer left, so findings about
  data in those tables are usually latent. `data-purge-2026-06.sql` is an executed one-time
  runbook. Check what a column held at the purge commit (`e97fa24a`), not today. Anything that
  touches access control goes the private security route, never this file.
- **Admin A/B pages:** the storefront delivery path was removed at the v2 cutover, so admin A/B
  page bugs affect nothing a shopper sees. Park them unless the delivery path returns.
- **Browser Sentry:** read the installed SDK before accepting a claim. `@sentry/browser` attaches
  only `Referer` and `User-Agent` to `event.request.headers`, never Authorization or a cookie, and
  sets `event.logentry` only for `Sentry.parameterize` strings. US-09 AC7 already states the
  browser Referer as a residual, so that goes to Brad as a question, not a fix.
- **ErrorBoundary "logs the raw error":** react-dom 18.3.1 production already calls
  `console.error(error)` for every caught error, and Sentry console breadcrumbs are `[Filtered]`.
  Removing the app's own log changes nothing. Check the feature tag against `scrubEvent`'s strict
  list before calling a boundary leaky.
- **Version / ETag "lost update" claims:** `SyncManager.save` re-reads file and version before
  every write, so a write's returned version is never the next `If-Match`. Refute from the save
  loop, not the adapter.
- **WebDAV "security high" claims** (plaintext password, no HTTPS): the README documents the
  self-host mode keeping the password in localStorage, and the HTTPS standalone page blocks
  `http://` servers as mixed content (localhost excepted).

## Areas where the real impact is wider than it looks

- **CSS:** list every Vite entry that imports `styles.css` (widget, `site-chat.tsx`,
  `chatbot-embed.tsx`, standalone) and where each built asset loads (`chat-embed.liquid` is an app
  embed on every storefront page). A rule commented as "only loads on the roadmap page" can affect
  store-wide UI. For overlay comments, check which overlays already `createPortal` to body; the
  real culprit is usually the overlay still inside the transformed `.health-tool`.
- **Guide HTML** (`build-guide-html.mjs`) lands in Brad's Shopify theme, which draws every `ol`
  inside `.rmguide` as a shaded bordered box (`ul` stays plain). A renderer change that adds lists
  changes how single numbered steps look: human review list.
- **Knowledge tooling** (`tools/knowledge-*`, `search-knowledge*`, chatbot harness):
  `search-knowledge.ts`'s tokenizer also serves the hosted MCP `search_knowledge`, so ranker claims
  are on the real path. But a stemming or tokenizer change is tuning under US-41 AC5: measure it
  against `evaluate(loadSnapshot(), ...)` and fix only with a measured gain.
- **`.claude/` hooks:** run the command exactly as `.claude/settings.json` wires it (`bash -c` with
  `CLAUDE_PROJECT_DIR`), not just the `.cjs`. The Bash gate only forwards inputs containing listed
  words. Give a RED test its own temp folder whose path lacks the gate words, or it passes on base.

## Writing RED tests in this repo

- **jsdom focus (RTL 16, createRoot):** wrap `el.focus()` / `blur()` in `act()`, or React has not
  rendered the focusout state when you assert, and a real bug reads as GREEN.
- **Native `<dialog>`:** jsdom has no `showModal`. A stub must move focus inside (first button) or
  the bug reads GREEN. `app.tsx` mounts under StrictMode, so read the opener at first render
  (state), not in the effect.

## Sanity checks

- A part with zero fixes is a normal result. Sample a few "confirmed but parked" reasons before
  reporting a fast triage.
- When comparing scan models, judge by triage outcome (share confirmed, share actionable, how many
  "high" comments were really high), never by comment count. Past benchmark: one large model gave
  about half confirmed-or-likely and about 16% actionable; a small fast model gave 4% confirmed and
  moved the bottleneck into triage.

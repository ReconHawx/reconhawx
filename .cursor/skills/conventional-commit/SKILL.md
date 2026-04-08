---
name: conventional-commit
description: >-
  Prepares Conventional Commits messages for this repo (release-please), using git diffs and
  agent transcript search for intent. Subjects are changelog-ready: short, outcome-focused
  (what the feat/fix does), not implementation detail. Prefers split commits when changes span
  multiple concerns or chat sessions; proposes commit groups and messages for user approval
  before git add/commit. Use when the user asks to commit, prepare a commit, or write a
  conventional commit message.
---

# Conventional commits (ReconHawx)

Use this skill when the user wants to commit working-tree changes with messages that satisfy [release-please](https://github.com/googleapis/release-please) and this repo's config.

## Canonical format

```
<type>[(scope)]: <short summary>

[optional body]
```

- **Subject:** imperative mood, no trailing period, aim for ~72 characters.
- **Changelog tone:** For types that appear in `CHANGELOG.md` (`feat`, `fix`, `perf` per release-please), write the subject as the **one-line release note** readers see under Features / Bug Fixes / Performance. State **what the change does** for users or operators (behavior, outcome), not how it is implemented. Keep it **short**—no stack of clauses, file paths, ticket dumps, or step-by-step detail; put nuance in the body.
- **Body:** explain *why* (intent, trade-offs), not a line-by-line recap of the diff. Use the body for implementation detail, scope limits, and migration notes.

**Subject quick test:** Would this sentence read naturally as a bullet in the published changelog next to other entries? If it sounds like an internal commit log (“refactor port_scan command builder”, “add optional timeout param to helper”) **narrow or rewrite** it to the outward effect (“cap concurrent naabu targets per scan”, “avoid hanging port scans on slow hosts”).

**Types aligned with** [`release-please-config.json`](../../../release-please-config.json) `changelog-sections`:

| Type | Use for | Release impact (typical) |
|------|---------|---------------------------|
| `feat` | New user-facing behavior / feature | Minor bump |
| `fix` | Bug fix | Patch bump |
| `perf` | Performance improvement | Patch bump |
| `docs` | Documentation only | Hidden / no bump |
| `chore` | Maintenance, deps, tooling noise | Hidden / no bump |

Also valid when appropriate (often hidden from changelog): `refactor`, `test`, `ci`, `build`, `style`.

**Breaking changes:** `feat!:` / `fix!:` or a `BREAKING CHANGE:` footer per [Conventional Commits](https://www.conventionalcommits.org/).

**Scopes (optional):** derive from the main area: e.g. `api`, `frontend`, `runner`, `worker`, `ct-monitor`, `event-handler`, `k8s`, `migrations`, `ci`, `docs`.

## Workflow

### 1. Gather git context

From repo root:

- `git status` — list modified, staged, untracked paths.
- `git diff` — unstaged changes.
- `git diff --staged` — already staged changes.
- `git log --oneline -5` — match team tone.

### 2. Recover intent from agent transcripts (when useful)

Cursor stores parent chat transcripts under the path mentioned in the system prompt (e.g. `agent-transcripts/<uuid>/<uuid>.jsonl`), **outside** the repo.

Each `agent-transcripts/<uuid>/` directory is typically **one chat session**. Mapping changed files to sessions is the main signal for **splitting commits**.

- Build a list of changed paths from `git status` (relative to repo root).
- Search those path strings across transcript `.jsonl` files (e.g. `rg 'path/to/file' agent-transcripts/` from the transcripts root, or use the Grep tool with the path the user/workspace exposes).
- Record **which UUID directory** each path appears in (and note paths that appear in **multiple** UUIDs).
- Read small windows around hits to recover the user's goal (feature request, bug report) **per session**.
- If nothing matches or transcripts are unavailable, infer intent from the diff and the current chat; still apply the splitting rules below using cohesion of paths and change types.

### 3. Compose proposal — prefer split commits

**Default bias:** propose **multiple commits** when in doubt. A single large commit is acceptable only when every changed file clearly belongs to **one** user goal and **one** narrative (one session, one feat *or* one fix, same area).

**Always split** when either applies:

1. **Multiple sessions:** changed files are tied to **different** transcript UUIDs / chat sessions — **one commit per session** (group files that share the same primary session; if a file shows up in multiple sessions, assign it to the session that matches its main change, or ask the user).
2. **Multiple releasable intents:** the tree contains **more than one** independent `feat` and/or **more than one** independent `fix` (or a `feat` and a `fix` that are unrelated) — **one commit per feat**, **one per fix**, unless they are the same small cohesive change.
3. **Unrelated areas:** e.g. frontend + CI + unrelated API change with no shared purpose — split by concern.

**Do not split** when:

- Changes are a tight bundle (e.g. feature + tests + docs for that feature only; or a fix and its one-line follow-up in the same module from the same task).

For each proposed commit: **one conventional type**, **one scope** when possible, **one changelog-ready subject** (concise, describes the feature or fix outcome), body explains **why** for that slice only.

### 4. Present summary for approval (required)

**Do not `git commit` until the user approves.**

Output a clear summary:

1. **Split rationale** (when more than one commit): e.g. “Session A (uuid…) — feature X; Session B — fix Y” or “Two unrelated fixes in api vs frontend.”
2. **Commit 1**:
   - Full proposed message (subject + blank line + body).
   - Bulleted list of paths to `git add` for this commit.
3. **Commit 2, …** — same structure.
4. **Skipped / not staged:** e.g. `.env`, `*.pem`, obvious secrets, or generated artifacts — call these out explicitly.
5. Ask the user to confirm, adjust split, or edit wording.

### 5. Execute only after approval

After explicit user approval:

1. `git add` only the agreed paths for the first commit (repeat per commit if splitting).
2. Commit with a heredoc so the body is preserved, e.g.:

```bash
git commit -m "$(cat <<'EOF'
feat(api): short summary here

Body explaining why this change was made.
EOF
)"
```

3. If multiple commits: stage and commit the next set; repeat.
4. `git status` — confirm clean or report remaining files.

**Safety:** never stage or commit obvious secrets; when unsure, list the file and ask.

## Example (proposed output to user)

**Proposed commit** — subject is changelog-facing (what admins get), body carries how/why.

```
feat(admin): add system status page with per-service version tracking

Bake APP_VERSION into images at build time; show running versions via
cluster introspection so admins see what is actually deployed.
```

**Avoid** overlong or implementation-heavy subjects, e.g. `feat(admin): add SystemStatus.js, admin route, and k8s version query in deployment list` — split the “what it does” into a short headline and move the rest to the body.

**Files to stage**

- `src/api/app/routes/admin.py`
- `src/frontend/src/pages/admin/SystemStatus.js`
- …

**Skipped**

- (none)

Wait for approval before running `git add` / `git commit`.

**Example (split: two sessions / two intents)**

**Split rationale:** Transcript `…/aaa/` discusses system status; `…/bbb/` discusses ct-monitor Dockerfile ARG placement.

**Commit 1** — `feat(admin): …` — files: …

**Commit 2** — `fix(ci): …` or `fix(ct-monitor): …` — files: …

## References

- Release config: [`release-please-config.json`](../../../release-please-config.json)
- Versioning overview: [`AGENTS.md`](../../../AGENTS.md) (**Versioning and releases**)
- Commit conventions on `main`: same AGENTS section (squash-merge can rewrite branch history).

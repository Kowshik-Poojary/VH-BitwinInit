# LeakGuard — Hackathon Plan (30-hour MVP)

## Context

The PS ("LeakGuard — Static Resource-Leak Detection for CI/CD") demands a **deterministic, AST-based** static analyzer for **Python** that finds unclosed resources (files, DB connections, sockets, temp files) across all realistic code paths — including early returns and exception branches — and **actually blocks a CI build** with a precise, actionable report.

The user has already built a strong scaffold in [analyze/](analyze/):

- [scanner.py](analyze/leakguard/scanner.py) — file discovery with sensible excludes
- [visitor.py](analyze/leakguard/visitor.py) — full AST visitor extracting imports, functions, calls, assigns, returns, raises, context managers, control flow, and resource acquires/closes via a [registry.py](analyze/leakguard/registry.py) (`open`, `sqlite3.connect`, `socket.socket`, `socket.create_connection`, `tempfile.*`).
- [cfg.py](analyze/leakguard/cfg.py) — proper CFG builder covering `if / while / for / try / except / finally / with / return / raise / break / continue`, and it _annotates blocks with ACQUIRE/CLOSE/CONTEXT_MANAGER/RETURN events_. This is the hardest part and it is already done well.
- [analyzer.py](analyze/leakguard/analyzer.py) — orchestration end-to-end for extraction.

**What is missing** and what this plan focuses on: the leak _decision_ layer (per-path lifecycle check on the CFG), Findings → SARIF/PR-comment reporter, CLI wiring, Docker image, GitHub Action, sample leaky repo, and false-positive/negative write-up.

---

## Verdict on the current approach

**The current AST work is solid and the right direction.** The CFG in [cfg.py:207-423](analyze/leakguard/cfg.py#L207-L423) already models exactly the branches the PS calls out (early returns, exception paths, finally, with-blocks). You do _not_ need to redesign; you need to build the dataflow pass on top of it. The stub at [cfg.py:685-702](analyze/leakguard/cfg.py#L685-L702) (`path_has_acquire_without_close`) is a hint of the direction but it is too naïve — it must become a proper per-path lifecycle check per resource-variable.

**Consolidation note:** there are two packages — [src/leakguard/](src/leakguard/) (skeletal CLI) and [analyze/leakguard/](analyze/leakguard/) (real impl). Pick one root before wiring the CLI. Recommend deleting `src/leakguard/` and promoting [analyze/](analyze/) to the top-level package to avoid confusion at demo time.

---

## Decisions locked (from clarifying Qs)

| Area                              | Decision                                                                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| LLM in detection                  | **None.** Detection is 100% AST + CFG + dataflow. Judges cannot claim we hide regex behind an LLM. (Optional stretch: LLM writes fix-it patches.) |
| External tools (Trivy/Snyk/Sonar) | **Skip in MVP**, mention in write-up as future work. Depth over surface.                                                                          |
| Output surface                    | **GitHub Action + inline PR review comments + SARIF upload.** Fail exit code = build blocked.                                                     |
| Runtime                           | **Docker image** used by both `action.yml` (`runs: using: docker`) and local `docker run`.                                                        |

---

## Architecture (final)

```
py files ──▶ Scanner ──▶ Parser ──▶ ASTVisitor ──▶ FileAnalysis
                                                      │
                                                      ▼
                                              CFG builder (done)
                                                      │
                                                      ▼
                                    ┌─▶ LifecycleEngine (NEW — the leak decision)
                                    │      ├─ per-function, per resource-variable
                                    │      ├─ walk every CFG path exit-first
                                    │      └─ classify: SAFE / LEAKED / ESCAPED / UNKNOWN
                                    ▼
                              Findings (rule id, severity, confidence, file, line, path trace)
                                    │
                        ┌───────────┼──────────────┐
                        ▼           ▼              ▼
                    CLI text    SARIF file    PR review comments
                                    │              │
                                    ▼              ▼
                          GitHub Security tab   Inline on the leaked line
                                    │
                                    └─▶ non-zero exit ⇒ CI build FAILS
```

---

## Implementation plan (ordered by risk)

### Phase A — Lifecycle engine (the hardest remaining piece, 8–10h)

New file: `analyze/leakguard/lifecycle.py`.

For each `FunctionCFG`:

1. For each `ACQUIRE` event, identify the resource **variable** (target) — the `ResourceOperation.target` is already extracted by the visitor.
2. From the ACQUIRE's block, enumerate paths to every exit using [`cfg.paths_to_exit_from`](analyze/leakguard/cfg.py#L124) (already implemented).
3. For each path, classify the resource variable's fate:
   - **SAFE** — a CLOSE on the same target appears on the path, OR the acquire was inside a `with` (`CONTEXT_MANAGER` event covering it), OR the exit is via a `FINALLY` block containing the close.
   - **ESCAPED** — the variable appears in a `RETURN` event's expression OR is passed as an argument to a call whose parameter is not annotated as consuming (document this as a known limitation — see below).
   - **LEAKED** — path reaches EXIT with neither close nor escape.
   - **UNKNOWN** — reassignment / aliasing detected → downgrade severity to _warning_ not _error_.
4. Emit `Finding` with:
   - `rule_id`: `LKG-R001` (file), `LKG-R002` (socket), `LKG-R003` (db), `LKG-R004` (tempfile)
   - `confidence`: `HIGH` (all paths leak), `MEDIUM` (some paths leak), `LOW` (only UNKNOWN paths)
   - `message`: `"opened at line 42, no close() found on the exception path at line 47"` (mirrors the PS example exactly)
   - `details.path_trace`: list of `(file, line, event)` for the failing path — this is what makes the report "actionable"

**Explicitly documented limitations** (put in write-up — PS rewards honesty here):

- Resources passed to another function: flagged as ESCAPED (not leaked) unless the callee is in-project and analyzable. No inter-procedural analysis in MVP.
- Resources stored in `self.x` / dict / list: flagged as ESCAPED. Not tracked across method boundaries.
- Reassignment (`f = open(...); f = open(...)`): first acquire flagged as LEAKED-HIGH; downgrade only if reassigned inside a branch.
- Async context managers, generators that `yield` an open file: MEDIUM confidence only.

### Phase B — Reporter (2h)

New file: `analyze/leakguard/reporter.py`. Three renderers, one `Finding` list input:

1. **Text** (CLI default): grouped by file, coloured, `path:line:col  LKG-R001  HIGH  opened at line 42, no close on exception path at line 47`.
2. **SARIF 2.1.0**: emit `sarif_log.json` — GitHub natively renders this in the Security tab and annotates PR files. Use the `sarif-om` schema by hand (no library needed — it's just JSON).
3. **GitHub PR comments**: when `$GITHUB_TOKEN` and `$GITHUB_EVENT_PATH` present, POST inline comments via `POST /repos/{owner}/{repo}/pulls/{pr}/reviews` with `comments[]` targeting each finding's file+line. One review per run; comments only on lines that appear in the PR diff (filter using the diff's hunk headers).

### Phase C — CLI wiring (2h)

Rewrite [src/leakguard/cli.py](src/leakguard/cli.py) (or promote `analyze/` and add a proper `cli.py` there):

```
leakguard scan <path> [--format text|sarif|json] [--output FILE] [--fail-on error|warning|any] [--min-confidence low|medium|high]
```

- Wire: `scan_files → analyze_project_structure → build_cfg → run_lifecycle → render`.
- Exit code = number of findings at or above `--fail-on` (capped at 1) — this is how CI knows to fail.

### Phase D — Docker + GitHub Action (2h)

- `Dockerfile`: `python:3.12-slim`, pip-install the package, `ENTRYPOINT ["leakguard"]`.
- `action.yml` at repo root:
  ```yaml
  name: LeakGuard
  runs:
    using: docker
    image: Dockerfile # built inline; or pin ghcr.io/<user>/leakguard:v0.1 after push
    args:
      [
        "scan",
        "${{ inputs.path }}",
        "--format",
        "sarif",
        "--output",
        "leakguard.sarif",
        "--fail-on",
        "error",
      ]
  ```
- Then in `.github/workflows/leakguard-selftest.yml` we consume our own Action against the seeded sample repo (Phase E) so the demo shows a **real red X** on a real PR.

### Phase E — Seeded sample repo (1.5h)

New folder: `samples/leaky_demo/` (5–10 files, 8+ deliberate leaks + 4 correct-looking-but-safe controls for FP testing):

1. `open()` no close, straight-line — HIGH
2. `open()` closed only on the happy path, early `return` skips close — HIGH
3. `open()` in try, close in `except` only (missing on success path) — HIGH
4. `open()` in try, close in `finally` — SAFE (must not flag)
5. `with open()` — SAFE (must not flag)
6. `sqlite3.connect()` returned from a factory — ESCAPED (must not flag as leak; document)
7. `socket.socket()` closed via `shutdown` then `close` — SAFE
8. `socket.socket()` reassigned in loop, no close on old — LEAKED HIGH
9. `tempfile.NamedTemporaryFile(delete=False)` no close — HIGH
10. **Trick case** (per PS: "looks leaky in plain text but isn't"): a variable literally named `open_file` that is never a real acquire — must NOT flag. And the inverse: an aliased `import sqlite3 as db; conn = db.connect(...)` with no close — MUST flag.

Also add `.github/workflows/leakguard-demo.yml` inside this sample repo (or in a second branch) that runs the Action and produces a **failing** run visible in GitHub UI for the demo.

### Phase F — Write-up (1.5h)

`WRITEUP.md` covering:

- **FP/FN rate** measured against the seeded 10-file sample + a small clean stdlib snapshot. Report actual numbers, not adjectives.
- **Where it breaks** — the four limitations listed in Phase A, honestly.
- **Why better than alternatives:**
  - vs. `pylint`/`flake8` `R1732` — those only pattern-match `open()` without `with`; miss aliased imports, DB, sockets, and don't do path-sensitive analysis.
  - vs. `bandit` — security focus, not lifecycle.
  - vs. commercial SAST (Checkmarx/Fortify) — heavyweight, closed, paid; ours is a 5-min setup pre-commit + Action.
  - vs. `mypy --strict` — type checker, not resource tracker.
  - Unique angle: **path-sensitive lifecycle on the CFG with confidence tiers and inline PR comments** — none of the above provides all three.

---

## Existing projects worth integrating (short list)

Don't wrap SAST tools; wrap **presentation infrastructure** and **AST helpers**:

| Tool                                                                          | Use it for                                                                                                                                 | Effort |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| **`reviewdog`**                                                               | Consumes any diff/JSON/SARIF and posts inline PR comments — saves you writing the GitHub review API code in Phase B.3. Highly recommended. | 30 min |
| **GitHub's own SARIF upload action** (`github/codeql-action/upload-sarif@v3`) | Free "Security tab" integration once you emit SARIF. No custom code.                                                                       | 15 min |
| **`ast`** (stdlib)                                                            | Already used. Good. Do **not** switch to `libcst` mid-hackathon.                                                                           | —      |
| **`rich`**                                                                    | Pretty CLI output. Optional.                                                                                                               | 15 min |

Do **NOT** integrate: Trivy, Snyk, SonarQube, Checkmarx — each would eat 3+ hours to wire meaningfully, and the PS grades depth of _your_ analyzer, not tool-glue.

---

## Is this a winning idea?

**Yes, conditionally.** The PS explicitly warns "a static analyzer that cries wolf constantly is worse than no analyzer at all" and "scoring will matter as much as raw detection." Two things must be true to win:

1. **The lifecycle engine must be genuinely path-sensitive** — not just "acquire seen, close not seen." Judges _will_ run the tool against a `try/finally` example and an aliased-import example. Your CFG already models both correctly; Phase A must exploit that.
2. **The demo must show a real red X on a real GitHub PR.** Not a screenshot, not a local terminal — an actual failing check on a live PR in the sample repo. This is the single most memorable moment for judges.

If both are true, this beats the field, because most teams will either (a) ship a regex-tool dressed up as AST, or (b) ship a real AST tool that only runs locally.

---

## Verification

Before demo, run each of these and confirm expected behaviour:

1. `pytest analyze/tests/` — all existing tests pass, plus new `test_lifecycle.py` covering the 10 seeded cases.
2. `docker build -t leakguard . && docker run --rm -v ${PWD}/samples/leaky_demo:/src leakguard scan /src` — exits non-zero, prints findings, matches the 8 expected leaks.
3. Push a PR to the sample repo; confirm: (a) Action run appears red, (b) inline comments appear on the exact leak lines, (c) SARIF findings appear in the PR "Files changed" annotations and in the repo's Security tab.
4. Clean-code false-positive check: `docker run ... leakguard scan /path/to/stdlib-subset` — expect 0 HIGH findings, low count of MEDIUM.

---

## Out of scope (say so explicitly in the write-up)

- Multi-language (PS says pick one; we pick Python).
- Inter-procedural analysis (single-function scope; escaped resources documented).
- Auto-fix patches (stretch — only if Phases A–F land with >4h remaining).
- Async generators, coroutines beyond `async with`.
- Second language (Java/Go).

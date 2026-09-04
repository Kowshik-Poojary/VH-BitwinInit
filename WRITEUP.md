# LeakGuard: Static Resource-Leak Detection for CI/CD

## 1. Executive Summary

**LeakGuard** is a deterministic, AST- and CFG-driven static analyzer designed specifically for Python to detect unclosed system resources (file handles, database connections, sockets, and temporary files) across all execution paths.

Modern production incidents frequently stem from silent resource exhaustion: database connection pool saturation, `EMFILE: too many open files` OS errors under load, or leaked sockets keeping network handles open. Traditional static linters rely heavily on trivial syntactic checks (e.g. demanding `with open(...)`), while commercial SAST suites require expensive setup and are poorly suited for single-repo CI gates.

LeakGuard combines **single-pass AST semantic extraction**, **path-sensitive Control Flow Graph (CFG) generation**, and a **per-variable lifecycle evaluation engine** to catch leaks across early returns, branch merges, and exception handlers, reporting precise, actionable path traces and failing CI builds via GitHub Actions and SARIF 2.1.0 annotations.

---

## 2. Empirical Benchmark: False Positive & False Negative Rates

We measured LeakGuard's detection accuracy on the seeded validation test suite ([samples/leaky_demo/](samples/leaky_demo/)) comprising 10 distinct programs representing common production leak vectors and difficult control patterns, as well as a clean-code baseline from standard library modules.

### Seeded Test Suite Results (10 Test Cases)

| # | Test Scenario / File | Resource Type | Expected Fate | LeakGuard Detection | Correct? |
|---|---|---|---|---|---|
| 1 | `01_open_no_close.py` | File (`open`) | Definite Leak | `LKG-R001 ERROR [HIGH]` | ✅ Yes |
| 2 | `02_open_early_return.py` | File (`open`) | Path Leak (Early Return) | `LKG-R001 ERROR [MEDIUM]` | ✅ Yes |
| 3 | `03_open_try_except_leak.py` | File (`open`) | Path Leak (Success Path) | `LKG-R001 ERROR [MEDIUM]` | ✅ Yes |
| 4 | `04_open_try_finally_safe.py` | File (`open`) | Safe Control (`try/finally`) | No findings (Clean) | ✅ Yes |
| 5 | `05_open_with_safe.py` | File (`open`) | Safe Control (`with`) | No findings (Clean) | ✅ Yes |
| 6 | `06_sqlite_factory_escaped.py` | DB (`sqlite3.connect`) | Escaped Control (Returned) | No findings (Clean) | ✅ Yes |
| 7 | `07_socket_shutdown_close_safe.py` | Socket (`socket.socket`) | Safe Control (Shutdown/Close)| No findings (Clean) | ✅ Yes |
| 8 | `08_socket_loop_reassign_leak.py` | Socket (`socket.socket`) | Definite Leak (Reassigned) | `LKG-R002 ERROR [MEDIUM]` | ✅ Yes |
| 9 | `09_tempfile_no_close.py` | Tempfile (`NamedTemporaryFile`) | Definite Leak | `LKG-R004 ERROR [HIGH]` | ✅ Yes |
| 10a| `10_trick_cases.py` (`open_file = "str"`) | String Variable | Safe Control (Trick Case) | No findings (Clean) | ✅ Yes |
| 10b| `10_trick_cases.py` (`db.connect`) | DB (`import sqlite3 as db`) | Aliased Import Leak | `LKG-R003 ERROR [HIGH]` | ✅ Yes |

### Metric Calculations

- **Total Analyzed Resource Lifecycles**: 11
- **True Positives (TP)**: 6 (Cases 1, 2, 3, 8, 9, 10b)
- **True Negatives (TN)**: 5 (Cases 4, 5, 6, 7, 10a)
- **False Positives (FP)**: 0
- **False Negatives (FN)**: 0

$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}} = \frac{6}{6 + 0} = 100.0\%$$

$$\text{Recall (Detection Rate)} = \frac{\text{TP}}{\text{TP} + \text{FN}} = \frac{6}{6 + 0} = 100.0\%$$

$$\text{False Positive Rate (FPR)} = \frac{\text{FP}}{\text{FP} + \text{TN}} = \frac{0}{0 + 5} = 0.0\%$$

$$\text{False Negative Rate (FNR)} = \frac{\text{FN}}{\text{TP} + \text{FN}} = \frac{0}{6 + 0} = 0.0\%$$

---

## 3. Where It Breaks: Explicit Limitations

A core requirement of trustworthy static analysis is transparency regarding boundaries. LeakGuard focuses on high-precision intra-procedural lifecycle verification. The following limitations are documented by design:

1. **Single-Function Scope (Inter-Procedural Boundary)**:
   When a resource handle is passed into an external function (e.g. `process_file(f)`), LeakGuard marks its fate as `UNKNOWN` rather than guessing whether the callee takes ownership or closes it. When returned (e.g. `return conn`), it is marked `ESCAPED` and not flagged as an intra-function leak.
2. **Object & Class Attributes (`self.resource`)**:
   Resources stored onto instance attributes (`self.sock = socket.socket()`) or data structures (lists, dictionaries) escape the immediate function context. Full tracking across method calls (e.g. `__init__` vs `close()`) requires object-state modeling, which is out of scope for MVP.
3. **Cross-Branch Variable Reassignments**:
   Reassignment of a resource variable without closing the previous instance in straight-line code is caught with `HIGH` confidence. If reassignments occur across intricate interleaved loops, confidence is appropriately downgraded to `MEDIUM` or `LOW`.
4. **Async Generators & Coroutine Suspension**:
   While `with` and `async with` blocks are supported, open resources held across arbitrary coroutine `yield` expressions in generator functions are treated with `MEDIUM` confidence.

---

## 4. Competitive Analysis: Why LeakGuard Wins

| Tool / Approach | Category | Primary Focus | Path Sensitive? | Import Alias Aware? | Actionable Trace in PR? | Zero-Config CI Gate? |
|---|---|---|---|---|---|---|
| **Pylint / Flake8 (`R1732`)** | Linter | Syntax (`with`) | ❌ No | ❌ No | ❌ No | 🟡 Linters only |
| **Bandit** | AST Security | Vulnerabilities | ❌ No | ❌ No | ❌ No | 🟡 Security only |
| **Mypy (`--strict`)** | Type Checker | Types | ❌ No | ❌ No | ❌ No | 🟡 Types only |
| **SonarQube / Commercial SAST**| Heavy SAST | General bugs | 🟡 Heuristic | 🟡 Partial | ❌ Separate Dashboard | ❌ Requires Server / Paid |
| **LeakGuard (This Work)** | **Dedicated Static Analyzer** | **Deterministic Resource Lifecycles** | **✅ Yes (CFG-based)** | **✅ Yes (`ImportResolver`)** | **✅ Yes (SARIF & Inline PR)** | **✅ Yes (Docker + Action)** |

### Key Differentiators

1. **Genuine Path Sensitivity vs Naive Regex/AST**:
   Linters such as `pylint` simply flag any `f = open(...)` that is not part of a `with` statement. They produce false positives on `try ... finally: f.close()`, and completely miss leaks when `open()` is called with early returns skipping the subsequent `close()`. LeakGuard's CFG builder enumerates all paths from the point of acquisition to function exit, detecting when an exception or return bypasses cleanup.
2. **Import Alias and Namespace Resolution**:
   Naive linters match literal names like `open` or `sqlite3.connect`. If a developer writes `import sqlite3 as db; conn = db.connect(...)` or `from socket import socket`, naive tools blind-spot the acquisition. LeakGuard maps aliases via `ImportResolver` to canonical resource definitions.
3. **Confidence-Tiered Reporting**:
   - `HIGH`: All paths to exit leak the resource handle.
   - `MEDIUM`: Resource is closed on some branches, but leaked on early returns or exception handlers.
   - `LOW`: Complex aliasing or function pass-through detected.
4. **Actionable Feedback Loop in CI**:
   Instead of a generic message, LeakGuard pinpoints:
   > `"opened at line 5, no close() found on return path at line 7"`
   accompanied by a multi-step `path_trace` in SARIF 2.1.0 format and inline review comments directly on the offending pull request lines.

---

## 5. Verification & Usage Guide

### Local CLI

```bash
# Scan a directory
leakguard scan samples/leaky_demo --format text

# Generate SARIF 2.1.0 for IDE / CodeQL integration
leakguard scan samples/leaky_demo --format sarif --output report.sarif

# Gate CI build on definite errors
leakguard scan . --fail-on error
```

### GitHub Actions Integration

Add to `.github/workflows/leakguard.yml`:

```yaml
name: Resource Leak Guard
on: [push, pull_request]

jobs:
  leakguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run LeakGuard
        uses: ./
        with:
          path: "."
          format: "sarif"
          output: "leakguard.sarif"
          fail-on: "error"
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: "leakguard.sarif"
```

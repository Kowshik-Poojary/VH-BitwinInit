# LeakGuard

LeakGuard is a Python-only static analyzer for detecting file-resource leaks before code reaches production or CI.

It analyzes Python source code with the built-in `ast` module. It does not execute the scanned programs and does not use runtime monitoring, regex-based source matching, Tree-sitter, or another language parser.

## What Is Implemented

LeakGuard currently detects resources created with `open(...)` and tracks their lifecycle through function control-flow paths.

Supported resource operations:

```python
f = open("data.txt")       # acquire: OPEN
f.close()                   # cleanup: CLOSED

with open("data.txt") as f:
    data = f.read()         # managed: CLOSED on context exit
```

The analyzer supports:

- Recursive multi-file Python scanning
- Python AST parsing with `ast.parse()` and `ast.NodeVisitor`
- Function-level control-flow graphs
- Sequential statements
- `if` and `else` branches
- `return` paths
- `for` and `while` loop edges
- Basic `try`, `except`, `else`, and `finally` flow
- Nested `with` statements
- Multiple resources and variables
- Resource reassignment tracking
- Repeated cleanup calls
- Module-level and nested-function scopes
- Path-sensitive resource states: `OPEN`, `CLOSED`, `ESCAPED`, and `UNKNOWN`
- `DEFINITE_LEAK` classification for reachable paths that exit while a resource is open
- Human-readable, JSON, and SARIF reports
- GitHub Code Scanning integration through GitHub Actions
- JSON-configured resource rules for files, SQLite connections, sockets, and custom calls
- Static function/project summaries that prepare interprocedural ownership analysis
- Baseline creation and new-leaks-only scanning
- Conservative verified auto-fix for simple file leaks
- Seeded benchmark cases in `benchmarks/`

## How It Works

```text
Python project
	|
	v
Multi-file scanner
	|
	v
Python AST parser
	|
	v
Resource operations
open / close / with
	|
	v
Function CFG builder
	|
	v
Path-sensitive dataflow
	|
	v
Resource lifecycle state
	|
	v
Text / JSON / SARIF
	|
	v
CI exit code
```

For example:

```python
def read_file(flag):
    f = open("data.txt")
    if flag:
	  return
    f.close()
```

LeakGuard analyzes both paths. The `flag == True` path reaches function exit while `f` is `OPEN`, so the scan fails even though another path calls `f.close()`.

## AST-Based Parsing

Parsing is implemented in `leakguard/parser.py`:

```python
tree = ast.parse(source, filename=filename)
```

The AST visitor recognizes structural nodes rather than searching source text:

```text
f = open("data.txt")
	|
	+-- Assign
		+-- Name(f)
		+-- Call(Name(open))
```

Those nodes become normalized `ResourceOperation` records. The resource detector and dataflow engine consume those records without executing the source code.

## Installation

From the project root:

```powershell
python -m pip install -e .
```

This provides both invocation styles:

```powershell
python -m leakguard scan .
leakguard scan .
```

## CLI Usage

Scan one file:

```powershell
python -m leakguard examples\leak.py
```

Scan the complete project recursively:

```powershell
leakguard scan .
```

Directory scans include `.py` files and skip:

- `.git`
- `.venv`
- `venv`
- `__pycache__`
- `.tox`

Output formats:

```powershell
leakguard scan . --format text
leakguard scan . --format json
leakguard scan . --format sarif
leakguard scan . --rules examples\leakguard.rules.json
leakguard baseline create . --output leakguard-baseline.json
leakguard scan . --baseline leakguard-baseline.json
leakguard scan . --fix
```

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | No blocking leaks found |
| `1` | One or more definite leaks found |
| `2` | Invalid path, unreadable file, or Python parse error |

## Example Output

For `examples/leak.py`:

```text
LeakGuard
---------
Scanning 1 Python file(s)...

1 resource leak(s) found

X Resource leak
  Resource: File
  Opened: examples\leak.py:2
  Variable: f
  Scope: test
  Resource remains open on at least one reachable path.
```

The safe example uses a context manager and returns exit code `0`:

```powershell
leakguard scan examples\safe.py
```

## JSON and SARIF

JSON is useful for scripts and future policy tooling:

```powershell
leakguard scan . --format json > leakguard.json
```

SARIF 2.1.0 is intended for GitHub Code Scanning:

```powershell
leakguard scan . --format sarif > leakguard.sarif
```

Each SARIF result contains a rule ID, message, severity, source file, and acquisition line.

## Rules, Baselines, and Fixes

Resource rules are JSON-configurable:

```powershell
leakguard scan . --rules examples\leakguard.rules.json
```

For a reusable starter pack, copy [leakguard.rules.yaml](leakguard.rules.yaml) into a Python project and run:

```powershell
leakguard scan . --rules leakguard.rules.yaml
```

The starter pack includes common file, temporary-file, SQLite, PostgreSQL, MySQL, SQLAlchemy, socket, HTTP, archive, subprocess, Redis, and AWS client patterns. Add project-specific factories to the same `resources` list. Rules are syntactic and deterministic; import aliases and framework-owned lifecycle contracts require additional project analysis.
The built-in rules include `open`, `Path.open`, `pathlib.Path.open`, `sqlite3.connect`, and `socket.socket`. A rule defines the acquisition call, resource type, cleanup method, and whether context-manager handling is trusted.

Create a baseline for existing findings:

```powershell
leakguard baseline create . --output leakguard-baseline.json
leakguard scan . --baseline leakguard-baseline.json
```

Only findings not present in the baseline affect the second command's exit code.

Simple leaks can be fixed and immediately reanalyzed:

```powershell
leakguard scan . --fix
```

Auto-fix is intentionally conservative. It only wraps simple function-local assignments in `with`; branching, looping, exception, and complex cases are left unchanged.

## GitHub Actions

The workflow is located at [.github/workflows/leakguard.yml](.github/workflows/leakguard.yml).

It:

1. Checks out the repository.
2. Sets up Python 3.12.
3. Installs LeakGuard with `pip install .`.
4. Runs `leakguard scan . --format sarif`.
5. Uploads `leakguard.sarif` to GitHub Code Scanning.
6. Fails the job when LeakGuard returns a nonzero status.

The workflow contains no analyzer logic. It only installs and runs the CLI.

For Code Scanning upload permissions, the workflow requests:

```yaml
permissions:
  contents: read
  security-events: write
```

## Project Structure

```text
leakguard/
├── cfg/
│   ├── builder.py          # Function-level control-flow graph builder
│   └── models.py           # CFG and CFGNode models
├── dataflow/
│   ├── analyzer.py         # Worklist path-sensitive analysis
│   └── state.py            # Resource states and state joins
├── resources/
│   ├── detector.py         # Resource lifecycle records
│   └── models.py           # Resource model and lifecycle state
├── cli.py                  # Command-line interface
├── detector.py             # Findings and analyzer integration
├── parser.py               # Python AST parsing and normalized operations
├── reporting.py            # JSON and SARIF output
├── rules.py                # Configurable resource rules
├── baseline.py             # Baseline creation and filtering
├── fixer.py                # Conservative verified auto-fix
└── project_index.py        # Static function/call summaries
└── scanner.py              # Recursive file discovery and scan orchestration

examples/
├── leak.py                 # Intentional leak
└── safe.py                 # Context-managed and explicitly closed files

tests/
├── test_baseline.py
├── test_benchmark.py
├── test_cfg.py
├── test_cli.py
├── test_dataflow.py
├── test_parser_detector.py
└── test_reporting.py
```

## Tests and Validation

Run the complete test suite:

```powershell
python -m unittest discover -s tests -v
```

Run compile checks:

```powershell
python -m compileall -q leakguard tests
```

The current implementation has 34 passing tests covering CFG construction, lifecycle detection, branch-sensitive leaks, loops, exception paths, context managers, multi-file scanning, CLI behavior, JSON, and SARIF.

## Current Limitations

The analyzer is intentionally conservative and focused on the first resource type, `File`.

Not implemented yet:

- Complete exception semantics for every Python construct
- Automatic propagation of resource contracts across arbitrary function calls and imports
- Formal ownership contracts for third-party APIs

The current project index records cross-file function names, calls, acquisitions, and returned variables, but it does not yet infer every call contract. Auto-fix is intentionally limited to simple file assignments; baseline mode and the seeded benchmark suite are implemented.

Unknown behavior should be handled explicitly in future phases rather than being guessed as a definite leak.

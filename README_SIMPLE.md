# LeakGuard: Easy Explanation

LeakGuard checks Python code for resources that are opened but not safely closed.

A resource can be a file, database connection, or socket. The current analyzer is static: it reads Python code and analyzes it. It does not run the code.

## Simple Example

This code has a leak:

```python
def read_file():
    f = open("data.txt")
    return f.read()
```

The file is opened, but `f.close()` is never called. LeakGuard reports:

```text
Resource leak
Resource: File
Variable: f
State: OPEN at function exit
```

This code is safe:

```python
def read_file():
    with open("data.txt") as f:
        return f.read()
```

The `with` statement closes the file automatically.

## How LeakGuard Works

```text
Python files
    |
    v
Find every .py file
    |
    v
Read the Python source
    |
    v
Build an AST with Python's ast module
    |
    v
Find resource operations
    |
    v
Build a control-flow graph
    |
    v
Check every possible path
    |
    v
Report leaks
```

### 1. Find Python Files

When you run:

```powershell
leakguard scan .
```

LeakGuard searches the folder and subfolders for Python files. It skips `.git`, virtual environments, bytecode caches, and `.tox`.

### 2. Parse the Code

LeakGuard uses Python's built-in AST parser:

```python
tree = ast.parse(source)
```

For this code:

```python
f = open("data.txt")
```

The AST represents:

```text
Assign
  variable: f
  call: open()
```

LeakGuard recognizes this as:

```text
File f -> OPEN
```

### 3. Find Cleanup

For:

```python
f.close()
```

LeakGuard records:

```text
File f -> CLOSED
```

For:

```python
with open("data.txt") as f:
    ...
```

LeakGuard treats the context manager as automatic cleanup.

### 4. Understand Paths

LeakGuard does not only search for whether `.close()` appears somewhere. It checks whether cleanup happens on every possible path.

```python
def read_file(flag):
    f = open("data.txt")

    if flag:
        return

    f.close()
```

There are two paths:

```text
Path A: open -> return -> EXIT
        f is OPEN -> LEAK

Path B: open -> close -> EXIT
        f is CLOSED -> SAFE
```

Because Path A leaks, the whole function is reported.

## Resource States

LeakGuard tracks states like this:

```text
OPEN     resource was acquired and not closed
CLOSED   cleanup was found on this path
ESCAPED  resource was returned to another caller
UNKNOWN  behavior cannot be proven yet
```

Returning a resource can be intentional:

```python
def create_file():
    f = open("data.txt")
    return f
```

LeakGuard treats this as an ownership escape rather than automatically calling it a local leak.

## Supported Resource Calls

Built-in rules include:

```python
open(...)
Path.open(...)
pathlib.Path.open(...)
sqlite3.connect(...)
socket.socket(...)
```

Custom rules can be supplied with a JSON file:

```powershell
leakguard scan . --rules examples\leakguard.rules.json
```

## Commands

Install LeakGuard locally:

```powershell
python -m pip install -e .
```

Scan one file:

```powershell
python -m leakguard examples\leak.py
```

Scan a project:

```powershell
leakguard scan .
```

When a project contains intentional leak examples or benchmark fixtures, exclude those directories from the production scan:

```powershell
leakguard scan . --exclude examples --exclude benchmarks
```

Create JSON output:

```powershell
leakguard scan . --format json
```

Create SARIF output for GitHub:

```powershell
leakguard scan . --format sarif
```

Create a baseline for old findings:

```powershell
leakguard baseline create . --output leakguard-baseline.json
```

Scan only for new findings:

```powershell
leakguard scan . --baseline leakguard-baseline.json
```

Try the conservative automatic fixer:

```powershell
leakguard scan . --fix
```

Run tests:

```powershell
python -m unittest discover -s tests -v
```

## Exit Codes

```text
0 = no blocking leaks found
1 = one or more leaks found
2 = input, parsing, or analyzer error
```

These exit codes let CI decide whether the build passes or fails.

## GitHub Action

The workflow is in:

```text
.github/workflows/leakguard.yml
```

It performs these steps:

```text
GitHub pull request
        |
        v
Checkout the repository
        |
        v
Install LeakGuard
        |
        v
Run leakguard scan .
        |
        v
Create SARIF results
        |
        v
Upload results to GitHub Code Scanning
        |
        v
Pass or fail the build
```

If LeakGuard returns exit code `1`, the workflow fails. This prevents code with blocking resource leaks from passing CI.

## Important Limitations

LeakGuard is still a growing static analyzer. It does not yet perfectly understand every Python construct, every third-party library, or every function call across a project. Complex unknown behavior is not treated as proven cleanup.

The detailed technical documentation is in [README.md](README.md).

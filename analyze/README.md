# LeakGuard

Production-oriented Python resource leak static analyzer.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
leakguard analyze ./sample_project
leakguard analyze ./sample_project --format json
```

```python
from leakguard import analyze_project

findings = analyze_project("./sample_project")
```

## Architecture

```
Project path → Scanner → Parser → AST Visitor → FileAnalysis → (CFG → Dataflow → Lifecycle → Findings)
```

The AST layer extracts structural information without prematurely classifying leaks.

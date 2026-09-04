# LeakGuard Seeded Benchmark

Each Python file is a deterministic seeded case. Run the benchmark suite from the project root with:

```powershell
python -m unittest tests.test_benchmark -v
```

Expected outcomes:

| Case | Expected |
| --- | --- |
| `01_obvious_leak.py` | leak |
| `02_direct_close.py` | safe |
| `03_early_return.py` | leak |
| `04_if_else_safe.py` | safe |
| `05_branch_leak.py` | leak |
| `06_try_finally.py` | safe |
| `07_exception_return.py` | leak |
| `08_with_safe.py` | safe |
| `09_loop_close.py` | safe |
| `10_returned_resource.py` | safe ownership escape |

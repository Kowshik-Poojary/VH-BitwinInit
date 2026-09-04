"""Case 4 (SAFE): open() protected by try-finally block."""


def safe_try_finally(path: str) -> str:
    f = open(path, "r")
    try:
        data = f.read()
        return data
    finally:
        f.close()

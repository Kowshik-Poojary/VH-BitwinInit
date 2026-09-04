"""Case 5 (SAFE): open() managed with standard 'with' context manager."""


def safe_context_manager(path: str) -> str:
    with open(path, "r") as f:
        return f.read()

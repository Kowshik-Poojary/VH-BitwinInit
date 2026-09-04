"""Case 3: open() inside try-block, close() only in except handler (missing on success)."""


def buggy_exception_handling(path: str) -> str:
    f = open(path, "r")
    try:
        data = f.read()
        return data
    except Exception:
        f.close()
        raise

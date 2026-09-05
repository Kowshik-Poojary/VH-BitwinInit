"""Case 1: open() with no close() on straight-line code path."""


def process_file(path: str) -> str:
    f = open(path, "r")
    data = f.read()

    return data

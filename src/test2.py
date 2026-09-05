def load_with_early_return(path: str, fast_exit: bool) -> str | None:
    f = open(path, "r")
    if fast_exit:
        return None
    content = f.read()
    return content

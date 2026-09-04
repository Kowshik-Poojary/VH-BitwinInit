def run():
    handle = open("data.txt")
    try:
        work()
    except Exception:
        return
    handle.close()

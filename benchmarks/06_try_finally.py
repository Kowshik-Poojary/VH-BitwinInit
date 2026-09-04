def run():
    handle = open("data.txt")
    try:
        return handle.read()
    finally:
        handle.close()

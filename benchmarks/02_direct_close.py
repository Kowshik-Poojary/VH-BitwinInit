def run():
    handle = open("data.txt")
    value = handle.read()
    handle.close()
    return value

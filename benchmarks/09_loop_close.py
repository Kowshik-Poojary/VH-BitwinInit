def run(items):
    handle = open("data.txt")
    for item in items:
        print(item)
    handle.close()

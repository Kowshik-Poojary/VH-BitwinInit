def read_data():
    f = open("data.txt")
    data = f.read()
    f.close()
    return data


def read_with_context():
    with open("data.txt") as f:
        return f.read()

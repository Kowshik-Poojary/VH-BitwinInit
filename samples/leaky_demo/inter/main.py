from closer import close_file

def go():
    f = open("x.txt")
    close_file(f)   # should NOT be flagged


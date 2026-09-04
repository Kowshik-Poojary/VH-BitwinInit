"""Sample project for LeakGuard CLI demonstration."""

from __future__ import annotations


def read_config(path: str) -> str:
    f = open(path)
    data = f.read()
    f.close()
    return data


def leaky_read(path: str) -> str:
    f = open(path)
    return f.read()


def safe_with(path: str) -> str:
    with open(path) as f:
        return f.read()


def early_return_leak(path: str, skip: bool) -> None:
    f = open(path)
    if skip:
        return
    f.close()


def try_finally_safe(path: str) -> None:
    f = open(path)
    try:
        process(f)
    finally:
        f.close()


def alias_close(path: str) -> None:
    f = open(path)
    g = f
    g.close()


def return_escape(path: str):
    f = open(path)
    return f


def process(f) -> None:
    pass


import sqlite3
import socket


def db_example(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.close()


def socket_example() -> None:
    sock = socket.socket()
    sock.close()


def nested_leak() -> None:
    f = open("a.txt")
    f = open("b.txt")
    f.close()

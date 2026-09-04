"""Case 8: socket.socket() reassigned in loop without closing prior socket."""

import socket


def poll_servers(addresses: list[tuple[str, int]]) -> None:
    s = None
    for host, port in addresses:
        s = socket.socket()
        s.connect((host, port))
    if s:
        s.close()

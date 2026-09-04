"""Case 7 (SAFE): socket.socket() closed via shutdown and close."""

import socket


def send_payload(host: str, port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((host, port))
        s.sendall(b"PING")
    finally:
        s.shutdown(socket.SHUT_RDWR)
        s.close()

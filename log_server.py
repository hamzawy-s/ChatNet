#!/usr/bin/env python3
"""Tiny threaded HTTP log server for ChatNet Phase 4."""

import html
import os
import socket
import threading
from collections import deque


HOST = "0.0.0.0"
PORT = 8080
LOG_FILE = "server.log"
MAX_LOG_LINES = 50
RECV_SIZE = 4096


def read_last_log_lines(path=LOG_FILE, max_lines=MAX_LOG_LINES):
    """Return the last max_lines from the chat server log."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as log_file:
            return list(deque(log_file, maxlen=max_lines))
    except FileNotFoundError:
        return ["server.log was not found.\n"]


def build_log_html(lines):
    escaped_lines = "".join(html.escape(line) for line in lines)
    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<title>ChatNet Server Log</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;margin:24px;background:#f7f7f7;color:#222;}"
        "h1{font-size:24px;margin:0 0 16px;}"
        "pre{white-space:pre-wrap;background:#fff;border:1px solid #ddd;"
        "padding:16px;border-radius:6px;line-height:1.45;}"
        "</style>"
        "</head>"
        "<body>"
        "<h1>ChatNet Server Log</h1>"
        f"<pre>{escaped_lines}</pre>"
        "</body>"
        "</html>"
    )


def build_http_response(status, content_type, body):
    body_bytes = body.encode("utf-8")
    response_headers = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return response_headers.encode("utf-8") + body_bytes


def parse_request_line(raw_request):
    """Manually parse the first HTTP request line."""
    try:
        request_text = raw_request.decode("iso-8859-1", errors="replace")
        request_line = request_text.split("\r\n", 1)[0]
        method, path, version = request_line.split(" ", 2)
    except ValueError:
        return None, None, None

    return method, path, version


def handle_client(client_socket, client_address):
    """Handle one HTTP client connection."""
    try:
        raw_request = client_socket.recv(RECV_SIZE)
        method, path, version = parse_request_line(raw_request)

        if method == "GET" and path == "/chatlog" and version == "HTTP/1.1":
            lines = read_last_log_lines()
            body = build_log_html(lines)
            response = build_http_response("200 OK", "text/html; charset=utf-8", body)
        else:
            body = (
                "<!doctype html><html><head><title>404 Not Found</title></head>"
                "<body><h1>404 Not Found</h1></body></html>"
            )
            response = build_http_response("404 Not Found", "text/html; charset=utf-8", body)

        client_socket.sendall(response)
    except OSError:
        pass
    finally:
        try:
            client_socket.close()
        except OSError:
            pass


def start_server(host=HOST, port=PORT):
    """Start a raw TCP HTTP server and handle each client on a thread."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen()

        actual_host, actual_port = server_socket.getsockname()
        print(f"Log server listening on {actual_host}:{actual_port}")
        print(f"Open http://127.0.0.1:{actual_port}/chatlog")

        while True:
            client_socket, client_address = server_socket.accept()
            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True,
            )
            thread.start()


def main():
    if not os.path.exists(LOG_FILE):
        print(f"Warning: {LOG_FILE} does not exist yet.")
    start_server()


if __name__ == "__main__":
    main()

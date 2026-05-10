#!/usr/bin/env python3
"""Threaded TCP chat server for ChatNet Phase 3."""

import datetime
import logging
import socket
import threading
import time


HOST = "0.0.0.0"
PORT = 12000
BUFFER_SIZE = 4096
WELCOME_MSG = "200 OK ; Connected to ChatNet Server"
USERNAME_REQUEST = "USERNAME_REQUEST"
UDP_FILE_PORT = 13000

# Required global client table. Every read/write is protected by clients_lock.
clients = {}
clients_lock = threading.Lock()


logger = logging.getLogger("chatnet.server")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    file_handler = logging.FileHandler("server.log", mode="a", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(console_handler)


def timestamp():
    """Return a compact chat timestamp."""
    return datetime.datetime.now().strftime("[%H:%M:%S]")


def send_text(sock, message):
    """Send a UTF-8 text message to one socket."""
    sock.sendall(message.encode("utf-8"))


def print_active_threads():
    """Print the number of currently active Python threads."""
    print(f"Active threads: {threading.active_count()}", flush=True)


def list_users():
    """Return a snapshot of online usernames."""
    with clients_lock:
        return list(clients.keys())


def get_client_socket(username):
    """Return a client socket by username, or None."""
    with clients_lock:
        return clients.get(username)


def get_recipient_snapshot(exclude_user=None):
    """Return a locked snapshot of recipients for broadcast."""
    with clients_lock:
        return [
            (username, sock)
            for username, sock in clients.items()
            if username != exclude_user
        ]


def remove_client(username):
    """Remove a client from the global table and close its socket."""
    with clients_lock:
        sock = clients.pop(username, None)

    if sock is None:
        return

    try:
        sock.close()
    except OSError:
        pass

    logger.info("User '%s' disconnected", username)


def broadcast(message, exclude_user=None):
    """Broadcast a message to all connected clients except exclude_user."""
    dead_users = []
    for username, sock in get_recipient_snapshot(exclude_user):
        try:
            send_text(sock, message)
        except OSError:
            dead_users.append(username)

    for username in dead_users:
        remove_client(username)


def register_username(client_socket, client_address):
    """Read, validate, and register a username for a new client."""
    raw_name = client_socket.recv(BUFFER_SIZE)
    if not raw_name:
        return None

    username = raw_name.decode("utf-8", errors="replace").strip()
    if not username:
        send_text(client_socket, "400 Bad Request ; Username cannot be empty.")
        return None

    with clients_lock:
        duplicate = username in clients
        if not duplicate:
            clients[username] = client_socket

    if duplicate:
        send_text(client_socket, "409 Conflict ; Username already taken.")
        logger.warning(
            "Rejected duplicate username '%s' from %s", username, client_address
        )
        return None

    logger.info("User '%s' connected from %s", username, client_address)
    return username


def handle_users_command(client_socket):
    """Send the current online user list to the requester."""
    users = list_users()
    if users:
        response = f"Online users ({len(users)}): " + ", ".join(users)
    else:
        response = "Online users (0):"
    send_text(client_socket, response)


def handle_private_message(sender, client_socket, message):
    """Handle /msg <user> <text>."""
    parts = message.split(" ", 2)
    if len(parts) < 3 or not parts[1] or not parts[2]:
        send_text(client_socket, "Usage: /msg <user> <text>")
        return

    recipient, text = parts[1], parts[2]
    recipient_socket = get_client_socket(recipient)
    if recipient_socket is None:
        send_text(client_socket, f"ERROR: User '{recipient}' not found.")
        return

    try:
        send_text(recipient_socket, f"{timestamp()} [PM from {sender}]: {text}")
        send_text(client_socket, f"{timestamp()} [PM to {recipient}]: {text}")
    except OSError:
        remove_client(recipient)
        send_text(client_socket, f"ERROR: Could not deliver message to '{recipient}'.")


def handle_sendfile_command(sender, client_socket, message):
    """Coordinate UDP file transfer between two chat clients."""
    parts = message.split(" ", 2)
    if len(parts) < 3:
        send_text(client_socket, "Usage: /sendfile <filename> <recipient>")
        return

    filename, recipient = parts[1], parts[2]
    recipient_socket = get_client_socket(recipient)
    if recipient_socket is None:
        send_text(client_socket, f"ERROR: User '{recipient}' not found.")
        return

    try:
        sender_ip = client_socket.getpeername()[0]
        recipient_ip = recipient_socket.getpeername()[0]
        send_text(
            recipient_socket,
            f"FILE_NOTIFY {sender} {filename} {sender_ip} {UDP_FILE_PORT}",
        )
        time.sleep(0.5)
        send_text(client_socket, f"FILE_TARGET {recipient_ip} {UDP_FILE_PORT}")
        logger.info("File transfer requested: %s -> %s (%s)", sender, recipient, filename)
    except OSError:
        remove_client(recipient)
        send_text(client_socket, f"ERROR: Could not contact '{recipient}'.")


def handle_throughput_command(client_socket, message):
    """Compatibility command from Phase 2 tests."""
    parts = message.split()
    if len(parts) != 2:
        send_text(client_socket, "Usage: THROUGHPUT <bytes>")
        return

    try:
        expected = int(parts[1])
    except ValueError:
        send_text(client_socket, "ERROR: Invalid throughput size.")
        return

    received = 0
    while received < expected:
        chunk = client_socket.recv(min(BUFFER_SIZE, expected - received))
        if not chunk:
            break
        received += len(chunk)

    send_text(client_socket, f"THROUGHPUT_ACK {received}")


def handle_client(client_socket, client_address):
    """Serve one connected client in its own thread."""
    username = None

    try:
        send_text(client_socket, WELCOME_MSG)
        time.sleep(0.05)
        send_text(client_socket, USERNAME_REQUEST)

        username = register_username(client_socket, client_address)
        if username is None:
            return

        print_active_threads()
        send_text(client_socket, f"Welcome, {username}!")
        broadcast(f"{timestamp()} {username} has joined the chat.", exclude_user=username)

        while True:
            data = client_socket.recv(BUFFER_SIZE)
            if not data:
                break

            message = data.decode("utf-8", errors="replace").strip()
            if not message:
                continue

            command = message.lower()

            if command == "/quit":
                send_text(client_socket, "DISCONNECT_ACK")
                break
            if command == "/users":
                handle_users_command(client_socket)
                continue
            if command.startswith("/msg "):
                handle_private_message(username, client_socket, message)
                continue
            if command.startswith("/sendfile ") or command.startswith("sendfile "):
                handle_sendfile_command(username, client_socket, message)
                continue
            if message.upper() == "PING":
                send_text(client_socket, "PONG")
                continue
            if message.upper().startswith("THROUGHPUT"):
                handle_throughput_command(client_socket, message)
                continue

            logger.info("[CHAT] %s: %s", username, message)
            broadcast(f"{timestamp()} <{username}>: {message}", exclude_user=username)

    except ConnectionResetError:
        logger.warning("Connection reset by %s", username or client_address)
    except OSError as exc:
        logger.warning("Socket error for %s: %s", username or client_address, exc)
    finally:
        if username is not None:
            broadcast(f"{timestamp()} {username} has left the chat.", exclude_user=username)
            remove_client(username)
        else:
            try:
                client_socket.close()
            except OSError:
                pass
        print_active_threads()


def main(host=HOST, port=PORT):
    """Start the threaded chat server."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen()

    bound_host, bound_port = server_socket.getsockname()
    print(f"Server listening on {bound_host}:{bound_port}", flush=True)
    logger.info("ChatNet threaded server started on %s:%s", bound_host, bound_port)
    print_active_threads()

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            logger.info("Incoming connection from %s", client_address)
            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True,
            )
            thread.start()
    except KeyboardInterrupt:
        logger.info("Server shutting down")
    finally:
        with clients_lock:
            connected = list(clients.items())
            clients.clear()

        for _, sock in connected:
            try:
                send_text(sock, "Server shutting down.")
                sock.close()
            except OSError:
                pass

        server_socket.close()
        logger.info("Server stopped")


if __name__ == "__main__":
    main()

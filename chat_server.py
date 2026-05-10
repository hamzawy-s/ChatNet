#!/usr/bin/env python3














# ─── Standard Library Imports ─────────────────────────────────
import socket       # Core TCP networking
import select       # I/O multiplexing (single-threaded concurrency)
import time         # Timestamps
import datetime     # Formatted time strings
import logging      # Structured logging
import struct       # (Available for future binary protocol work)

# ─── Logging Configuration ────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('ChatNet-Server')

# ─── Server Constants ─────────────────────────────────────────
HOST = '0.0.0.0'           # Listen on all available interfaces
PORT = 12000                # Assignment-specified port
BUFFER_SIZE = 4096          # Max bytes per recv() call
WELCOME_MSG = "200 OK ; Connected to ChatNet Server"


# ═══════════════════════════════════════════════════════════════
#  Helper Functions
# ═══════════════════════════════════════════════════════════════

def get_timestamp():
    """Return current time as [HH:MM:SS] string for chat messages."""
    return datetime.datetime.now().strftime('[%H:%M:%S]')


def broadcast(message, sender_sock, clients):
    """
    Send a message to ALL connected clients except the sender.

    Args:
        message    : The string message to broadcast.
        sender_sock: Socket of the client who sent the message (excluded).
        clients    : Dict mapping {socket: username} of connected clients.
    """
    dead_sockets = []
    for sock in clients:
        if sock is not sender_sock:
            try:
                sock.send(message.encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError, OSError):
                # Mark broken connections for cleanup
                dead_sockets.append(sock)
    return dead_sockets


def remove_client(sock, sockets_list, clients, pending, throughput_state):
    """
    Cleanly remove a client from all tracking structures and close socket.

    Args:
        sock             : The client socket to remove.
        sockets_list     : Master list of sockets monitored by select().
        clients          : Dict {socket: username}.
        pending          : Set of sockets awaiting username.
        throughput_state  : Dict tracking in-progress throughput tests.
    """
    username = clients.pop(sock, None)
    pending.discard(sock)
    throughput_state.pop(sock, None)
    if sock in sockets_list:
        sockets_list.remove(sock)
    try:
        sock.close()
    except OSError:
        pass
    if username:
        logger.info(f"Cleaned up connection for '{username}'")


# ═══════════════════════════════════════════════════════════════
#  Main Server Loop
# ═══════════════════════════════════════════════════════════════

def main():
    """
    Main entry point. Creates a TCP server socket, then enters
    a select()-based event loop to handle multiple clients without
    any threading.
    """

    # ── Create and configure the listening socket ──────────────
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR allows immediate rebind after server restart
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)             # Backlog of 5 pending connections
    server_socket.setblocking(False)    # Non-blocking for select()

    # Print the required startup message
    actual_ip, actual_port = server_socket.getsockname()
    print(f"Server listening on {actual_ip}:{actual_port}")
    logger.info("ChatNet Server started successfully")

    # ── State tracking structures ──────────────────────────────
    sockets_list = [server_socket]  # All sockets for select()
    clients = {}                    # {socket: username} — authenticated clients
    pending = set()                 # Sockets that haven't sent a username yet
    # Tracks in-progress throughput tests: {socket: {'expected': int, 'received': int}}
    throughput_state = {}

    # ── Event loop using select() ──────────────────────────────
    try:
        while True:
            # Wait up to 1 second for readable or exceptional sockets
            readable, _, exceptional = select.select(
                sockets_list, [], sockets_list, 1.0
            )

            # ── Handle readable sockets ───────────────────────
            for sock in readable:

                # ── Case 1: New incoming connection ────────────
                if sock is server_socket:
                    client_socket, client_addr = server_socket.accept()
                    logger.info(f"New connection from {client_addr}")

                    # Send the required welcome message
                    client_socket.send(WELCOME_MSG.encode('utf-8'))
                    time.sleep(0.05)  # Brief pause so client receives separately
                    # Prompt for username
                    client_socket.send("USERNAME_REQUEST".encode('utf-8'))

                    sockets_list.append(client_socket)
                    pending.add(client_socket)
                    continue

                # ── Case 2: Data from existing client ──────────
                try:
                    data = sock.recv(BUFFER_SIZE)

                    # Empty data = client dropped connection
                    if not data:
                        username = clients.get(sock, 'Unknown')
                        logger.info(f"'{username}' disconnected (empty recv)")
                        dead = broadcast(
                            f"{get_timestamp()} {username} has left the chat.",
                            sock, clients
                        )
                        for d in dead:
                            remove_client(d, sockets_list, clients, pending, throughput_state)
                        remove_client(sock, sockets_list, clients, pending, throughput_state)
                        continue

                    # ── Sub-case 2a: Throughput data accumulation ──
                    if sock in throughput_state:
                        state = throughput_state[sock]
                        state['received'] += len(data)
                        # Check if all expected bytes have arrived
                        if state['received'] >= state['expected']:
                            sock.send(
                                f"THROUGHPUT_ACK {state['received']}".encode('utf-8')
                            )
                            logger.info(
                                f"Throughput test complete: {state['received']} bytes"
                            )
                            del throughput_state[sock]
                        continue

                    message = data.decode('utf-8').strip()

                    # ── Sub-case 2b: Username registration ─────
                    if sock in pending:
                        username = message
                        clients[sock] = username
                        pending.discard(sock)
                        logger.info(f"User '{username}' joined from {sock.getpeername()}")

                        # Notify everyone about the new user
                        dead = broadcast(
                            f"{get_timestamp()} {username} has joined the chat.",
                            sock, clients
                        )
                        for d in dead:
                            remove_client(d, sockets_list, clients, pending, throughput_state)

                        sock.send(
                            f"Welcome, {username}! Type messages or 'DISCONNECT' to leave.\n"
                            .encode('utf-8')
                        )
                        continue

                    # ── Sub-case 2c: DISCONNECT command ────────
                    if message.upper() == 'DISCONNECT':
                        username = clients.get(sock, 'Unknown')
                        logger.info(f"User '{username}' requested disconnect")
                        dead = broadcast(
                            f"{get_timestamp()} {username} has left the chat.",
                            sock, clients
                        )
                        for d in dead:
                            remove_client(d, sockets_list, clients, pending, throughput_state)
                        sock.send("DISCONNECT_ACK".encode('utf-8'))
                        remove_client(sock, sockets_list, clients, pending, throughput_state)
                        continue

                    # ── Sub-case 2d: PING command ──────────────
                    if message.upper() == 'PING':
                        sock.send("PONG".encode('utf-8'))
                        continue

                    # ── Sub-case 2e: THROUGHPUT command ────────
                    if message.upper().startswith('THROUGHPUT'):
                        parts = message.split()
                        if len(parts) >= 2:
                            try:
                                expected = int(parts[1])
                                throughput_state[sock] = {
                                    'expected': expected,
                                    'received': 0
                                }
                                logger.info(f"Throughput test started: expecting {expected} bytes")
                            except ValueError:
                                sock.send("ERROR: Invalid throughput size".encode('utf-8'))
                        continue

                    # ── Sub-case 2f: Regular chat message ──────
                    username = clients.get(sock, 'Unknown')
                    formatted = f"{get_timestamp()} <{username}>: {message}"
                    logger.info(f"Message from {username}: {message}")
                    dead = broadcast(formatted, sock, clients)
                    for d in dead:
                        remove_client(d, sockets_list, clients, pending, throughput_state)

                except ConnectionResetError:
                    username = clients.get(sock, 'Unknown')
                    logger.warning(f"Connection reset by '{username}'")
                    remove_client(sock, sockets_list, clients, pending, throughput_state)

            # ── Handle exceptional sockets ─────────────────────
            for sock in exceptional:
                logger.warning(f"Exceptional condition on {sock.getpeername()}")
                remove_client(sock, sockets_list, clients, pending, throughput_state)

    except KeyboardInterrupt:
        logger.info("Server shutting down (Ctrl+C)...")
    finally:
        # Close all remaining sockets
        for sock in sockets_list:
            try:
                sock.close()
            except OSError:
                pass
        logger.info("All connections closed. Server terminated.")


# ═══════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Phase 3 TCP chat client with private messages and UDP file transfer."""

import os
import socket
import threading
import time

from file_receiver import receive_file
from file_sender import send_file


BUFFER_SIZE = 4096
DEFAULT_SERVER_IP = "127.0.0.1"
DEFAULT_SERVER_PORT = 12000
RECEIVED_DIR = "received_files"


class ChatClientV2:
    """Interactive ChatNet client."""

    def __init__(self, server_ip, server_port):
        self.server_ip = server_ip
        self.server_port = server_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = ""
        self.running = False
        self.pause_receiver = threading.Event()

    def connect(self):
        """Connect to the TCP server and register a username."""
        try:
            self.socket.connect((self.server_ip, self.server_port))
            welcome = self.socket.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
            print(f"Server: {welcome}")

            if "USERNAME_REQUEST" not in welcome:
                prompt = self.socket.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
                if "USERNAME_REQUEST" not in prompt:
                    print(f"Unexpected server response: {prompt}")
                    return False

            while not self.username:
                self.username = input("Username: ").strip()

            self.socket.sendall(self.username.encode("utf-8"))
            response = self.socket.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
            print(response)

            if "409 Conflict" in response:
                self.socket.close()
                return False

            self.running = True
            return True
        except OSError as exc:
            print(f"Could not connect: {exc}")
            return False

    def receive_messages(self):
        """Receive server messages in the background."""
        self.socket.settimeout(0.25)

        while self.running:
            if self.pause_receiver.is_set():
                time.sleep(0.05)
                continue

            try:
                data = self.socket.recv(BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                if self.running:
                    print("\nConnection to server lost.")
                self.running = False
                break

            if not data:
                print("\nServer closed the connection.")
                self.running = False
                break

            message = data.decode("utf-8", errors="replace")
            if message == "DISCONNECT_ACK":
                self.running = False
                break

            if message.startswith("FILE_NOTIFY "):
                self.handle_file_notification(message)
            else:
                print(f"\n{message}")

            if self.running:
                print("You: ", end="", flush=True)

    def handle_file_notification(self, message):
        """Start a UDP receiver when another user sends a file."""
        parts = message.split()
        if len(parts) < 5:
            print(f"\nMalformed file notification: {message}")
            return

        sender = parts[1]
        filename = parts[2]
        port = int(parts[4])

        print(f"\nIncoming file '{filename}' from {sender}.")
        print(f"Starting UDP receiver on port {port}...")

        thread = threading.Thread(
            target=receive_file,
            args=(port, RECEIVED_DIR),
            daemon=True,
        )
        thread.start()

    def send_chat_command(self, message):
        """Send a normal chat command or broadcast message."""
        self.socket.sendall(message.encode("utf-8"))

    def send_file_command(self, filename, recipient):
        """Coordinate and start a UDP file transfer."""
        if not os.path.isfile(filename):
            print(f"File not found: {filename}")
            return

        display_name = os.path.basename(filename)
        self.pause_receiver.set()
        time.sleep(0.3)

        try:
            self.socket.sendall(f"SENDFILE {display_name} {recipient}".encode("utf-8"))
            self.socket.settimeout(5.0)
            response = self.socket.recv(BUFFER_SIZE).decode("utf-8", errors="replace")

            if response.startswith("FILE_TARGET "):
                parts = response.split()
                target_ip = parts[1]
                target_port = int(parts[2])
                print(f"Sending '{filename}' to {recipient} at {target_ip}:{target_port}")

                thread = threading.Thread(
                    target=send_file,
                    args=(filename, target_ip, target_port),
                    daemon=True,
                )
                thread.start()
            else:
                print(response)
        except socket.timeout:
            print("Timed out waiting for file-transfer response from server.")
        except OSError as exc:
            print(f"File transfer failed: {exc}")
        finally:
            self.socket.settimeout(0.25)
            self.pause_receiver.clear()

    def ping(self, count=4):
        """Send PING commands and print round-trip times."""
        self.pause_receiver.set()
        time.sleep(0.3)
        rtts = []

        try:
            for index in range(count):
                start = time.perf_counter()
                self.socket.sendall(b"PING")
                self.socket.settimeout(2.0)
                response = self.socket.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
                elapsed_ms = (time.perf_counter() - start) * 1000

                if response == "PONG":
                    rtts.append(elapsed_ms)
                    print(f"Ping {index + 1}: {elapsed_ms:.2f} ms")
                else:
                    print(f"Ping {index + 1}: unexpected response {response!r}")

            if rtts:
                avg = sum(rtts) / len(rtts)
                print(f"Ping min/avg/max: {min(rtts):.2f}/{avg:.2f}/{max(rtts):.2f} ms")
        except OSError as exc:
            print(f"Ping failed: {exc}")
        finally:
            self.socket.settimeout(0.25)
            self.pause_receiver.clear()

    def throughput_test(self, size_bytes):
        """Send a dummy payload for a simple throughput measurement."""
        self.pause_receiver.set()
        time.sleep(0.3)

        try:
            payload = b"X" * size_bytes
            self.socket.sendall(f"THROUGHPUT {size_bytes}".encode("utf-8"))
            time.sleep(0.05)

            start = time.perf_counter()
            self.socket.sendall(payload)
            self.socket.settimeout(10.0)
            ack = self.socket.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
            elapsed = time.perf_counter() - start

            kbps = (size_bytes * 8) / (elapsed * 1000) if elapsed > 0 else 0
            print(f"{ack}; throughput {kbps:.2f} kbps")
        except OSError as exc:
            print(f"Throughput test failed: {exc}")
        finally:
            self.socket.settimeout(0.25)
            self.pause_receiver.clear()

    def run(self):
        """Start the interactive client."""
        if not self.connect():
            return

        receiver_thread = threading.Thread(target=self.receive_messages, daemon=True)
        receiver_thread.start()

        print("Commands: /msg <user> <text>, /users, /sendfile <file> <user>, /quit")

        try:
            while self.running:
                message = input("You: ").strip()
                if not message:
                    continue

                command = message.lower()

                if command == "/quit":
                    self.send_chat_command("/quit")
                    self.running = False
                    break
                if command == "/users" or command.startswith("/msg "):
                    self.send_chat_command(message)
                    continue
                if command.startswith("/sendfile "):
                    parts = message.split()
                    if len(parts) != 3:
                        print("Usage: /sendfile <filename> <recipient>")
                    else:
                        self.send_file_command(parts[1], parts[2])
                    continue
                if command == "/ping":
                    self.ping()
                    continue
                if command.startswith("/throughput "):
                    parts = message.split()
                    try:
                        self.throughput_test(int(parts[1]))
                    except (IndexError, ValueError):
                        print("Usage: /throughput <bytes>")
                    continue

                self.send_chat_command(message)
        except (KeyboardInterrupt, EOFError):
            print("\nDisconnecting...")
            try:
                self.send_chat_command("/quit")
            except OSError:
                pass
        finally:
            self.running = False
            try:
                self.socket.close()
            except OSError:
                pass
            print("Connection closed.")


def main():
    """Prompt for server details and run the client."""
    server_ip = input(f"Server IP [{DEFAULT_SERVER_IP}]: ").strip() or DEFAULT_SERVER_IP
    raw_port = input(f"Server port [{DEFAULT_SERVER_PORT}]: ").strip()
    server_port = int(raw_port) if raw_port else DEFAULT_SERVER_PORT
    ChatClientV2(server_ip, server_port).run()


if __name__ == "__main__":
    main()

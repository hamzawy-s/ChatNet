#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           ChatNet Phase 2 - TCP Chat Client                  ║
║           With Built-in Network Diagnostics                  ║
║           University Network Programming Project             ║
╚══════════════════════════════════════════════════════════════╝

Connects to the ChatNet server and provides:
  - Real-time chat messaging
  - /ping        : RTT measurement (Avg, Min, Max)
  - /throughput N : Throughput test sending N bytes (reports kbps)
  - DISCONNECT    : Graceful disconnect
"""

# ─── Standard Library Imports ─────────────────────────────────
import socket       # Core TCP networking
import threading    # Receive thread runs in background
import time         # RTT measurement via perf_counter()
import datetime     # (Available for future use)
import logging      # Structured logging
import struct       # (Available for future binary protocol work)

# ─── Logging Configuration ────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('ChatNet-Client')

# ─── Client Constants ─────────────────────────────────────────
BUFFER_SIZE = 4096  # Max bytes per recv() call


# ═══════════════════════════════════════════════════════════════
#  ChatClient Class
# ═══════════════════════════════════════════════════════════════

class ChatClient:
    """
    TCP Chat client that connects to a ChatNet server.
    Uses a background thread for receiving messages and the
    main thread for user input and diagnostic commands.
    """

    def __init__(self, server_ip, server_port):
        """
        Initialize client with server address.

        Args:
            server_ip   : IP address of the ChatNet server.
            server_port : Port number the server is listening on.
        """
        self.server_ip = server_ip
        self.server_port = server_port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.username = None
        self.running = False
        # When True, the receive thread pauses so diagnostic
        # commands can read from the socket directly without races.
        self.diagnostic_mode = False

    # ─── Connection Setup ─────────────────────────────────────

    def connect(self):
        """
        Connect to the server, receive welcome message,
        register username, and receive confirmation.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self.socket.connect((self.server_ip, self.server_port))
            logger.info(f"Connected to {self.server_ip}:{self.server_port}")

            # Step 1: Receive "200 OK ; Connected to ChatNet Server"
            welcome = self.socket.recv(BUFFER_SIZE).decode('utf-8')
            print(f"\n  Server: {welcome}")

            # Step 2: Receive username request
            prompt = self.socket.recv(BUFFER_SIZE).decode('utf-8')
            if prompt == "USERNAME_REQUEST":
                self.username = input("  Enter your username: ").strip()
                # Step 3: Send username to server
                self.socket.send(self.username.encode('utf-8'))

            # Step 4: Receive welcome confirmation
            confirmation = self.socket.recv(BUFFER_SIZE).decode('utf-8')
            print(f"  {confirmation}")

            self.running = True
            return True

        except ConnectionRefusedError:
            print("\n  ERROR: Connection refused. Is the server running?")
            return False
        except Exception as e:
            print(f"\n  ERROR: {e}")
            return False

    # ─── Receive Thread ───────────────────────────────────────

    def receive_messages(self):
        """
        Background thread: continuously receive and display
        messages from the server. Pauses during diagnostic mode
        to avoid consuming PONG / THROUGHPUT_ACK responses.
        """
        while self.running:
            # Pause when diagnostic commands are active
            if self.diagnostic_mode:
                time.sleep(0.05)
                continue

            try:
                # Use timeout so we can check flags periodically
                self.socket.settimeout(0.5)
                data = self.socket.recv(BUFFER_SIZE)

                if not data:
                    # Server closed connection
                    print("\n  [!] Server closed the connection.")
                    self.running = False
                    break

                message = data.decode('utf-8')

                # Server acknowledged our DISCONNECT request
                if message.strip() == "DISCONNECT_ACK":
                    self.running = False
                    break

                # Display incoming chat message
                print(f"\n  {message}")
                print("  You: ", end='', flush=True)

            except socket.timeout:
                # No data available — loop and check flags again
                continue
            except (ConnectionResetError, OSError):
                if self.running:
                    print("\n  [!] Lost connection to server.")
                    self.running = False
                break

    # ─── Diagnostic: PING ─────────────────────────────────────

    def ping(self, count=4):
        """
        Send PING messages to the server and measure Round-Trip Time.
        Calculates and displays Average, Minimum, and Maximum RTT.

        Args:
            count: Number of PING packets to send (default 4).
        """
        # Pause receive thread so we can read PONG directly
        self.diagnostic_mode = True
        time.sleep(0.1)  # Let receive thread yield

        print(f"\n  --- Pinging ChatNet Server ({self.server_ip}:{self.server_port}) ---")
        rtts = []  # Collect RTT values in milliseconds

        for i in range(count):
            try:
                # Record start time with high-resolution timer
                start = time.perf_counter()

                # Send PING to server
                self.socket.send("PING".encode('utf-8'))

                # Wait for PONG response (with timeout)
                self.socket.settimeout(5.0)
                response = self.socket.recv(BUFFER_SIZE).decode('utf-8')

                # Record end time
                end = time.perf_counter()

                if response.strip() == "PONG":
                    # Calculate RTT in milliseconds
                    rtt_ms = (end - start) * 1000.0
                    rtts.append(rtt_ms)
                    print(f"    [{i+1}] Reply from {self.server_ip}: time={rtt_ms:.3f} ms")
                else:
                    print(f"    [{i+1}] Unexpected response: {response}")

            except socket.timeout:
                print(f"    [{i+1}] Request timed out (5s)")
            except Exception as e:
                print(f"    [{i+1}] Error: {e}")

            # Small delay between pings (like real ping utility)
            time.sleep(0.5)

        # ── Print RTT Statistics ──────────────────────────────
        print(f"\n  --- Ping Statistics for {self.server_ip} ---")
        sent = count
        received = len(rtts)
        lost = sent - received
        loss_pct = (lost / sent) * 100 if sent > 0 else 0

        print(f"    Packets: Sent = {sent}, Received = {received}, "
              f"Lost = {lost} ({loss_pct:.0f}% loss)")

        if rtts:
            avg_rtt = sum(rtts) / len(rtts)
            min_rtt = min(rtts)
            max_rtt = max(rtts)
            print(f"    RTT (ms): Min = {min_rtt:.3f}, "
                  f"Max = {max_rtt:.3f}, Avg = {avg_rtt:.3f}")
        else:
            print("    All packets lost — no RTT data available.")

        print()

        # Resume receive thread
        self.diagnostic_mode = False

    # ─── Diagnostic: Throughput ───────────────────────────────

    def throughput_test(self, size_bytes):
        """
        Measure network throughput by sending a dummy payload of
        the specified size to the server and timing the transfer.

        Args:
            size_bytes: Number of bytes to send for the test.
        """
        # Pause receive thread so we can read ACK directly
        self.diagnostic_mode = True
        time.sleep(0.1)  # Let receive thread yield

        print(f"\n  --- Throughput Test ({size_bytes} bytes) ---")

        try:
            # Step 1: Notify server that a throughput test is starting
            header = f"THROUGHPUT {size_bytes}"
            self.socket.send(header.encode('utf-8'))
            time.sleep(0.05)  # Brief pause so server processes the header

            # Step 2: Generate dummy payload (repeating 'X' bytes)
            payload = b'X' * size_bytes

            # Step 3: Send the payload and measure elapsed time
            start = time.perf_counter()

            total_sent = 0
            while total_sent < size_bytes:
                # Send in chunks up to BUFFER_SIZE
                chunk = payload[total_sent:total_sent + BUFFER_SIZE]
                sent = self.socket.send(chunk)
                total_sent += sent

            # Step 4: Wait for server acknowledgement
            self.socket.settimeout(10.0)
            ack = self.socket.recv(BUFFER_SIZE).decode('utf-8')

            end = time.perf_counter()

            # Step 5: Calculate throughput
            elapsed_sec = end - start
            elapsed_ms = elapsed_sec * 1000.0

            if elapsed_sec > 0:
                # bits = bytes * 8, kbps = bits / (seconds * 1000)
                throughput_kbps = (size_bytes * 8) / (elapsed_sec * 1000)
                throughput_mbps = throughput_kbps / 1000

                print(f"    Bytes sent     : {total_sent}")
                print(f"    Server ACK     : {ack}")
                print(f"    Time elapsed   : {elapsed_ms:.2f} ms")
                print(f"    Throughput     : {throughput_kbps:.2f} kbps "
                      f"({throughput_mbps:.4f} Mbps)")
            else:
                print("    Transfer completed too fast to measure accurately.")

        except socket.timeout:
            print("    ERROR: Server did not acknowledge — timed out (10s).")
        except Exception as e:
            print(f"    ERROR: Throughput test failed — {e}")

        print()

        # Resume receive thread
        self.diagnostic_mode = False

    # ─── Main Client Loop ─────────────────────────────────────

    def run(self):
        """
        Main entry point for the client. Connects to the server,
        starts the receive thread, then loops for user input.
        """
        # Attempt connection
        if not self.connect():
            return

        # Start background receive thread (daemon so it dies with main)
        recv_thread = threading.Thread(target=self.receive_messages, daemon=True)
        recv_thread.start()
        logger.info("Receive thread started")

        # Print available commands
        print("  ┌─────────────────────────────────────────────┐")
        print("  │  Commands:                                  │")
        print("  │    /ping             - Measure RTT          │")
        print("  │    /throughput <N>   - Test throughput       │")
        print("  │    DISCONNECT        - Leave the chat       │")
        print("  └─────────────────────────────────────────────┘")
        print()

        try:
            while self.running:
                message = input("  You: ").strip()

                # Check if connection dropped while waiting for input
                if not self.running:
                    break

                # Skip empty input
                if not message:
                    continue

                # ── Command: /ping ────────────────────────────
                if message.lower() == '/ping':
                    self.ping(count=4)

                # ── Command: /throughput <size> ───────────────
                elif message.lower().startswith('/throughput'):
                    parts = message.split()
                    if len(parts) >= 2:
                        try:
                            size = int(parts[1])
                            if size <= 0:
                                print("  Usage: /throughput <positive_integer>")
                            else:
                                self.throughput_test(size)
                        except ValueError:
                            print("  Usage: /throughput <size_in_bytes>  (e.g. /throughput 10000)")
                    else:
                        print("  Usage: /throughput <size_in_bytes>  (e.g. /throughput 10000)")

                # ── Command: DISCONNECT ───────────────────────
                elif message.upper() == 'DISCONNECT':
                    self.socket.send("DISCONNECT".encode('utf-8'))
                    time.sleep(0.5)
                    self.running = False
                    print("  Disconnected from ChatNet server.")

                # ── Regular chat message ──────────────────────
                else:
                    self.socket.send(message.encode('utf-8'))

        except (KeyboardInterrupt, EOFError):
            # Handle Ctrl+C gracefully
            print("\n  Disconnecting...")
            try:
                self.socket.send("DISCONNECT".encode('utf-8'))
            except OSError:
                pass
            self.running = False
        finally:
            self.socket.close()
            logger.info("Connection closed.")
            print("  Connection closed. Goodbye!")


# ═══════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════

def main():
    """Prompt user for server details and launch the client."""
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║        ChatNet Client — Phase 2              ║")
    print("  ╠══════════════════════════════════════════════╣")
    print("  ║  Network Diagnostics:  /ping  /throughput    ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()

    # Prompt with sensible defaults for quick local testing
    server_ip = input("  Server IP   [127.0.0.1]: ").strip() or '127.0.0.1'
    server_port = input("  Server Port [12000]    : ").strip() or '12000'

    client = ChatClient(server_ip, int(server_port))
    client.run()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""UDP Stop-and-Wait file receiver for ChatNet Phase 3."""

import os
import socket
import struct
import time


CHUNK_SIZE = 512
BUFFER_SIZE = CHUNK_SIZE + 4
DEFAULT_PORT = 13000
RECEIVE_TIMEOUT_SECONDS = 30.0


def _parse_header(packet):
    """Parse FILEHEADER:<filename>:<total_chunks> packets."""
    try:
        text = packet.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if not text.startswith("FILEHEADER:"):
        return None

    parts = text.split(":", 2)
    if len(parts) != 3:
        return None

    filename = os.path.basename(parts[1]) or "received_file"
    try:
        total_chunks = int(parts[2])
    except ValueError:
        return None

    if total_chunks < 1:
        return None

    return filename, total_chunks


def _print_progress(received_chunks, total_chunks):
    """Print one-line receive progress."""
    percent = (received_chunks / total_chunks) * 100 if total_chunks else 100
    print(
        f"\r[receiver] Progress: {received_chunks}/{total_chunks} chunks "
        f"({percent:5.1f}%)",
        end="",
    )


def receive_file(listen_port=DEFAULT_PORT, save_dir="received_files"):
    """
    Receive a file over UDP using Stop-and-Wait ARQ.

    The receiver accepts 512-byte data chunks prefixed by a 4-byte sequence
    number, ACKs each sequence number with struct.pack("!I", seq), reassembles
    the chunks in order, and saves the file in save_dir.
    """
    os.makedirs(save_dir, exist_ok=True)

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        try:
            udp_socket.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass
    udp_socket.bind(("0.0.0.0", int(listen_port)))
    udp_socket.settimeout(RECEIVE_TIMEOUT_SECONDS)

    print(f"[receiver] Listening on UDP port {listen_port}")
    print(f"[receiver] Saving files in {os.path.abspath(save_dir)}")

    filename = None
    total_chunks = None
    sender_addr = None
    chunks = {}
    start = time.perf_counter()

    try:
        while filename is None:
            packet, sender_addr = udp_socket.recvfrom(4096)
            parsed_header = _parse_header(packet)
            if parsed_header is None:
                continue

            filename, total_chunks = parsed_header
            udp_socket.sendto(b"ACK_HEADER", sender_addr)
            print(f"[receiver] Receiving {filename} ({total_chunks} chunks)")

        while len(chunks) < total_chunks:
            packet, packet_addr = udp_socket.recvfrom(4096)

            parsed_header = _parse_header(packet)
            if parsed_header is not None:
                udp_socket.sendto(b"ACK_HEADER", packet_addr)
                continue

            if packet == b"FILEEND":
                if len(chunks) >= total_chunks:
                    break
                continue

            if len(packet) < 4:
                continue

            sequence_number = struct.unpack("!I", packet[:4])[0]
            chunk = packet[4:]

            udp_socket.sendto(struct.pack("!I", sequence_number), packet_addr)

            if 0 <= sequence_number < total_chunks and sequence_number not in chunks:
                chunks[sequence_number] = chunk
                _print_progress(len(chunks), total_chunks)

        if len(chunks) != total_chunks:
            print(f"\n[receiver] Transfer incomplete: {len(chunks)}/{total_chunks} chunks.")
            return False

        output_path = os.path.join(save_dir, filename)
        with open(output_path, "wb") as output_file:
            for sequence_number in range(total_chunks):
                output_file.write(chunks[sequence_number])

        elapsed = time.perf_counter() - start
        print()
        print(f"[receiver] Saved {output_path} in {elapsed:.2f}s.")
        return True
    except socket.timeout:
        print("\n[receiver] Timed out waiting for file data.")
        return False
    except OSError as exc:
        print(f"\n[receiver] Receive failed: {exc}")
        return False
    finally:
        udp_socket.close()


if __name__ == "__main__":
    raw_port = input(f"Listen port [{DEFAULT_PORT}]: ").strip()
    port = int(raw_port) if raw_port else DEFAULT_PORT
    directory = input("Save directory [received_files]: ").strip() or "received_files"
    receive_file(port, directory)

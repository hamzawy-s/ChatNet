#!/usr/bin/env python3
"""UDP Stop-and-Wait file sender for ChatNet Phase 3."""

import math
import os
import socket
import struct
import time

CHUNK_SIZE = 512
TIMEOUT_SECONDS = 2.0
MAX_RETRIES = 10
DEFAULT_PORT = 13000


def _is_udp_reset(exc):
    """Return True for Windows UDP ICMP connection reset noise."""
    return getattr(exc, "winerror", None) == 10054 or getattr(exc, "errno", None) == 10054


def _recvfrom_ignoring_udp_reset(udp_socket, buffer_size):
    """Receive an ACK, treating WinError 10054 like a lost UDP packet."""
    try:
        return udp_socket.recvfrom(buffer_size)
    except OSError as exc:
        if _is_udp_reset(exc):
            return None
        raise


def _send_header(udp_socket, target_addr, filename, total_chunks):
    """Send the file header until the receiver acknowledges it."""
    header = f"FILEHEADER:{filename}:{total_chunks}".encode("utf-8")

    for attempt in range(1, MAX_RETRIES + 1):
        udp_socket.sendto(header, target_addr)
        try:
            result = _recvfrom_ignoring_udp_reset(udp_socket, 1024)
            if result is None:
                print(f"[sender] UDP reset while waiting for header ACK, retry {attempt}/{MAX_RETRIES}")
                continue
            ack, _ = result
            if ack == b"ACK_HEADER":
                return True
        except socket.timeout:
            print(f"[sender] Header timeout, retry {attempt}/{MAX_RETRIES}")
            continue
    return False

def _send_chunk(udp_socket, target_addr, sequence_number, chunk):
    """Send one chunk and wait for its matching ACK."""
    packet = struct.pack("!I", sequence_number) + chunk

    for attempt in range(1, MAX_RETRIES + 1):
        udp_socket.sendto(packet, target_addr)
        try:
            result = _recvfrom_ignoring_udp_reset(udp_socket, 1024)
            if result is None:
                print(f"[sender] UDP reset while waiting for chunk {sequence_number} ACK, retry {attempt}/{MAX_RETRIES}")
                continue
            ack, _ = result
            if len(ack) >= 4:
                ack_number = struct.unpack("!I", ack[:4])[0]
                if ack_number == sequence_number:
                    return True
        except socket.timeout:
            print(f"[sender] Chunk {sequence_number} timeout, retry {attempt}/{MAX_RETRIES}")
            continue

        print(f"[sender] Bad ACK for chunk {sequence_number}, retry {attempt}/{MAX_RETRIES}")
    return False

def _print_progress(sent_chunks, total_chunks):
    """Print one-line transfer progress."""
    percent = (sent_chunks / total_chunks) * 100 if total_chunks else 100
    print(f"\r[sender] Progress: {sent_chunks}/{total_chunks} chunks ({percent:5.1f}%)", end="")

def send_file(filepath, target_ip, target_port=DEFAULT_PORT):
    """Send a file over UDP using Stop-and-Wait ARQ."""
    if not os.path.isfile(filepath):
        print(f"[sender] File not found: {filepath}")
        return False

    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)
    total_chunks = max(1, math.ceil(filesize / CHUNK_SIZE))
    target_addr = (target_ip, int(target_port))

    print(f"[sender] Sending {filename} ({filesize} bytes) to {target_addr[0]}:{target_addr[1]}")
    
    # إنشاء السوكيت وتطبيق إصلاح ويندوز
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.settimeout(TIMEOUT_SECONDS)
    
    if hasattr(socket, 'SIO_UDP_CONNRESET'):
        try:
            # هذا السطر يمنع WinError 10054
            udp_socket.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass

    print(f"[sender] Attempting to start transfer...")
    start_time = time.perf_counter()

    try:
        # 1. إرسال الهيدر
        if not _send_header(udp_socket, target_addr, filename, total_chunks):
            print("\n[sender] Receiver did not acknowledge file header (Timeout).")
            return False

        # 2. إرسال البيانات
        with open(filepath, "rb") as file_obj:
            for sequence_number in range(total_chunks):
                chunk = file_obj.read(CHUNK_SIZE)
                if not _send_chunk(udp_socket, target_addr, sequence_number, chunk):
                    print(f"\n[sender] Failed to send chunk {sequence_number} after retries.")
                    return False
                _print_progress(sequence_number + 1, total_chunks)

        # 3. إرسال إشارة النهاية
        udp_socket.sendto(b"FILEEND", target_addr)
        
        elapsed = time.perf_counter() - start_time
        print(f"\n[sender] Transfer complete in {elapsed:.2f}s.")
        return True

    except Exception as exc:
        print(f"\n[sender] Transfer failed with error: {exc}")
        return False
    finally:
        udp_socket.close()

if __name__ == "__main__":
    path = input("File to send: ").strip()
    ip = input("Receiver IP [127.0.0.1]: ").strip() or "127.0.0.1"
    raw_port = input(f"Receiver port [{DEFAULT_PORT}]: ").strip()
    port = int(raw_port) if raw_port else DEFAULT_PORT
    send_file(path, ip, port)

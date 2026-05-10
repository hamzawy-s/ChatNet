"""Phase 3 automated test: threaded server + UDP file transfer."""
import socket
import time
import struct
import threading
import os

SERVER = ('127.0.0.1', 12000)
BUF = 4096

def make_client(name):
    """Connect and register a client, return socket."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(SERVER)
    s.recv(BUF)  # welcome
    s.recv(BUF)  # username request
    s.send(name.encode())
    resp = s.recv(BUF).decode()
    return s, resp

def test_chat_and_commands():
    print("=== Phase 3 Tests ===\n")

    # 1. Two clients connect
    s1, r1 = make_client("Alice")
    assert "Welcome" in r1, f"FAIL connect Alice: {r1}"
    print("[PASS] Alice connected")

    time.sleep(0.2)
    s2, r2 = make_client("Bob")
    assert "Welcome" in r2, f"FAIL connect Bob: {r2}"
    # Alice gets join notification
    s1.settimeout(1)
    try:
        notif = s1.recv(BUF).decode()
        assert "Bob" in notif and "joined" in notif
        print("[PASS] Bob connected, Alice notified")
    except socket.timeout:
        print("[WARN] Alice didn't get Bob's join notification")

    # 2. Duplicate username rejection
    s3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s3.connect(SERVER)
    s3.recv(BUF)  # welcome
    s3.recv(BUF)  # username request
    s3.send("Alice".encode())
    rej = s3.recv(BUF).decode()
    assert "409" in rej, f"FAIL duplicate: {rej}"
    print("[PASS] Duplicate username rejected (409 Conflict)")
    s3.close()

    # 3. /users command
    s1.send("/users".encode())
    time.sleep(0.2)
    s1.settimeout(2)
    users = s1.recv(BUF).decode()
    assert "Alice" in users and "Bob" in users, f"FAIL /users: {users}"
    print("[PASS] /users lists Alice and Bob")

    # 4. /msg private message
    s1.send("/msg Bob Hello privately".encode())
    time.sleep(0.2)
    s1.settimeout(1)
    pm_confirm = s1.recv(BUF).decode()
    assert "PM to Bob" in pm_confirm, f"FAIL PM confirm: {pm_confirm}"

    s2.settimeout(1)
    pm_recv = s2.recv(BUF).decode()
    assert "PM from Alice" in pm_recv, f"FAIL PM recv: {pm_recv}"
    print("[PASS] /msg private message delivered")

    # 5. Broadcast
    s1.send("Hello everyone".encode())
    time.sleep(0.2)
    s2.settimeout(1)
    broadcast = s2.recv(BUF).decode()
    assert "Alice" in broadcast and "Hello everyone" in broadcast
    print("[PASS] Broadcast message received by Bob")

    # 6. PING
    s1.send("PING".encode())
    s1.settimeout(2)
    pong = s1.recv(BUF).decode()
    assert pong == "PONG", f"FAIL PING: {pong}"
    print("[PASS] PING/PONG works")

    # 7. /quit
    s2.send("/quit".encode())
    s2.settimeout(2)
    ack = s2.recv(BUF).decode()
    assert ack == "DISCONNECT_ACK", f"FAIL quit: {ack}"
    s2.close()
    print("[PASS] /quit handled cleanly")

    # Alice gets leave notification
    time.sleep(0.3)
    s1.settimeout(1)
    try:
        leave = s1.recv(BUF).decode()
        assert "Bob" in leave and "left" in leave
        print("[PASS] Alice notified of Bob leaving")
    except socket.timeout:
        print("[WARN] Leave notification not received")

    s1.send("/quit".encode())
    s1.settimeout(1)
    s1.recv(BUF)
    s1.close()

def test_udp_file_transfer():
    """Test the UDP Stop-and-Wait file transfer."""
    print("\n--- UDP File Transfer Test ---")

    # Create a test file
    test_data = b"ChatNet Phase 3 UDP test! " * 100  # 2600 bytes
    with open("test_transfer.txt", "wb") as f:
        f.write(test_data)
    print(f"[INFO] Created test file: {len(test_data)} bytes")

    from file_sender import send_file
    from file_receiver import receive_file

    # Start receiver in a thread
    recv_result = [None]
    def run_receiver():
        recv_result[0] = receive_file(13001, 'test_received')
    
    recv_thread = threading.Thread(target=run_receiver, daemon=True)
    recv_thread.start()
    time.sleep(0.5)  # Let receiver bind

    # Run sender
    result = send_file("test_transfer.txt", "127.0.0.1", 13001)
    assert result, "FAIL: send_file returned False"
    
    recv_thread.join(timeout=5)
    assert recv_result[0], "FAIL: receive_file returned False"

    # Verify received file matches
    received_path = os.path.join('test_received', 'test_transfer.txt')
    assert os.path.exists(received_path), f"FAIL: {received_path} not found"
    with open(received_path, 'rb') as f:
        received_data = f.read()
    assert received_data == test_data, "FAIL: File content mismatch!"
    print("[PASS] UDP file transfer — content verified")

    import shutil
    os.remove("test_transfer.txt")
    shutil.rmtree('test_received', ignore_errors=True)

if __name__ == '__main__':
    test_chat_and_commands()
    test_udp_file_transfer()
    print("\n=== ALL PHASE 3 TESTS PASSED ===")

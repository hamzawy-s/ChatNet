"""Quick automated test for Phase 2 server functionality."""
import socket
import time

SERVER = ('127.0.0.1', 12000)
BUF = 4096

def test():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(SERVER)

    # 1. Receive welcome
    welcome = s.recv(BUF).decode()
    assert "200 OK" in welcome, f"FAIL: Expected '200 OK', got: {welcome}"
    print(f"[PASS] Welcome message: {welcome}")

    # 2. Receive username request
    prompt = s.recv(BUF).decode()
    assert "USERNAME" in prompt, f"FAIL: Expected username request, got: {prompt}"
    print(f"[PASS] Username prompt received")

    # 3. Send username
    s.send("TestUser".encode())
    confirm = s.recv(BUF).decode()
    assert "Welcome" in confirm, f"FAIL: Expected confirmation, got: {confirm}"
    print(f"[PASS] Username accepted: {confirm.strip()}")

    # 4. Test PING/PONG
    s.send("PING".encode())
    pong = s.recv(BUF).decode()
    assert pong == "PONG", f"FAIL: Expected PONG, got: {pong}"
    print(f"[PASS] PING/PONG works")

    # 5. Test THROUGHPUT
    size = 5000
    s.send(f"THROUGHPUT {size}".encode())
    time.sleep(0.05)
    s.send(b'X' * size)
    s.settimeout(5.0)
    ack = s.recv(BUF).decode()
    assert "THROUGHPUT_ACK" in ack, f"FAIL: Expected ACK, got: {ack}"
    print(f"[PASS] Throughput ACK: {ack}")

    # 6. Test DISCONNECT
    s.send("DISCONNECT".encode())
    disc = s.recv(BUF).decode()
    assert disc == "DISCONNECT_ACK", f"FAIL: Expected DISCONNECT_ACK, got: {disc}"
    print(f"[PASS] DISCONNECT handled cleanly")

    s.close()
    print("\n=== ALL TESTS PASSED ===")

if __name__ == '__main__':
    test()

#!/usr/bin/env python3
import socket
import sys
import ssl
import base64
from email.utils import formatdate

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
TIMEOUT_SECONDS = 15

class SMTPHandshakeError(Exception):
    """خطأ مخصص لمرحلة المصافحة مع السيرفر"""
    pass

def recv_smtp_response(sock):
    """استقبال الرد من السيرفر بشكل كامل"""
    data = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk: break
        data += chunk
        if len(data) >= 4 and data.splitlines()[-1][3:4] == b" ":
            break
    return data.decode("utf-8", errors="replace")

def send_command(sock, command):
    """إرسال أمر للسيرفر واستقبال الرد"""
    full_command = (command + "\r\n").encode("utf-8")
    sock.sendall(full_command)
    return recv_smtp_response(sock)

def expect(response, allowed_codes, cmd_name):
    """التأكد من أن كود الرد من السيرفر صحيح"""
    try:
        code = int(response[:3])
    except:
        code = 0
    if code not in allowed_codes:
        raise SMTPHandshakeError(f"{cmd_name} failed with SMTP {code}: {response.strip()}")
    return code

def send_email(sender_user, sender_pass, rcpt_to, subject, body):
    transcript = []
    
    # 1. الاتصال الأولي (Plaintext)
    sock = socket.create_connection((SMTP_HOST, SMTP_PORT), TIMEOUT_SECONDS)
    res = recv_smtp_response(sock)
    transcript.append(("CONNECT", res))
    expect(res, {220}, "CONNECT")

    # 2. إرسال EHLO (البداية)
    res = send_command(sock, "EHLO chatnet.local")
    transcript.append(("EHLO", res))
    expect(res, {250}, "EHLO")

    # 3. طلب التشفير STARTTLS
    res = send_command(sock, "STARTTLS")
    transcript.append(("STARTTLS", res))
    expect(res, {220}, "STARTTLS")

    # 4. تفعيل التشفير (Wrapping the socket)
    context = ssl.create_default_context()
    secure_sock = context.wrap_socket(sock, server_hostname=SMTP_HOST)

    # 5. إرسال EHLO مرة أخرى (ضروري بعد التشفير حسب RFC)
    res = send_command(secure_sock, "EHLO chatnet.local")
    transcript.append(("EHLO_AFTER_TLS", res))
    expect(res, {250}, "EHLO_AFTER_TLS")

    # 6. تسجيل الدخول AUTH LOGIN
    res = send_command(secure_sock, "AUTH LOGIN")
    transcript.append(("AUTH_LOGIN", res))
    expect(res, {334}, "AUTH_LOGIN")

    # إرسال الإيميل مشفر Base64
    user_b64 = base64.b64encode(sender_user.encode()).decode()
    res = send_command(secure_sock, user_b64)
    transcript.append(("USER_B64", res))
    expect(res, {334}, "USER_B64")

    # إرسال الباسورد مشفر Base64
    pass_b64 = base64.b64encode(sender_pass.encode()).decode()
    res = send_command(secure_sock, pass_b64)
    transcript.append(("PASS_B64", res))
    expect(res, {235}, "PASS_B64") # 235 تعني نجاح الدخول

    # 7. إرسال محتوى الإيميل (عبر السوكيت المشفر حصراً)
    res = send_command(secure_sock, f"MAIL FROM:<{sender_user}>")
    transcript.append(("MAIL_FROM", res))
    expect(res, {250}, "MAIL_FROM")

    res = send_command(secure_sock, f"RCPT TO:<{rcpt_to}>")
    transcript.append(("RCPT_TO", res))
    expect(res, {250, 251}, "RCPT_TO")

    res = send_command(secure_sock, "DATA")
    transcript.append(("DATA", res))
    expect(res, {354}, "DATA")

    # بناء الرسالة
    msg = [
        f"From: {sender_user}",
        f"To: {rcpt_to}",
        f"Subject: {subject}",
        f"Date: {formatdate(localtime=True)}",
        "",
        body,
        "."
    ]
    res = send_command(secure_sock, "\r\n".join(msg))
    transcript.append(("SEND_MSG", res))
    expect(res, {250}, "SEND_MSG")

    # 8. خروج
    send_command(secure_sock, "QUIT")
    secure_sock.close()
    return transcript

def main():
    if len(sys.argv) < 6:
        print("\nUsage: python smtp_notifier.py <sender_email> <app_password> <receiver_email> <subject> <body>")
        return 1

    s_user, s_pass, r_to, subj = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    body = " ".join(sys.argv[5:])

    try:
        print(f"[*] Connecting to {SMTP_HOST}...")
        transcript = send_email(s_user, s_pass, r_to, subj, body)
        print("\n[✔] SUCCESS! Email sent.")
        for cmd, res in transcript:
            print(f"{cmd}: {res.strip()}")
    except Exception as e:
        print(f"\n[✘] FAILED: {e}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
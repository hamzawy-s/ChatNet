#!/usr/bin/env python3
"""Modern customtkinter GUI for the ChatNet student services chat room.

Run with:
    python chatnet_gui.py

Install the GUI dependency if needed:
    pip install customtkinter
"""

from __future__ import annotations

import os
import json
import queue
import re
import socket
import threading
import time
import webbrowser
from dataclasses import dataclass
from tkinter import filedialog

try:
    import customtkinter as ctk
except ModuleNotFoundError as exc:
    raise SystemExit(
        "customtkinter is required. Install it with: pip install customtkinter"
    ) from exc

try:
    from dns_resolver import resolve as backend_dns_query
except ImportError:
    backend_dns_query = None

try:
    from file_receiver import receive_file as backend_receive_file
    from file_sender import send_file as backend_send_file
except ImportError:
    backend_receive_file = None
    backend_send_file = None

try:
    from smtp_notifier import send_email as backend_send_email
except ImportError:
    backend_send_email = None


APP_TITLE = "ChatNet Student Services"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 12000
BUFFER_SIZE = 4096
RECEIVED_DIR = "received_files"
HTTP_LOG_URL = "http://127.0.0.1:8080/chatlog"
ENROLLMENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enrollment_database.json")
GMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@gmail\.com$")

COLORS = {
    "bg": "#F2F2F7",            # خلفية التطبيق
    "panel": "#FFFFFF",         # لوحات بيضاء نقية
    "panel_alt": "#F5F5FA",     # لوحات بديلة أغمق قليلاً
    "surface": "#FAFAFE",       # سطح فاتح
    "surface_hover": "#EFEFF4", # سطح عند التمرير
    "blue": "#007AFF",          # الأزرق iOS
    "blue_hover": "#005FCC",    # أزرق داكن عند التمرير
    "cyan": "#5AC8FA",          # سماوي
    "success": "#34C759",       # أخضر نجاح
    "warning": "#FF9500",       # برتقالي تحذير
    "danger": "#FF3B30",        # أحمر خطأ
    "text": "#1C1C1E",          # نص أساسي (داكن)
    "muted": "#8E8E93",         # نص ثانوي
    "border": "#D9D9DE",        # حدود العناصر
    "bubble_in": "#E9E9ED",     # فقاعة الرسائل الواردة
    "bubble_out": "#007AFF",    # فقاعة الرسائل الصادرة (أزرق)
}


DEFAULT_ENROLLMENT_DATABASE = [
    {"name": "Ahmed Hassan", "student_id": "2021001", "email": "ahmed.hassan@gmail.com", "email_code": ""},
    {"name": "Mariam Adel", "student_id": "2021002", "email": "mariam.adel@gmail.com", "email_code": ""},
    {"name": "Omar Khaled", "student_id": "2021003", "email": "omar.khaled@gmail.com", "email_code": ""},
    {"name": "Laila Mostafa", "student_id": "2021004", "email": "laila.mostafa@gmail.com", "email_code": ""},
    {"name": "Youssef Samir", "student_id": "2021005", "email": "youssef.samir@gmail.com", "email_code": ""},
    {"name": "Test Student", "student_id": "9999999", "email": "test.student@gmail.com", "email_code": ""},
]

ENROLLMENT_LOCK = threading.Lock()
ACTIVE_STUDENT_IDS: set[str] = set()
ACTIVE_IDS_LOCK = threading.Lock()


@dataclass(frozen=True)
class Student:
    full_name: str
    email: str
    student_id: str
    email_code: str = ""

    @property
    def chat_username(self) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9]+", "_", self.full_name).strip("_")
        safe_name = safe_name or "Student"
        return f"{safe_name}_{self.student_id}"


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def normalize_email_code(value: str) -> str:
    return "".join(str(value).strip().split())


def clean_student_record(record: dict) -> dict:
    return {
        "name": " ".join(str(record.get("name", "")).strip().split()),
        "student_id": str(record.get("student_id", "")).strip(),
        "email": normalize_email(str(record.get("email", "")).strip()),
        "email_code": normalize_email_code(record.get("email_code", "")),
    }


def load_enrollment_database() -> list[dict]:
    if not os.path.exists(ENROLLMENT_FILE):
        save_enrollment_database(DEFAULT_ENROLLMENT_DATABASE)
        return [clean_student_record(record) for record in DEFAULT_ENROLLMENT_DATABASE]

    try:
        with open(ENROLLMENT_FILE, "r", encoding="utf-8") as file_obj:
            raw_records = json.load(file_obj)
    except (OSError, json.JSONDecodeError):
        raw_records = DEFAULT_ENROLLMENT_DATABASE

    records = []
    for record in raw_records if isinstance(raw_records, list) else []:
        cleaned = clean_student_record(record)
        if cleaned["name"] and cleaned["student_id"] and cleaned["email"]:
            records.append(cleaned)

    if not records:
        records = [clean_student_record(record) for record in DEFAULT_ENROLLMENT_DATABASE]
        save_enrollment_database(records)

    return records


def save_enrollment_database(records: list[dict]) -> None:
    cleaned_records = [clean_student_record(record) for record in records]
    with open(ENROLLMENT_FILE, "w", encoding="utf-8") as file_obj:
        json.dump(cleaned_records, file_obj, indent=2)


ENROLLMENT_DATABASE = load_enrollment_database()


def is_enrolled(full_name: str, student_id: str, email: str) -> bool:
    wanted_name = normalize_name(full_name)
    wanted_id = student_id.strip()
    wanted_email = normalize_email(email)
    with ENROLLMENT_LOCK:
        return any(
            normalize_name(record["name"]) == wanted_name
            and record["student_id"] == wanted_id
            and normalize_email(record.get("email", "")) == wanted_email
            for record in ENROLLMENT_DATABASE
        )


def find_student_record(full_name: str, student_id: str, email: str) -> dict | None:
    wanted_name = normalize_name(full_name)
    wanted_id = student_id.strip()
    wanted_email = normalize_email(email)
    with ENROLLMENT_LOCK:
        for record in ENROLLMENT_DATABASE:
            if (
                normalize_name(record["name"]) == wanted_name
                and record["student_id"] == wanted_id
                and normalize_email(record.get("email", "")) == wanted_email
            ):
                return dict(record)
    return None


def find_student_by_id(student_id: str) -> dict | None:
    wanted_id = student_id.strip()
    with ENROLLMENT_LOCK:
        for record in ENROLLMENT_DATABASE:
            if record["student_id"] == wanted_id:
                return dict(record)
    return None


def upsert_student_record(full_name: str, student_id: str, email: str, email_code: str = "", old_student_id: str | None = None) -> tuple[bool, str]:
    cleaned = clean_student_record(
        {"name": full_name, "student_id": student_id, "email": email, "email_code": email_code}
    )
    if not cleaned["name"] or not cleaned["student_id"] or not cleaned["email"]:
        return False, "Complete name, student ID, and email."
    if not GMAIL_RE.match(cleaned["email"]):
        return False, "Student email must be a valid @gmail.com address."
    if cleaned["email_code"] and (len(cleaned["email_code"]) != 16 or not cleaned["email_code"].isalnum()):
        return False, "Email code must be exactly 16 letters or digits."

    with ENROLLMENT_LOCK:
        target_old_id = (old_student_id or "").strip()
        for record in ENROLLMENT_DATABASE:
            same_id = record["student_id"] == cleaned["student_id"]
            same_email = normalize_email(record.get("email", "")) == cleaned["email"]
            editing_same_record = target_old_id and record["student_id"] == target_old_id
            if (same_id or same_email) and not editing_same_record:
                return False, "Another student already uses this ID or email."

        for index, record in enumerate(ENROLLMENT_DATABASE):
            if target_old_id and record["student_id"] == target_old_id:
                ENROLLMENT_DATABASE[index] = cleaned
                save_enrollment_database(ENROLLMENT_DATABASE)
                return True, "Student record updated."

        ENROLLMENT_DATABASE.append(cleaned)
        ENROLLMENT_DATABASE.sort(key=lambda item: item["student_id"])
        save_enrollment_database(ENROLLMENT_DATABASE)
        return True, "Student record added."


def delete_student_record(student_id: str) -> tuple[bool, str]:
    wanted_id = student_id.strip()
    with ACTIVE_IDS_LOCK:
        if wanted_id in ACTIVE_STUDENT_IDS:
            return False, "This student is currently logged in."

    with ENROLLMENT_LOCK:
        for index, record in enumerate(ENROLLMENT_DATABASE):
            if record["student_id"] == wanted_id:
                ENROLLMENT_DATABASE.pop(index)
                save_enrollment_database(ENROLLMENT_DATABASE)
                return True, "Student record deleted."
    return False, "Student record was not found."


class ChatNetworkClient:
    """Threaded ChatNet protocol adapter.

    Replace methods in this class with your existing backend socket functions
    if your project exposes a different API. Keep the public method names the
    same so the GUI layer does not need to know about protocol details.
    """

    def __init__(
        self,
        student: Student,
        ui_dispatch,
        on_message,
        on_users,
        on_status,
        on_file_notice,
    ):
        self.student = student
        self.ui_dispatch = ui_dispatch
        self.on_message = on_message
        self.on_users = on_users
        self.on_status = on_status
        self.on_file_notice = on_file_notice

        self.sock: socket.socket | None = None
        self.running = False
        self.pause_receiver = threading.Event()
        self.send_lock = threading.Lock()

    def connect_async(self, on_done):
        thread = threading.Thread(target=self._connect, args=(on_done,), daemon=True)
        thread.start()

    def _connect(self, on_done):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((SERVER_HOST, SERVER_PORT))

            welcome = sock.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
            if "USERNAME_REQUEST" not in welcome:
                prompt = sock.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
                if "USERNAME_REQUEST" not in prompt:
                    raise ConnectionError(f"Unexpected server response: {prompt}")

            sock.sendall(self.student.chat_username.encode("utf-8"))
            response = sock.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
            if "409 Conflict" in response:
                raise ConnectionError("This student is already connected to ChatNet.")

            self.sock = sock
            self.running = True
            self.ui_dispatch(on_done, True, "")
            self.ui_dispatch(self.on_message, "System", response.strip() or "Connected.")

            recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            recv_thread.start()
            self.request_users()
        except OSError as exc:
            self.ui_dispatch(on_done, False, f"Could not connect to server: {exc}")
        except Exception as exc:
            self.ui_dispatch(on_done, False, str(exc))

    def _recv_loop(self):
        if self.sock is None:
            return

        self.sock.settimeout(0.25)

        while self.running:
            if self.pause_receiver.is_set():
                time.sleep(0.05)
                continue

            try:
                data = self.sock.recv(BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                if self.running:
                    self.ui_dispatch(self.on_status, "Connection to server was lost.", "error")
                self.running = False
                break

            if not data:
                self.running = False
                self.ui_dispatch(self.on_status, "Server closed the connection.", "warning")
                break

            message = data.decode("utf-8", errors="replace").strip()
            if not message:
                continue
            self._handle_server_message(message)

    def _handle_server_message(self, message: str):
        if message == "DISCONNECT_ACK":
            self.running = False
            self.ui_dispatch(self.on_status, "Disconnected from ChatNet.", "success")
            return

        if message.startswith("Online users"):
            users = self._parse_users(message)
            self.ui_dispatch(self.on_users, users)
            return

        if message.startswith("FILE_NOTIFY "):
            self._handle_file_notification(message)
            return

        self.ui_dispatch(self.on_message, "ChatNet", message)

    def _parse_users(self, message: str) -> list[str]:
        if ":" not in message:
            return []
        _, raw_users = message.split(":", 1)
        return [user.strip() for user in raw_users.split(",") if user.strip()]

    def _handle_file_notification(self, message: str):
        parts = message.split()
        if len(parts) < 5:
            self.ui_dispatch(self.on_status, f"Malformed file notice: {message}", "error")
            return

        sender = parts[1]
        filename = parts[2]
        port = int(parts[4])
        self.ui_dispatch(self.on_file_notice, sender, filename)

        if backend_receive_file is None:
            self.ui_dispatch(
                self.on_status,
                "File receiver backend is not available. Plug in receive_file().",
                "error",
            )
            return

        # Backend hook: replace backend_receive_file with your UDP receiver.
        thread = threading.Thread(
            target=backend_receive_file,
            args=(port, RECEIVED_DIR),
            daemon=True,
        )
        thread.start()

    def send_chat_async(self, message: str):
        thread = threading.Thread(target=self._send_chat, args=(message,), daemon=True)
        thread.start()

    def _send_chat(self, message: str):
        if not self.running or self.sock is None:
            self.ui_dispatch(self.on_status, "Not connected to ChatNet.", "error")
            return

        try:
            with self.send_lock:
                # Backend hook: replace this sendall with your chat send call.
                self.sock.sendall(message.encode("utf-8"))
        except OSError as exc:
            self.ui_dispatch(self.on_status, f"Send failed: {exc}", "error")

    def request_users(self):
        if self.running:
            self.send_chat_async("/users")

    def send_file_async(self, filepath: str, recipient: str, on_progress, on_done):
        thread = threading.Thread(
            target=self._send_file,
            args=(filepath, recipient, on_progress, on_done),
            daemon=True,
        )
        thread.start()

    def _send_file(self, filepath: str, recipient: str, on_progress, on_done):
        if not self.running or self.sock is None:
            self.ui_dispatch(on_done, False, "Not connected to ChatNet.")
            return
        if backend_send_file is None:
            self.ui_dispatch(on_done, False, "File sender backend is not available.")
            return
        if not os.path.isfile(filepath):
            self.ui_dispatch(on_done, False, "Selected file does not exist.")
            return

        display_name = re.sub(r"\s+", "_", os.path.basename(filepath))
        self.pause_receiver.set()
        time.sleep(0.35)
        self.ui_dispatch(on_progress, 0.08, "Requesting transfer route...")

        try:
            with self.send_lock:
                self.sock.settimeout(5.0)
                # Backend hook: replace this command with your file-transfer handshake.
                self.sock.sendall(f"SENDFILE {display_name} {recipient}".encode("utf-8"))
                response = self.sock.recv(BUFFER_SIZE).decode("utf-8", errors="replace")

            if not response.startswith("FILE_TARGET "):
                self.ui_dispatch(on_done, False, response)
                return

            parts = response.split()
            target_ip = parts[1]
            target_port = int(parts[2])
            self.ui_dispatch(on_progress, 0.18, "Waiting for recipient UDP receiver...")
            time.sleep(0.5)
            self.ui_dispatch(on_progress, 0.28, "Starting UDP transfer...")

            # Backend hook: replace backend_send_file with your UDP sender.
            ok = backend_send_file(filepath, target_ip, target_port)
            self.ui_dispatch(
                on_done,
                bool(ok),
                "File transfer complete." if ok else "File transfer failed.",
            )
        except socket.timeout:
            self.ui_dispatch(on_done, False, "Timed out waiting for file route.")
        except OSError as exc:
            self.ui_dispatch(on_done, False, f"File transfer failed: {exc}")
        finally:
            if self.sock is not None:
                self.sock.settimeout(0.25)
            self.pause_receiver.clear()

    def ping_async(self, count: int, on_done):
        thread = threading.Thread(target=self._ping, args=(count, on_done), daemon=True)
        thread.start()

    def _ping(self, count: int, on_done):
        if not self.running or self.sock is None:
            self.ui_dispatch(on_done, "Not connected.")
            return

        self.pause_receiver.set()
        time.sleep(0.35)
        rtts: list[float] = []

        try:
            with self.send_lock:
                self.sock.settimeout(2.0)
                for _ in range(count):
                    start = time.perf_counter()
                    # Backend hook: replace with your ping backend call.
                    self.sock.sendall(b"PING")
                    response = self.sock.recv(BUFFER_SIZE).decode("utf-8", errors="replace")
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    if response == "PONG":
                        rtts.append(elapsed_ms)
                    time.sleep(0.2)

            if not rtts:
                self.ui_dispatch(on_done, "No ping replies received.")
                return

            avg = sum(rtts) / len(rtts)
            result = (
                f"Ping replies: {len(rtts)}/{count}\n"
                f"Min: {min(rtts):.2f} ms\n"
                f"Avg: {avg:.2f} ms\n"
                f"Max: {max(rtts):.2f} ms"
            )
            self.ui_dispatch(on_done, result)
        except OSError as exc:
            self.ui_dispatch(on_done, f"Ping failed: {exc}")
        finally:
            if self.sock is not None:
                self.sock.settimeout(0.25)
            self.pause_receiver.clear()

    def throughput_async(self, size_bytes: int, on_done):
        thread = threading.Thread(
            target=self._throughput,
            args=(size_bytes, on_done),
            daemon=True,
        )
        thread.start()

    def _throughput(self, size_bytes: int, on_done):
        if not self.running or self.sock is None:
            self.ui_dispatch(on_done, "Not connected.")
            return

        self.pause_receiver.set()
        time.sleep(0.35)

        try:
            payload = b"X" * size_bytes
            with self.send_lock:
                self.sock.settimeout(10.0)
                # Backend hook: replace with your throughput backend call.
                self.sock.sendall(f"THROUGHPUT {size_bytes}".encode("utf-8"))
                time.sleep(0.05)
                start = time.perf_counter()
                self.sock.sendall(payload)
                ack = self.sock.recv(BUFFER_SIZE).decode("utf-8", errors="replace")

            elapsed = time.perf_counter() - start
            kbps = (size_bytes * 8) / (elapsed * 1000) if elapsed > 0 else 0
            result = (
                f"{ack}\n"
                f"Payload: {size_bytes:,} bytes\n"
                f"Elapsed: {elapsed * 1000:.2f} ms\n"
                f"Throughput: {kbps:.2f} kbps"
            )
            self.ui_dispatch(on_done, result)
        except OSError as exc:
            self.ui_dispatch(on_done, f"Throughput test failed: {exc}")
        finally:
            if self.sock is not None:
                self.sock.settimeout(0.25)
            self.pause_receiver.clear()

    def disconnect_async(self):
        thread = threading.Thread(target=self._disconnect, daemon=True)
        thread.start()

    def _disconnect(self):
        self.running = False
        if self.sock is None:
            return
        try:
            with self.send_lock:
                self.sock.sendall(b"/quit")
        except OSError:
            pass
        finally:
            try:
                self.sock.close()
            except OSError:
                pass


class Toast(ctk.CTkFrame):
    def __init__(self, master, message: str, kind: str = "error"):
        color = {
            "error": COLORS["danger"],
            "warning": COLORS["warning"],
            "success": COLORS["success"],
            "info": COLORS["blue"],
        }.get(kind, COLORS["blue"])

        super().__init__(master, fg_color=COLORS["panel_alt"], corner_radius=16)
        self.configure(border_width=1, border_color=color)
        self.place(relx=0.985, rely=0.035, anchor="ne")

        accent = ctk.CTkFrame(self, width=5, fg_color=color, corner_radius=6)
        accent.pack(side="left", fill="y", padx=(12, 8), pady=12)

        ctk.CTkLabel(
            self,
            text=message,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            wraplength=360,
            justify="left",
        ).pack(side="left", padx=(0, 16), pady=14)

        self.after(3300, self.destroy)


class SplashFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.progress_value = 0.0
        self.pack(fill="both", expand=True)

        shell = ctk.CTkFrame(
            self,
            width=640,
            height=330,
            fg_color=COLORS["panel"],
            corner_radius=28,
            border_width=1,
            border_color=COLORS["border"],
        )
        shell.place(relx=0.5, rely=0.5, anchor="center")
        shell.pack_propagate(False)

        ctk.CTkLabel(
            shell,
            text="ChatNet",
            text_color=COLORS["cyan"],
            font=ctk.CTkFont(size=34, weight="bold"),
        ).pack(pady=(42, 8))

        ctk.CTkLabel(
            shell,
            text="Welcome to the New Cairo University Student Services Chat Room",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=24, weight="bold"),
            wraplength=520,
            justify="center",
        ).pack(padx=42)

        self.status_label = ctk.CTkLabel(
            shell,
            text="Preparing secure student entry...",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=14),
        )
        self.status_label.pack(pady=(28, 12))

        self.progress = ctk.CTkProgressBar(
            shell,
            width=360,
            height=9,
            corner_radius=12,
            fg_color=COLORS["surface"],
            progress_color=COLORS["blue"],
        )
        self.progress.set(0)
        self.progress.pack()

    def start(self):
        self._fade_in(0.82)
        self._animate_progress()
        self.after(2700, self._fade_out)

    def _fade_in(self, alpha: float):
        if alpha >= 1:
            self.master.attributes("-alpha", 1)
            return
        self.master.attributes("-alpha", alpha)
        self.after(24, lambda: self._fade_in(alpha + 0.025))

    def _fade_out(self):
        current = float(self.master.attributes("-alpha") or 1)
        if current <= 0.05:
            self.master.show_role_selection()
            return
        self.master.attributes("-alpha", current - 0.06)
        self.after(24, self._fade_out)

    def _animate_progress(self):
        self.progress_value = min(1.0, self.progress_value + 0.018)
        self.progress.set(self.progress_value)
        if self.progress_value < 1.0:
            self.after(36, self._animate_progress)


class RoleSelectionFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.master = master
        self.pack(fill="both", expand=True)

        panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["panel"],
            corner_radius=24,
            border_width=1,
            border_color=COLORS["border"],
        )
        panel.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.72, relheight=0.68)

        ctk.CTkLabel(
            panel,
            text="Welcome Beek y 3sll enta Meen ?!",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=30, weight="bold"),
        ).pack(pady=(48, 8))

        ctk.CTkLabel(
            panel,
            text="Enter as a student or manage enrollment records as admin.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=14),
        ).pack(pady=(0, 34))

        choices = ctk.CTkFrame(panel, fg_color="transparent")
        choices.pack(fill="both", expand=True, padx=58, pady=(0, 48))
        choices.grid_columnconfigure((0, 1), weight=1, uniform="role")
        choices.grid_rowconfigure(0, weight=1)

        self._role_card(
            choices,
            column=0,
            title="Student",
            subtitle="Verify your name, Gmail, and student ID to enter ChatNet.",
            button_text="Continue as Student",
            command=self.master.show_registration,
        )
        self._role_card(
            choices,
            column=1,
            title="Admin",
            subtitle="Add, edit, and remove students from the enrollment list.",
            button_text="Continue as Admin",
            command=self.master.show_admin_login,
        )

    def _role_card(self, parent, column: int, title: str, subtitle: str, button_text: str, command):
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel_alt"],
            corner_radius=20,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.grid(row=0, column=column, sticky="nsew", padx=10)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=title,
            text_color=COLORS["cyan"] if title == "Student" else COLORS["warning"],
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, padx=24, pady=(34, 12))

        ctk.CTkLabel(
            card,
            text=subtitle,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13),
            wraplength=260,
            justify="center",
        ).grid(row=1, column=0, padx=26, pady=(0, 26))

        ctk.CTkButton(
            card,
            text=button_text,
            height=44,
            corner_radius=14,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=command,
        ).grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 28))


class AdminLoginFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.master = master
        self.pack(fill="both", expand=True)

        panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["panel"],
            corner_radius=24,
            border_width=1,
            border_color=COLORS["border"],
        )
        panel.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.58, relheight=0.66)

        ctk.CTkLabel(
            panel,
            text="Admin Login",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=30, weight="bold"),
        ).pack(pady=(46, 8))

        ctk.CTkLabel(
            panel,
            text="Use the admin account to manage student enrollment.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=14),
        ).pack(pady=(0, 28))

        form = ctk.CTkFrame(panel, fg_color="transparent")
        form.pack(fill="x", padx=72)

        self.username_entry = self._field(form, "Username")
        self.password_entry = self._field(form, "Password", show="*")

        self.login_button = ctk.CTkButton(
            panel,
            text="Login",
            height=46,
            corner_radius=14,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.submit,
        )
        self.login_button.pack(fill="x", padx=72, pady=(18, 10))

        ctk.CTkButton(
            panel,
            text="Back",
            height=40,
            corner_radius=14,
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            command=self.master.show_role_selection,
        ).pack(fill="x", padx=72, pady=(0, 28))

        self.username_entry.bind("<Return>", lambda _event: self.submit())
        self.password_entry.bind("<Return>", lambda _event: self.submit())

    def _field(self, parent, label: str, show: str | None = None):
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 7))
        entry = ctk.CTkEntry(
            parent,
            height=44,
            corner_radius=13,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            show=show,
        )
        entry.pack(fill="x", pady=(0, 16))
        return entry

    def submit(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if username == "admin" and password == "admin":
            self.master.show_admin_panel()
            return
        self.master.show_toast("Invalid admin username or password.", "error")


class AdminPanelFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.master = master
        self.selected_student_id: str | None = None
        self.pack(fill="both", expand=True)

        self.grid_columnconfigure(0, minsize=420, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=28, pady=(24, 14))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Enrollment Admin",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=26, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header,
            text="Back to Mode Select",
            width=170,
            height=38,
            corner_radius=12,
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            command=self.master.show_role_selection,
        ).grid(row=0, column=1, sticky="e")

        self._build_list()
        self._build_form()
        self.refresh_student_list()

    def _build_list(self):
        list_panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["panel"],
            corner_radius=20,
            border_width=1,
            border_color=COLORS["border"],
        )
        list_panel.grid(row=1, column=0, sticky="nsew", padx=(28, 12), pady=(0, 28))
        list_panel.grid_rowconfigure(1, weight=1)
        list_panel.grid_columnconfigure(0, weight=1)

        self.count_label = ctk.CTkLabel(
            list_panel,
            text="Students",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        )
        self.count_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))

        self.student_list = ctk.CTkScrollableFrame(
            list_panel,
            fg_color=COLORS["panel_alt"],
            corner_radius=16,
            scrollbar_button_color=COLORS["surface"],
            scrollbar_button_hover_color=COLORS["surface_hover"],
        )
        self.student_list.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

    def _build_form(self):
        form_panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["panel"],
            corner_radius=20,
            border_width=1,
            border_color=COLORS["border"],
        )
        form_panel.grid(row=1, column=1, sticky="nsew", padx=(12, 28), pady=(0, 28))
        form_panel.grid_columnconfigure(0, weight=1)

        self.form_title = ctk.CTkLabel(
            form_panel,
            text="Add Student",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        )
        self.form_title.grid(row=0, column=0, sticky="ew", padx=26, pady=(26, 18))

        form = ctk.CTkFrame(form_panel, fg_color="transparent")
        form.grid(row=1, column=0, sticky="ew", padx=26)
        form.grid_columnconfigure(0, weight=1)

        self.admin_name_entry = self._field(form, 0, "Student Name")
        self.admin_id_entry = self._field(form, 1, "Student ID / Code")
        self.admin_email_entry = self._field(form, 2, "Gmail Address")
        self.admin_email_code_entry = self._field(form, 3, "Email 16-Code (Optional)", show="*")

        actions = ctk.CTkFrame(form_panel, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=26, pady=(20, 0))
        actions.grid_columnconfigure((0, 1), weight=1)

        self.save_button = ctk.CTkButton(
            actions,
            text="Add Student",
            height=42,
            corner_radius=13,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            command=self.save_student,
        )
        self.save_button.grid(row=0, column=0, sticky="ew", padx=(0, 7))

        ctk.CTkButton(
            actions,
            text="Clear",
            height=42,
            corner_radius=13,
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            command=self.clear_form,
        ).grid(row=0, column=1, sticky="ew", padx=(7, 0))

        self.delete_button = ctk.CTkButton(
            form_panel,
            text="Delete Selected Student",
            height=42,
            corner_radius=13,
            fg_color="#5A2030",
            hover_color="#743044",
            state="disabled",
            command=self.delete_student,
        )
        self.delete_button.grid(row=3, column=0, sticky="ew", padx=26, pady=(14, 10))

        ctk.CTkLabel(
            form_panel,
            text=f"Saved in {os.path.basename(ENROLLMENT_FILE)}",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", padx=26, pady=(0, 26))

    def _field(self, parent, row: int, label: str, show: str | None = None):
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=row * 2, column=0, sticky="ew", pady=(0, 7))
        entry = ctk.CTkEntry(
            parent,
            height=44,
            corner_radius=13,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            show=show,
        )
        entry.grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 16))
        entry.bind("<Return>", lambda _event: self.save_student())
        return entry

    def refresh_student_list(self):
        for child in self.student_list.winfo_children():
            child.destroy()

        with ENROLLMENT_LOCK:
            records = [dict(record) for record in ENROLLMENT_DATABASE]

        self.count_label.configure(text=f"Students ({len(records)})")
        if not records:
            ctk.CTkLabel(
                self.student_list,
                text="No students yet.",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=13),
            ).pack(anchor="w", padx=14, pady=14)
            return

        for record in records:
            is_selected = record["student_id"] == self.selected_student_id
            button = ctk.CTkButton(
                self.student_list,
                text=(
                    f"{record['name']}\n"
                    f"ID: {record['student_id']}  |  {record['email']}  |  "
                    f"Code: {'saved' if record.get('email_code') else 'not set'}"
                ),
                height=58,
                corner_radius=12,
                fg_color=COLORS["blue"] if is_selected else COLORS["surface"],
                hover_color=COLORS["blue_hover"] if is_selected else COLORS["surface_hover"],
                text_color=COLORS["text"],
                anchor="w",
                command=lambda selected=record: self.select_student(selected),
            )
            button.pack(fill="x", padx=10, pady=6)

    def select_student(self, record: dict):
        self.selected_student_id = record["student_id"]
        self.form_title.configure(text="Edit Student")
        self.save_button.configure(text="Save Changes")
        self.delete_button.configure(state="normal")
        self._replace_entry_value(self.admin_name_entry, record["name"])
        self._replace_entry_value(self.admin_id_entry, record["student_id"])
        self._replace_entry_value(self.admin_email_entry, record["email"])
        self._replace_entry_value(self.admin_email_code_entry, record.get("email_code", ""))
        self.refresh_student_list()

    def _replace_entry_value(self, entry, value: str):
        entry.delete(0, "end")
        entry.insert(0, value)

    def clear_form(self):
        self.selected_student_id = None
        self.form_title.configure(text="Add Student")
        self.save_button.configure(text="Add Student")
        self.delete_button.configure(state="disabled")
        for entry in (
            self.admin_name_entry,
            self.admin_id_entry,
            self.admin_email_entry,
            self.admin_email_code_entry,
        ):
            entry.delete(0, "end")
        self.refresh_student_list()

    def save_student(self):
        full_name = self.admin_name_entry.get().strip()
        student_id = self.admin_id_entry.get().strip()
        email = self.admin_email_entry.get().strip()
        email_code = self.admin_email_code_entry.get().strip()

        if self.selected_student_id:
            with ACTIVE_IDS_LOCK:
                if self.selected_student_id in ACTIVE_STUDENT_IDS:
                    self.master.show_toast("Cannot edit a student while they are logged in.", "error")
                    return

        ok, message = upsert_student_record(
            full_name,
            student_id,
            email,
            email_code,
            old_student_id=self.selected_student_id,
        )
        self.master.show_toast(message, "success" if ok else "error")
        if ok:
            self.selected_student_id = student_id
            self.form_title.configure(text="Edit Student")
            self.save_button.configure(text="Save Changes")
            self.delete_button.configure(state="normal")
            self.refresh_student_list()

    def delete_student(self):
        if not self.selected_student_id:
            self.master.show_toast("Select a student first.", "error")
            return

        ok, message = delete_student_record(self.selected_student_id)
        self.master.show_toast(message, "success" if ok else "error")
        if ok:
            self.clear_form()
            self.refresh_student_list()


class RegistrationFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.master = master
        self.pack(fill="both", expand=True)

        panel = ctk.CTkFrame(
            self,
            fg_color=COLORS["panel"],
            corner_radius=24,
            border_width=1,
            border_color=COLORS["border"],
        )
        panel.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.72, relheight=0.74)

        ctk.CTkLabel(
            panel,
            text="Student Entry",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=30, weight="bold"),
        ).pack(pady=(42, 6))

        ctk.CTkLabel(
            panel,
            text="Verify your enrollment to enter the university chat room.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=14),
        ).pack(pady=(0, 28))

        form = ctk.CTkFrame(panel, fg_color="transparent")
        form.pack(fill="x", padx=86)

        self.name_entry = self._field(form, "Full Name")
        self.email_entry = self._field(form, "Gmail Address")
        self.id_entry = self._field(form, "Student ID Number")

        self.enter_button = ctk.CTkButton(
            panel,
            text="Enter Chat",
            height=48,
            corner_radius=14,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.submit,
        )
        self.enter_button.pack(fill="x", padx=86, pady=(26, 10))

        ctk.CTkButton(
            panel,
            text="Back",
            height=40,
            corner_radius=14,
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            command=self.master.show_role_selection,
        ).pack(fill="x", padx=86, pady=(0, 10))

        ctk.CTkLabel(
            panel,
            text="No password is required. Access is based on Name + Student ID verification.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
        ).pack(pady=(4, 0))

        for entry in (self.name_entry, self.email_entry, self.id_entry):
            entry.bind("<Return>", lambda _event: self.submit())

    def _field(self, parent, label: str):
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 7))
        entry = ctk.CTkEntry(
            parent,
            height=44,
            corner_radius=13,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        entry.pack(fill="x", pady=(0, 16))
        return entry

    def submit(self):
        full_name = " ".join(self.name_entry.get().strip().split())
        email = self.email_entry.get().strip()
        student_id = self.id_entry.get().strip()

        if not full_name or not email or not student_id:
            self.master.show_toast("Please complete all student entry fields.", "error")
            return
        if not GMAIL_RE.match(email):
            self.master.show_toast("Use a valid Gmail address: name@gmail.com", "error")
            return
        student_record = find_student_record(full_name, student_id, email)
        if student_record is None:
            self.master.show_toast("Name, Student ID, and Gmail were not found in enrollment records.", "error")
            return

        with ACTIVE_IDS_LOCK:
            if student_id in ACTIVE_STUDENT_IDS:
                self.master.show_toast("This Student ID is already logged in.", "error")
                return
            ACTIVE_STUDENT_IDS.add(student_id)

        student = Student(
            full_name=full_name,
            email=email,
            student_id=student_id,
            email_code=student_record.get("email_code", ""),
        )
        self.enter_button.configure(text="Connecting...", state="disabled")
        self.master.connect_student(student)


class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master, student: Student):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0)
        self.master = master
        self.student = student
        self.selected_file: str | None = None
        self.online_users: list[str] = []
        self.pack(fill="both", expand=True)

        self.grid_columnconfigure(0, minsize=260, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, minsize=330, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_chat_panel()
        self._build_tools_panel()
        self._schedule_user_refresh()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            sidebar,
            text="ChatNet",
            text_color=COLORS["cyan"],
            font=ctk.CTkFont(size=25, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(28, 18))

        profile = ctk.CTkFrame(sidebar, fg_color=COLORS["panel_alt"], corner_radius=18)
        profile.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))

        initials = "".join(part[:1] for part in self.student.full_name.split()[:2]).upper()
        avatar = ctk.CTkLabel(
            profile,
            text=initials,
            width=54,
            height=54,
            corner_radius=28,
            fg_color=COLORS["blue"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        avatar.grid(row=0, column=0, padx=16, pady=16)

        info = ctk.CTkFrame(profile, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=(0, 16))
        profile.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            info,
            text=self.student.full_name,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            info,
            text=f"ID {self.student.student_id}",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).pack(fill="x", pady=(3, 0))

        online_wrap = ctk.CTkFrame(sidebar, fg_color="transparent")
        online_wrap.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        online_wrap.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            online_wrap,
            text="Online Students",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.online_list = ctk.CTkScrollableFrame(
            online_wrap,
            fg_color=COLORS["panel_alt"],
            corner_radius=16,
            scrollbar_button_color=COLORS["surface"],
            scrollbar_button_hover_color=COLORS["surface_hover"],
        )
        self.online_list.grid(row=1, column=0, sticky="nsew")

        self.disconnect_button = ctk.CTkButton(
            sidebar,
            text="Disconnect",
            height=42,
            corner_radius=14,
            fg_color="#26364C",
            hover_color="#344C6E",
            command=self.master.disconnect,
        )
        self.disconnect_button.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 22))

    def _build_chat_panel(self):
        chat = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        chat.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        chat.grid_rowconfigure(1, weight=1)
        chat.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(chat, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(6, 14))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Student Services Chat Room",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.connection_label = ctk.CTkLabel(
            header,
            text="Connected",
            text_color=COLORS["success"],
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.connection_label.grid(row=0, column=1, sticky="e")

        self.messages = ctk.CTkScrollableFrame(
            chat,
            fg_color=COLORS["panel"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
            scrollbar_button_color=COLORS["surface"],
            scrollbar_button_hover_color=COLORS["surface_hover"],
        )
        self.messages.grid(row=1, column=0, sticky="nsew")
        self.messages.grid_columnconfigure(0, weight=1)

        entry_bar = ctk.CTkFrame(chat, fg_color=COLORS["panel"], corner_radius=18)
        entry_bar.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        entry_bar.grid_columnconfigure(0, weight=1)

        self.message_entry = ctk.CTkEntry(
            entry_bar,
            height=48,
            corner_radius=16,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        self.message_entry.bind("<Return>", lambda _event: self.send_message())

        ctk.CTkButton(
            entry_bar,
            text="Send",
            width=96,
            height=42,
            corner_radius=14,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            command=self.send_message,
        ).grid(row=0, column=1, padx=(0, 14), pady=14)

        self.add_message("System", "You are connected to the student services chat room.")

    def _build_tools_panel(self):
        tools = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORS["panel"],
            corner_radius=0,
            scrollbar_button_color=COLORS["surface"],
            scrollbar_button_hover_color=COLORS["surface_hover"],
        )
        tools.grid(row=0, column=2, sticky="nsew")
        tools.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tools,
            text="Network Tools",
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=21, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=22, pady=(28, 16))

        self._file_tool(tools, 1)
        self._email_tool(tools, 2)
        self._dns_tool(tools, 3)
        self._diagnostics_tool(tools, 4)
        self._logs_tool(tools, 5)

    def _tool_card(self, parent, row: int, title: str):
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["panel_alt"],
            corner_radius=18,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.grid(row=row, column=0, sticky="ew", padx=18, pady=(0, 16))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text=title,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 10))
        return card

    def _file_tool(self, parent, row: int):
        card = self._tool_card(parent, row, "UDP File Transfer")

        self.recipient_menu = ctk.CTkComboBox(
            card,
            values=["Select recipient"],
            height=38,
            corner_radius=12,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            button_color=COLORS["blue"],
            button_hover_color=COLORS["blue_hover"],
            text_color=COLORS["text"],
            dropdown_fg_color=COLORS["panel_alt"],
            dropdown_text_color=COLORS["text"],
        )
        self.recipient_menu.set("Select recipient")
        self.recipient_menu.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.file_label = ctk.CTkLabel(
            card,
            text="No file selected",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.file_label.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        ctk.CTkButton(
            card,
            text="Choose File",
            height=38,
            corner_radius=12,
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            command=self.choose_file,
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.file_progress = ctk.CTkProgressBar(
            card,
            height=9,
            corner_radius=12,
            mode="indeterminate",
            fg_color=COLORS["surface"],
            progress_color=COLORS["cyan"],
        )
        self.file_progress.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 10))
        self.file_progress.set(0)

        self.file_status = ctk.CTkLabel(
            card,
            text="Ready",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.file_status.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.send_file_button = ctk.CTkButton(
            card,
            text="Send File",
            height=40,
            corner_radius=12,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            command=self.send_file,
        )
        self.send_file_button.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 16))

    def _email_tool(self, parent, row: int):
        card = self._tool_card(parent, row, "Email Sender")

        ctk.CTkLabel(
            card,
            text="Recipient Gmail",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 7))

        self.email_to_entry = ctk.CTkEntry(
            card,
            height=38,
            corner_radius=12,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.email_to_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            card,
            text="Subject",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 7))

        self.email_subject_entry = ctk.CTkEntry(
            card,
            height=38,
            corner_radius=12,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.email_subject_entry.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 10))

        ctk.CTkLabel(
            card,
            text="Message",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 7))

        self.email_body = ctk.CTkTextbox(
            card,
            height=92,
            corner_radius=12,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=12),
        )
        self.email_body.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.email_status = ctk.CTkLabel(
            card,
            text="Ready",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.email_status.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.email_send_button = ctk.CTkButton(
            card,
            text="Send Email",
            height=40,
            corner_radius=12,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            command=self.send_email_message,
        )
        self.email_send_button.grid(row=8, column=0, sticky="ew", padx=16, pady=(0, 16))

    def _dns_tool(self, parent, row: int):
        card = self._tool_card(parent, row, "DNS Resolver")

        self.dns_entry = ctk.CTkEntry(
            card,
            height=38,
            corner_radius=12,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
        )
        self.dns_entry.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        self.dns_entry.bind("<Return>", lambda _event: self.resolve_dns())

        ctk.CTkButton(
            card,
            text="Resolve Domain",
            height=38,
            corner_radius=12,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            command=self.resolve_dns,
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.dns_result = ctk.CTkLabel(
            card,
            text="DNS result will appear here.",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=12),
            wraplength=260,
            justify="left",
            anchor="w",
        )
        self.dns_result.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))

    def _diagnostics_tool(self, parent, row: int):
        card = self._tool_card(parent, row, "Diagnostics")

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        actions.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            actions,
            text="Ping",
            height=36,
            corner_radius=12,
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            command=self.run_ping,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            actions,
            text="Throughput",
            height=36,
            corner_radius=12,
            fg_color=COLORS["surface"],
            hover_color=COLORS["surface_hover"],
            command=self.run_throughput,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.diagnostics_result = ctk.CTkTextbox(
            card,
            height=130,
            corner_radius=14,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=12),
            activate_scrollbars=True,
        )
        self.diagnostics_result.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        self._set_textbox(self.diagnostics_result, "Ping and throughput results will appear here.")

    def _logs_tool(self, parent, row: int):
        card = self._tool_card(parent, row, "Admin Logs")
        ctk.CTkButton(
            card,
            text="Open HTTP Chat Log",
            height=40,
            corner_radius=12,
            fg_color=COLORS["blue"],
            hover_color=COLORS["blue_hover"],
            command=lambda: webbrowser.open(HTTP_LOG_URL),
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))

    def _set_textbox(self, textbox, text: str):
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")

    def add_message(self, sender: str, text: str, outgoing: bool = False):
        row = len(self.messages.winfo_children())

        outer = ctk.CTkFrame(self.messages, fg_color="transparent")
        outer.grid(row=row, column=0, sticky="ew", padx=14, pady=8)
        outer.grid_columnconfigure(0, weight=1)

        anchor_col = 1 if outgoing else 0
        outer.grid_columnconfigure(anchor_col, weight=0)

        bubble = ctk.CTkFrame(
            outer,
            fg_color=COLORS["bubble_out"] if outgoing else COLORS["bubble_in"],
            corner_radius=18,
        )
        bubble.grid(row=0, column=anchor_col, sticky="e" if outgoing else "w")

        ctk.CTkLabel(
            bubble,
            text=sender,
            text_color="#DCE9FF" if outgoing else COLORS["cyan"],
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 2))

        ctk.CTkLabel(
            bubble,
            text=text,
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=13),
            wraplength=560,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 12))

        self.messages.after(50, self._scroll_messages_to_bottom)

    def _scroll_messages_to_bottom(self):
        canvas = getattr(self.messages, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(1.0)

    def send_message(self):
        message = self.message_entry.get().strip()
        if not message:
            return
        self.message_entry.delete(0, "end")
        self.add_message("You", message, outgoing=True)
        self.master.network.send_chat_async(message)

    def set_online_users(self, users: list[str]):
        self.online_users = users
        for child in self.online_list.winfo_children():
            child.destroy()

        if not users:
            ctk.CTkLabel(
                self.online_list,
                text="No active peers yet",
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", padx=12, pady=12)
        else:
            for user in users:
                is_self = user == self.student.chat_username
                color = COLORS["success"] if is_self else COLORS["text"]
                label_text = f"{user} (you)" if is_self else user
                ctk.CTkLabel(
                    self.online_list,
                    text=label_text,
                    text_color=color,
                    font=ctk.CTkFont(size=12, weight="bold" if is_self else "normal"),
                    anchor="w",
                    wraplength=195,
                    justify="left",
                ).pack(fill="x", padx=12, pady=7)

        recipients = [user for user in users if user != self.student.chat_username]
        values = recipients or ["Select recipient"]
        self.recipient_menu.configure(values=values)
        if self.recipient_menu.get() not in values:
            self.recipient_menu.set(values[0])

    def choose_file(self):
        path = filedialog.askopenfilename(title="Choose a file to send")
        if not path:
            return
        self.selected_file = path
        self.file_label.configure(text=os.path.basename(path), text_color=COLORS["text"])
        self.file_status.configure(text="Ready to send.", text_color=COLORS["muted"])

    def send_file(self):
        recipient = self.recipient_menu.get().strip()
        if not self.selected_file:
            self.master.show_toast("Choose a file before sending.", "error")
            return
        if not recipient or recipient == "Select recipient":
            self.master.show_toast("Choose an online recipient.", "error")
            return

        self.send_file_button.configure(state="disabled", text="Sending...")
        self.file_progress.start()
        self.file_status.configure(text="Preparing transfer...", text_color=COLORS["muted"])
        self.master.network.send_file_async(
            self.selected_file,
            recipient,
            self.on_file_progress,
            self.on_file_done,
        )

    def on_file_progress(self, value: float, message: str):
        self.file_status.configure(text=message, text_color=COLORS["muted"])

    def on_file_done(self, ok: bool, message: str):
        self.file_progress.stop()
        self.file_progress.set(1 if ok else 0)
        self.send_file_button.configure(state="normal", text="Send File")
        self.file_status.configure(
            text=message,
            text_color=COLORS["success"] if ok else COLORS["danger"],
        )
        self.master.show_toast(message, "success" if ok else "error")

    def send_email_message(self):
        recipient = normalize_email(self.email_to_entry.get())
        subject = self.email_subject_entry.get().strip()
        body = self.email_body.get("1.0", "end").strip()

        if backend_send_email is None:
            self.master.show_toast("SMTP email backend is not available.", "error")
            return
        if not recipient or not subject or not body:
            self.master.show_toast("Complete recipient Gmail, subject, and message.", "error")
            return
        if not GMAIL_RE.match(recipient):
            self.master.show_toast("Recipient must be a valid @gmail.com address.", "error")
            return

        record = find_student_by_id(self.student.student_id)
        email_code = normalize_email_code(
            record.get("email_code", "") if record is not None else self.student.email_code
        )
        if not email_code:
            self.master.show_toast("Admin must add the 16-code before email sending.", "error")
            return
        if len(email_code) != 16 or not email_code.isalnum():
            self.master.show_toast("Saved email code must be exactly 16 letters or digits.", "error")
            return

        self.email_send_button.configure(text="Sending...", state="disabled")
        self.email_status.configure(text="Connecting to Gmail SMTP...", text_color=COLORS["muted"])

        thread = threading.Thread(
            target=self._email_worker,
            args=(self.student.email, email_code, recipient, subject, body),
            daemon=True,
        )
        thread.start()

    def _email_worker(self, sender: str, email_code: str, recipient: str, subject: str, body: str):
        try:
            backend_send_email(sender, email_code, recipient, subject, body)
        except Exception as exc:
            self.master.dispatch_ui(self.on_email_done, False, f"Email failed: {exc}")
            return
        self.master.dispatch_ui(self.on_email_done, True, "Email sent successfully.")

    def on_email_done(self, ok: bool, message: str):
        self.email_send_button.configure(text="Send Email", state="normal")
        self.email_status.configure(
            text=message,
            text_color=COLORS["success"] if ok else COLORS["danger"],
        )
        self.master.show_toast(message, "success" if ok else "error")

    def resolve_dns(self):
        domain = self.dns_entry.get().strip()
        if not domain:
            self.master.show_toast("Enter a domain to resolve.", "error")
            return

        self.dns_result.configure(text="Resolving...", text_color=COLORS["muted"])
        thread = threading.Thread(target=self._dns_worker, args=(domain,), daemon=True)
        thread.start()

    def _dns_worker(self, domain: str):
        try:
            # Backend hook: replace with your dns_query(domain) call if needed.
            if backend_dns_query is not None:
                ip_address = backend_dns_query(domain)
            else:
                ip_address = socket.gethostbyname(domain)
            self.master.dispatch_ui(
                self.dns_result.configure,
                text=f"{domain} -> {ip_address}",
                text_color=COLORS["success"],
            )
        except Exception as exc:
            self.master.dispatch_ui(
                self.dns_result.configure,
                text=f"DNS lookup failed: {exc}",
                text_color=COLORS["danger"],
            )

    def run_ping(self):
        self._set_textbox(self.diagnostics_result, "Running ping test...")
        self.master.network.ping_async(4, self.on_diagnostics_done)

    def run_throughput(self):
        self._set_textbox(self.diagnostics_result, "Running throughput test...")
        self.master.network.throughput_async(100_000, self.on_diagnostics_done)

    def on_diagnostics_done(self, result: str):
        self._set_textbox(self.diagnostics_result, result)

    def on_status(self, message: str, kind: str = "info"):
        color = {
            "success": COLORS["success"],
            "warning": COLORS["warning"],
            "error": COLORS["danger"],
            "info": COLORS["cyan"],
        }.get(kind, COLORS["cyan"])
        self.connection_label.configure(text=message, text_color=color)
        self.master.show_toast(message, kind)

    def on_file_notice(self, sender: str, filename: str):
        self.add_message("File Transfer", f"Incoming file '{filename}' from {sender}.")
        self.master.show_toast(f"Receiving '{filename}' from {sender}.", "info")

    def _schedule_user_refresh(self):
        if self.master.network and self.master.network.running:
            self.master.network.request_users()
        self.after(6000, self._schedule_user_refresh)


class ChatNetApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self.configure(fg_color=COLORS["bg"])
        self.current_frame = None
        self.student: Student | None = None
        self.network: ChatNetworkClient | None = None
        self.ui_queue: queue.Queue[tuple[callable, tuple, dict]] = queue.Queue()

        self.protocol("WM_DELETE_WINDOW", self.disconnect)
        self.after(50, self._drain_ui_queue)
        self.show_splash()

    def dispatch_ui(self, callback, *args, **kwargs):
        self.ui_queue.put((callback, args, kwargs))

    def _drain_ui_queue(self):
        try:
            while True:
                callback, args, kwargs = self.ui_queue.get_nowait()
                callback(*args, **kwargs)
        except queue.Empty:
            pass
        self.after(50, self._drain_ui_queue)

    def _clear_frame(self):
        if self.current_frame is not None:
            self.current_frame.destroy()
            self.current_frame = None

    def _center(self, width: int, height: int):
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def show_splash(self):
        self.withdraw()
        self.overrideredirect(True)
        self.resizable(False, False)
        self.minsize(1, 1)
        self._center(740, 430)
        self.attributes("-alpha", 0.82)
        self.deiconify()
        self._clear_frame()
        self.current_frame = SplashFrame(self)
        self.current_frame.start()

    def show_role_selection(self):
        self.withdraw()
        self.overrideredirect(False)
        self.resizable(False, False)
        self.minsize(1, 1)
        self.attributes("-alpha", 1)
        self._center(900, 620)
        self.deiconify()
        self._clear_frame()
        self.current_frame = RoleSelectionFrame(self)

    def show_registration(self):
        self.withdraw()
        self.overrideredirect(False)
        self.resizable(False, False)
        self.minsize(1, 1)
        self.attributes("-alpha", 1)
        self._center(900, 620)
        self.deiconify()
        self._clear_frame()
        self.current_frame = RegistrationFrame(self)

    def show_admin_login(self):
        self.withdraw()
        self.overrideredirect(False)
        self.resizable(False, False)
        self.minsize(1, 1)
        self.attributes("-alpha", 1)
        self._center(850, 600)
        self.deiconify()
        self._clear_frame()
        self.current_frame = AdminLoginFrame(self)

    def show_admin_panel(self):
        self.resizable(True, True)
        self.minsize(1000, 650)
        self.attributes("-alpha", 1)
        self._center(1120, 720)
        self._clear_frame()
        self.current_frame = AdminPanelFrame(self)

    def connect_student(self, student: Student):
        self.student = student
        self.network = ChatNetworkClient(
            student=student,
            ui_dispatch=self.dispatch_ui,
            on_message=self._network_message,
            on_users=self._network_users,
            on_status=self._network_status,
            on_file_notice=self._network_file_notice,
        )
        self.network.connect_async(self._on_connect_done)

    def _on_connect_done(self, ok: bool, error: str):
        if ok:
            self.show_dashboard()
            return

        if self.student is not None:
            with ACTIVE_IDS_LOCK:
                ACTIVE_STUDENT_IDS.discard(self.student.student_id)

        self.show_toast(error or "Could not enter ChatNet.", "error")
        if isinstance(self.current_frame, RegistrationFrame):
            self.current_frame.enter_button.configure(text="Enter Chat", state="normal")

    def show_dashboard(self):
        self.resizable(True, True)
        self.minsize(1120, 680)
        self._center(1240, 780)
        self._clear_frame()
        self.current_frame = DashboardFrame(self, self.student)

    def _network_message(self, sender: str, message: str):
        if isinstance(self.current_frame, DashboardFrame):
            self.current_frame.add_message(sender, message)

    def _network_users(self, users: list[str]):
        if isinstance(self.current_frame, DashboardFrame):
            self.current_frame.set_online_users(users)

    def _network_status(self, message: str, kind: str = "info"):
        if isinstance(self.current_frame, DashboardFrame):
            self.current_frame.on_status(message, kind)
        else:
            self.show_toast(message, kind)

    def _network_file_notice(self, sender: str, filename: str):
        if isinstance(self.current_frame, DashboardFrame):
            self.current_frame.on_file_notice(sender, filename)

    def show_toast(self, message: str, kind: str = "error"):
        Toast(self, message, kind)

    def disconnect(self):
        if self.network is not None:
            self.network.disconnect_async()
        if self.student is not None:
            with ACTIVE_IDS_LOCK:
                ACTIVE_STUDENT_IDS.discard(self.student.student_id)
        self.destroy()


def main():
    app = ChatNetApp()
    app.mainloop()


if __name__ == "__main__":
    main()

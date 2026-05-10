# 🌐 ChatNet — Advanced Multi-Protocol Networking Framework

![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Networking](https://img.shields.io/badge/Protocols-TCP%20%7C%20UDP%20%7C%20DNS%20%7C%20HTTP%20%7C%20SMTP-orange)
![Status](https://img.shields.io/badge/status-active-success)

ChatNet is a low-level networking framework built entirely with Python standard libraries.

The project demonstrates manual implementation of core networking protocols and services without external frameworks.

It focuses on socket-level communication, concurrency, protocol handling, diagnostics, and secure service interaction.

---

# Features

## TCP Communication Engine

* Real-time TCP chat server
* Reliable client-server messaging
* Command-based interaction system
* Sequential and threaded communication models

## Concurrent Client Handling

* Multi-client support using `threading`
* Thread-safe shared resources with `threading.Lock`
* Stable handling of simultaneous connections

## Network Diagnostics

* `/ping` command for RTT measurement
* `/throughput` command for bandwidth testing
* Live response timing analysis

## Private Messaging System

* User-to-user direct messaging
* Connected users tracking
* Session-based communication routing

## Reliable UDP File Transfer

Custom implementation of Stop-and-Wait ARQ over UDP.

Includes:

* File chunking
* Sequence numbering
* ACK validation
* Packet retransmission
* Reliable delivery over unreliable transport

## Manual DNS Resolver

Low-level DNS resolver built manually without external libraries.

Capabilities:

* Raw binary DNS packet creation
* Parsing DNS responses
* Extracting A Records
* Direct communication with Google DNS `8.8.8.8`

## HTTP Log Server

Embedded HTTP server for monitoring logs through the browser.

Features:

* Live chat log rendering
* HTML response generation
* Lightweight monitoring dashboard

## SMTP Mail Notification System

Manual SMTP implementation with secure communication.

Includes:

* SMTP handshake
* STARTTLS encryption
* Base64 authentication
* Automated email alerts

---

# Architecture

ChatNet follows a modular client-server architecture.

## Core Services

| Service     | Port  | Purpose           |
| ----------- | ----- | ----------------- |
| TCP Server  | 12000 | Chat and commands |
| UDP Service | 13000 | File transfer     |
| HTTP Server | 8080  | Log monitoring    |

---

# Project Structure

```text
ChatNet/
│
├── chat_server_threaded.py
├── chat_client_v2.py
├── udp_transfer.py
├── dns_resolver.py
├── smtp_notifier.py
├── http_log_server.py
├── logs/
├── received_files/
├── README.md
└── .gitignore
```

---

# Installation

## Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/ChatNet.git
cd ChatNet
```

## Create Virtual Environment

Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

## Install Requirements

This project depends only on Python standard libraries.

No external packages required.

---

# Running The Project

## Start TCP Server

```bash
python chat_server_threaded.py
```

## Run Client

```bash
python chat_client_v2.py
```

## Open Web Logs

Open:

```text
http://localhost:8080/chatlog
```

---

# Available Commands

| Command                   | Description             |
| ------------------------- | ----------------------- |
| `/msg <user> <text>`      | Send private message    |
| `/users`                  | Show online users       |
| `/sendfile <path> <user>` | Transfer file using UDP |
| `/ping`                   | Measure RTT             |
| `/throughput <bytes>`     | Network throughput test |
| `/quit`                   | Disconnect safely       |

---

# Deployment

## Deploy On Linux VPS

Install Python:

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 -y
```

Clone project:

```bash
git clone https://github.com/YOUR_USERNAME/ChatNet.git
cd ChatNet
```

Run server:

```bash
python3 chat_server_threaded.py
```

## Keep Server Running

Using `screen`:

```bash
screen -S chatnet
python3 chat_server_threaded.py
```

Detach session:

```bash
CTRL + A + D
```

Return later:

```bash
screen -r chatnet
```

## Open Firewall Ports

```bash
sudo ufw allow 12000/tcp
sudo ufw allow 13000/udp
sudo ufw allow 8080/tcp
```

---

# GitHub Upload

## Initialize Git

```bash
git init
```

## Add Files

```bash
git add .
```

## Commit

```bash
git commit -m "Initial release: ChatNet networking framework"
```

## Connect Repository

```bash
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ChatNet.git
```

## Push

```bash
git push -u origin main
```

---

# .gitignore

```text
__pycache__/
*.log
received_files/
.vscode/
.idea/
venv/
```

---

# Technical Highlights

* Pure socket programming
* TCP and UDP protocol handling
* Concurrency with threads
* Low-level DNS packet parsing
* Manual SMTP communication
* Lightweight HTTP serving
* Reliability mechanisms over UDP
* Secure communication practices

---

# Academic Context

Developed for advanced network programming and protocol engineering practice.

Built using only Python standard libraries to strengthen low-level networking understanding and protocol implementation skills.

---

# Developer

Developer: Hamza Saeed Shukri

Field:
Network Engineering • Cybersecurity • Systems Programming

---

# License

MIT License

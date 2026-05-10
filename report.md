# Section 1 — Planning & Modelling

## Requirements Analysis + Use Case Diagram

The ChatNet system is designed to provide real-time multi-client communication with additional features like file transfer via UDP, domain name resolution, HTTP-based chat logging, and email notifications via SMTP. The requirements dictate a distributed architecture with multiple interacting modules.

```mermaid
usecaseDiagram
    actor User as "Client User"
    actor Admin as "System Admin"
    
    package "ChatNet System" {
        usecase UC1 as "Connect to Server"
        usecase UC2 as "Send/Receive Messages"
        usecase UC3 as "Transfer Files (UDP)"
        usecase UC4 as "Resolve Hostname (DNS)"
        usecase UC5 as "Receive @mention Email (SMTP)"
        usecase UC6 as "View Logs (HTTP)"
    }
    
    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC4
    User --> UC5
    Admin --> UC6
```

## Sequence Diagrams

### 1. TCP Connection Setup
```mermaid
sequenceDiagram
    participant Client as Client (TCP)
    participant Server as Chat Server (TCP)
    
    Client->>Server: SYN
    Server->>Client: SYN-ACK
    Client->>Server: ACK
    Note over Client,Server: 3-Way Handshake Complete
    Server->>Client: 200 OK - Welcome to ChatNet
    Client->>Server: USERNAME:<username>
    Server->>Client: 200 OK - Username accepted
```

### 2. Message Broadcast
```mermaid
sequenceDiagram
    participant C1 as Client 1
    participant Server as Chat Server
    participant C2 as Client 2
    participant C3 as Client 3
    
    C1->>Server: MSG:Hello everyone!
    Note over Server: Server processes message
    Server->>C2: BROADCAST:[User1]: Hello everyone!
    Server->>C3: BROADCAST:[User1]: Hello everyone!
```

### 3. UDP File Transfer
```mermaid
sequenceDiagram
    participant Sender as File Sender (UDP)
    participant Receiver as File Receiver (UDP)
    
    Note over Sender: Chunk file into fixed sizes
    Sender->>Receiver: Data Chunk 1 (Seq=1)
    Receiver->>Sender: ACK 1
    Sender->>Receiver: Data Chunk 2 (Seq=2)
    Note over Receiver: Receives Data Chunk 2
    Receiver->>Sender: ACK 2
    Note over Sender,Receiver: Stop-and-Wait Loop Continues
    Sender->>Receiver: EOF Marker
    Receiver->>Sender: ACK EOF
    Note over Receiver: Reassemble file
```

### 4. DNS Query
```mermaid
sequenceDiagram
    participant Client as DNS Resolver
    participant DNS as 8.8.8.8 (Google DNS)
    
    Note over Client: Build DNS Packet (QNAME, QTYPE=A)
    Client->>DNS: UDP Request (Port 53)
    Note over DNS: Process Query
    DNS->>Client: UDP Response (IP Address)
    Note over Client: Parse response & extract IP
```

### 5. SMTP Handshake
```mermaid
sequenceDiagram
    participant Client as SMTP Notifier
    participant Server as SMTP Server
    
    Client->>Server: TCP Connection (Port 25/587)
    Server->>Client: 220 Service Ready
    Client->>Server: HELO chatnet.local
    Server->>Client: 250 OK
    Client->>Server: MAIL FROM:<bot@chatnet.com>
    Server->>Client: 250 OK
    Client->>Server: RCPT TO:<user@example.com>
    Server->>Client: 250 OK
    Client->>Server: DATA
    Server->>Client: 354 Start mail input
    Client->>Server: <Headers & Body> ... \r\n.\r\n
    Server->>Client: 250 OK Message accepted
    Client->>Server: QUIT
    Server->>Client: 221 Closing connection
```

# Section 2 — System Architecture

## Component Diagram
```mermaid
flowchart TD
    subgraph "ChatNet Architecture"
        CoreServer[chat_server_threaded.py]
        BasicServer[chat_server.py]
        CoreClient[chat_client_v2.py]
        BasicClient[chat_client.py]
        FileSender[file_sender.py]
        FileReceiver[file_receiver.py]
        DNSResolver[dns_resolver.py]
        SMTPNotifier[smtp_notifier.py]
        LogServer[log_server.py]
        
        CoreClient -->|TCP| CoreServer
        BasicClient -->|TCP| BasicServer
        FileSender -->|UDP| FileReceiver
        CoreClient -.->|Local Call| DNSResolver
        CoreServer -.->|Local Call| SMTPNotifier
        LogServer -.->|Reads Logs| CoreServer
    end
```

## Socket Interface Diagram
```mermaid
flowchart TD
    subgraph Client Side
        C1[Chat Client] -- "TCP (Dynamic Port)" --> ServerTCP
        FS[File Sender] -- "UDP (Dynamic Port)" --> ReceiverUDP
        DNS[DNS Resolver] -- "UDP (Dynamic Port)" --> PublicDNS[Public DNS: 8.8.8.8:53]
    end

    subgraph Server Side
        ServerTCP[Chat Server] -- "TCP (:12000)" --> C1
        ReceiverUDP[File Receiver] -- "UDP (:12001)" --> FS
        HTTP[Log Server] -- "TCP (:8080)" --> Browser[Web Browser]
        SMTP[SMTP Notifier] -- "TCP" --> SMTPServer[Mail Server: 25/587]
    end
```

## Thread Model Diagram
```mermaid
flowchart TD
    Main[Main Server Thread]
    Wait[Wait for incoming connections]
    Main --> Wait
    Wait -- "New Client Connects" --> Thread[Spawn Client Thread]
    Wait --> Wait
    
    subgraph "Client Handler Thread"
        Thread --> LockWait[Acquire Lock]
        LockWait --> Update[Update Shared State / Append Log]
        Update --> LockRelease[Release Lock]
        LockRelease --> Loop[Listen for Messages]
        Loop -- "Receives Data" --> Broadcast[Broadcast to others]
        Loop -- "Client Disconnects" --> Cleanup[Cleanup resources]
        Cleanup --> Terminate[Thread Terminates]
    end
```

# Section 3 — Delay Calculations

*Note: Replace placeholders with measured values from the running system.*

- **Transmission delay**: `d_trans = L/R`
  *(Calculation details based on packet length `L` and link bandwidth `R`)*
- **Propagation delay**: `d_prop = d/s`
  *(Calculation based on distance `d` and propagation speed `s`)*
- **Processing delay**: `[MEASURED/ESTIMATED VALUE]` ms
  *(Estimated time taken by server to process the packet header)*
- **Store-and-forward**: `d_end-end = N × (L/R)`
  *(Total delay assuming `N` links)*
- **Traffic intensity**: `La/R`
  *(Calculation based on an average arrival rate `a` under 5-client load)*
- **RTT from /ping vs. theoretical propagation delay**: 
  *(Compare and explain the gap, e.g., operating system scheduling, thread switching overhead, processing delays)*

# Section 4 — Implementation Screenshots

*Insert real terminal/browser captures below:*

1. **Server startup** (showing IP and port)
   `[INSERT SCREENSHOT HERE]`
2. **Multi-client chat session** (3+ clients visible)
   `[INSERT SCREENSHOT HERE]`
3. **`/ping` output** with RTT values
   `[INSERT SCREENSHOT HERE]`
4. **`/throughput` output** with kbps result
   `[INSERT SCREENSHOT HERE]`
5. **UDP file transfer** progress log (Packet X/Y sent... ACK received)
   `[INSERT SCREENSHOT HERE]`
6. **DNS resolution** terminal output
   `[INSERT SCREENSHOT HERE]`
7. **Browser showing `/chatlog`** rendering 50 messages
   `[INSERT SCREENSHOT HERE]`
8. **Email inbox** confirming received SMTP notification
   `[INSERT SCREENSHOT HERE]`

# Section 5 — Test Cases

| TC | Module | Input | Expected Output |
|----|--------|-------|-----------------|
| TC-01 | TCP Server | Valid client connects | 200 OK + welcome message |
| TC-02 | TCP Server | Duplicate username | 409 Conflict rejection |
| TC-03 | UDP Transfer | Send 1 KB file | File received intact |
| TC-04 | UDP Transfer | Simulated ACK timeout | Retransmission triggered |
| TC-05 | DNS Resolver | google.com | Valid IPv4 address returned |
| TC-06 | DNS Resolver | Invalid hostname | Error message displayed |
| TC-07 | HTTP Log Server | GET /chatlog | 200 OK + HTML response |
| TC-08 | HTTP Log Server | GET /unknown | 404 Not Found |
| TC-09 | SMTP Notifier | Valid @mention | Email delivered to inbox |
| TC-10 | SMTP Notifier | Invalid recipient email | SMTP 550 error handled gracefully |

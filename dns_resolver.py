#!/usr/bin/env python3
"""Manual UDP DNS resolver for ChatNet Phase 4."""

import random
import socket
import struct
import sys


DNS_SERVER = "8.8.8.8"
DNS_PORT = 53
TIMEOUT_SECONDS = 5
TYPE_A = 1
CLASS_IN = 1
RCODE_NXDOMAIN = 3


class DNSResolutionError(Exception):
    """Raised when a DNS response cannot be resolved to an A record."""


class NXDOMAINError(DNSResolutionError):
    """Raised when the DNS server reports that the name does not exist."""


def encode_domain_name(domain):
    """Encode example.com into DNS label format: 7example3com0."""
    labels = domain.strip(".").split(".")
    encoded = bytearray()

    for label in labels:
        if not label:
            raise ValueError("Domain name contains an empty label.")

        label_bytes = label.encode("ascii")
        if len(label_bytes) > 63:
            raise ValueError("DNS labels must be 63 bytes or fewer.")

        encoded.append(len(label_bytes))
        encoded.extend(label_bytes)

    encoded.append(0)
    return bytes(encoded)


def build_dns_query(domain, transaction_id=None):
    """Build a binary DNS query packet for one IPv4 A record."""
    if transaction_id is None:
        transaction_id = random.randint(0, 0xFFFF)

    flags = 0x0100  # Standard recursive query.
    qdcount = 1
    ancount = 0
    nscount = 0
    arcount = 0

    header = struct.pack(
        "!HHHHHH", transaction_id, flags, qdcount, ancount, nscount, arcount
    )
    question = encode_domain_name(domain) + struct.pack("!HH", TYPE_A, CLASS_IN)
    return transaction_id, header + question


def read_domain_name(packet, offset):
    """Read a possibly compressed DNS name and return (name, next_offset)."""
    labels = []
    next_offset = offset
    jumped = False
    seen_offsets = set()

    while True:
        if offset >= len(packet):
            raise DNSResolutionError("DNS name points beyond the response packet.")

        length = packet[offset]

        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise DNSResolutionError("DNS compression pointer is incomplete.")

            pointer = struct.unpack("!H", packet[offset : offset + 2])[0] & 0x3FFF
            if pointer in seen_offsets:
                raise DNSResolutionError("DNS compression pointer loop detected.")

            seen_offsets.add(pointer)
            if not jumped:
                next_offset = offset + 2
            offset = pointer
            jumped = True
            continue

        if length == 0:
            offset += 1
            break

        offset += 1
        end = offset + length
        if end > len(packet):
            raise DNSResolutionError("DNS label extends beyond the response packet.")

        labels.append(packet[offset:end].decode("ascii", errors="replace"))
        offset = end

    if not jumped:
        next_offset = offset
    return ".".join(labels), next_offset


def parse_dns_response(packet, expected_transaction_id=None):
    """Parse a binary DNS response and return a list of IPv4 A records."""
    if len(packet) < 12:
        raise DNSResolutionError("DNS response is too short.")

    (
        transaction_id,
        flags,
        qdcount,
        ancount,
        _nscount,
        _arcount,
    ) = struct.unpack("!HHHHHH", packet[:12])

    if expected_transaction_id is not None and transaction_id != expected_transaction_id:
        raise DNSResolutionError("DNS transaction ID mismatch.")

    rcode = flags & 0x000F
    if rcode == RCODE_NXDOMAIN:
        raise NXDOMAINError("NXDOMAIN: domain name does not exist.")
    if rcode != 0:
        raise DNSResolutionError(f"DNS server returned error code {rcode}.")

    offset = 12

    for _ in range(qdcount):
        _query_name, offset = read_domain_name(packet, offset)
        if offset + 4 > len(packet):
            raise DNSResolutionError("DNS question section is truncated.")
        offset += 4

    addresses = []
    for _ in range(ancount):
        _name, offset = read_domain_name(packet, offset)
        if offset + 10 > len(packet):
            raise DNSResolutionError("DNS answer section is truncated.")

        record_type, record_class, _ttl, rdlength = struct.unpack(
            "!HHIH", packet[offset : offset + 10]
        )
        offset += 10

        rdata_end = offset + rdlength
        if rdata_end > len(packet):
            raise DNSResolutionError("DNS answer data is truncated.")

        if record_type == TYPE_A and record_class == CLASS_IN and rdlength == 4:
            addresses.append(socket.inet_ntoa(packet[offset:rdata_end]))

        offset = rdata_end

    if not addresses:
        raise DNSResolutionError("No IPv4 A record found in DNS response.")

    return addresses


def resolve(domain, dns_server=DNS_SERVER, timeout=TIMEOUT_SECONDS):
    """Resolve a domain name to its first IPv4 address using raw UDP DNS."""
    transaction_id, query = build_dns_query(domain)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.settimeout(timeout)
        udp_socket.sendto(query, (dns_server, DNS_PORT))
        response, _address = udp_socket.recvfrom(512)

    return parse_dns_response(response, transaction_id)[0]


def main():
    if len(sys.argv) != 2:
        print("Usage: python dns_resolver.py <domain>")
        return 2

    domain = sys.argv[1]
    try:
        ip_address = resolve(domain)
    except NXDOMAINError as exc:
        print(exc)
        return 1
    except (OSError, DNSResolutionError, ValueError) as exc:
        print(f"DNS lookup failed: {exc}")
        return 1

    print(f"{domain} -> {ip_address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Test NTRIP client to verify RTK corrections are being received
from the LC29H base station
"""

import socket
import sys
import time
import argparse
from datetime import datetime
import base64


class NTRIPClient:
    """Simple NTRIP client for testing base station connections"""

    def __init__(self, host: str, port: int, mountpoint: str,
                 username: str = None, password: str = None):
        self.host = host
        self.port = port
        self.mountpoint = mountpoint
        self.username = username
        self.password = password
        self.socket = None
        self.connected = False

        # Statistics
        self.bytes_received = 0
        self.messages_received = 0
        self.start_time = None
        self.message_types = {}

    def connect(self) -> bool:
        """Connect to NTRIP caster"""
        try:
            print(f"Connecting to {self.host}:{self.port}...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port))

            # Build NTRIP request
            request = f"GET /{self.mountpoint} HTTP/1.1\r\n"
            request += f"Host: {self.host}\r\n"
            request += "User-Agent: NTRIP PythonClient/1.0\r\n"
            request += "Ntrip-Version: Ntrip/2.0\r\n"

            # Add authentication if provided
            if self.username and self.password:
                auth_str = f"{self.username}:{self.password}"
                auth_bytes = auth_str.encode('ascii')
                auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                request += f"Authorization: Basic {auth_b64}\r\n"

            request += "Connection: close\r\n"
            request += "\r\n"

            # Send request
            self.socket.send(request.encode('ascii'))

            # Read response
            response = self.socket.recv(4096).decode('ascii', errors='ignore')

            if "200 OK" in response or "ICY 200 OK" in response:
                print("✓ Connected successfully!")
                print(f"  Server response: {response.split()[0:3]}")
                self.connected = True
                self.start_time = time.time()
                return True
            else:
                print(f"✗ Connection failed!")
                print(f"  Server response: {response[:200]}")
                return False

        except socket.timeout:
            print("✗ Connection timeout")
            return False
        except Exception as e:
            print(f"✗ Connection error: {e}")
            return False

    def parse_rtcm3(self, data: bytes) -> list:
        """
        Parse RTCM3 messages from byte stream
        Returns list of (message_type, message_data) tuples
        """
        messages = []
        i = 0

        while i < len(data):
            # Look for RTCM3 preamble (0xD3)
            if data[i] != 0xD3:
                i += 1
                continue

            # Need at least 6 bytes for header + CRC
            if i + 6 > len(data):
                break

            # Parse message length
            msg_len = ((data[i + 1] & 0x03) << 8) | data[i + 2]
            total_len = msg_len + 6  # header (3) + message + CRC (3)

            # Check if we have the complete message
            if i + total_len > len(data):
                break

            # Extract message type (first 12 bits of message payload)
            if msg_len >= 2:
                msg_type = (data[i + 3] << 4) | ((data[i + 4] >> 4) & 0x0F)
                msg_data = data[i:i + total_len]
                messages.append((msg_type, msg_data))

            i += total_len

        return messages

    def receive_loop(self, duration: int = None, max_messages: int = None):
        """
        Receive and display RTCM corrections

        Args:
            duration: How long to run in seconds (None = infinite)
            max_messages: Max messages to receive (None = infinite)
        """
        if not self.connected:
            print("Not connected!")
            return

        print("\n" + "=" * 60)
        print("Receiving RTCM corrections...")
        print("Press Ctrl+C to stop")
        print("=" * 60 + "\n")

        try:
            self.socket.settimeout(5.0)
            buffer = bytearray()
            last_stats_time = time.time()

            while True:
                # Check duration limit
                if duration and (time.time() - self.start_time) >= duration:
                    print("\nDuration limit reached")
                    break

                # Check message limit
                if max_messages and self.messages_received >= max_messages:
                    print("\nMessage limit reached")
                    break

                try:
                    # Receive data
                    data = self.socket.recv(4096)
                    if not data:
                        print("\n✗ Connection closed by server")
                        break

                    self.bytes_received += len(data)
                    buffer.extend(data)

                    # Parse RTCM messages
                    messages = self.parse_rtcm3(bytes(buffer))

                    for msg_type, msg_data in messages:
                        self.messages_received += 1

                        # Track message types
                        if msg_type not in self.message_types:
                            self.message_types[msg_type] = 0
                        self.message_types[msg_type] += 1

                        # Remove processed message from buffer
                        idx = buffer.find(msg_data)
                        if idx >= 0:
                            del buffer[:idx + len(msg_data)]

                    # Print statistics every 2 seconds
                    if time.time() - last_stats_time >= 2.0:
                        self._print_stats()
                        last_stats_time = time.time()

                except socket.timeout:
                    # Print stats on timeout too
                    if time.time() - last_stats_time >= 2.0:
                        self._print_stats()
                        last_stats_time = time.time()
                    continue

        except KeyboardInterrupt:
            print("\n\nStopped by user")

        self._print_final_stats()

    def _print_stats(self):
        """Print real-time statistics"""
        elapsed = time.time() - self.start_time
        rate = self.messages_received / elapsed if elapsed > 0 else 0
        byte_rate = self.bytes_received / elapsed if elapsed > 0 else 0

        print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
              f"Messages: {self.messages_received:4d} | "
              f"Rate: {rate:5.1f} msg/s | "
              f"Data: {self.bytes_received:6d} bytes ({byte_rate:.0f} B/s)",
              end='', flush=True)

    def _print_final_stats(self):
        """Print final statistics"""
        print("\n\n" + "=" * 60)
        print("FINAL STATISTICS")
        print("=" * 60)

        elapsed = time.time() - self.start_time
        rate = self.messages_received / elapsed if elapsed > 0 else 0
        byte_rate = self.bytes_received / elapsed if elapsed > 0 else 0

        print(f"Duration:         {elapsed:.1f} seconds")
        print(f"Messages:         {self.messages_received}")
        print(f"Bytes received:   {self.bytes_received:,}")
        print(f"Message rate:     {rate:.2f} msg/s")
        print(f"Byte rate:        {byte_rate:.0f} B/s")

        if self.message_types:
            print("\nMessage types received:")
            for msg_type in sorted(self.message_types.keys()):
                count = self.message_types[msg_type]
                desc = self._get_message_description(msg_type)
                print(f"  {msg_type:4d}: {count:5d} messages - {desc}")

    def _get_message_description(self, msg_type: int) -> str:
        """Get human-readable description of RTCM message type"""
        descriptions = {
            1005: "Station Coordinates",
            1006: "Station Coordinates + Height",
            1074: "GPS MSM4",
            1075: "GPS MSM5",
            1077: "GPS MSM7",
            1084: "GLONASS MSM4",
            1085: "GLONASS MSM5",
            1087: "GLONASS MSM7",
            1094: "Galileo MSM4",
            1095: "Galileo MSM5",
            1097: "Galileo MSM7",
            1124: "BeiDou MSM4",
            1125: "BeiDou MSM5",
            1127: "BeiDou MSM7",
            1230: "GLONASS Code-Phase Biases"
        }
        return descriptions.get(msg_type, "Unknown")

    def disconnect(self):
        """Close connection"""
        if self.socket:
            self.socket.close()
        self.connected = False
        print("Disconnected")


def main():
    parser = argparse.ArgumentParser(
        description='NTRIP client to test RTK base station corrections',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Connect to local base station
  python3 test_ntrip_client.py localhost 2101 BASE

  # Connect with authentication
  python3 test_ntrip_client.py localhost 2101 BASE -u user -p pass

  # Run for 30 seconds
  python3 test_ntrip_client.py localhost 2101 BASE -d 30

  # Receive 100 messages then stop
  python3 test_ntrip_client.py localhost 2101 BASE -m 100
        """
    )

    parser.add_argument('host', help='NTRIP caster hostname or IP')
    parser.add_argument('port', type=int, help='NTRIP caster port')
    parser.add_argument('mountpoint', help='NTRIP mountpoint')
    parser.add_argument('-u', '--username', help='Username for authentication')
    parser.add_argument('-p', '--password', help='Password for authentication')
    parser.add_argument('-d', '--duration', type=int, help='Duration in seconds')
    parser.add_argument('-m', '--max-messages', type=int, help='Maximum messages to receive')

    args = parser.parse_args()

    # Create client
    client = NTRIPClient(
        host=args.host,
        port=args.port,
        mountpoint=args.mountpoint,
        username=args.username,
        password=args.password
    )

    # Connect
    if not client.connect():
        sys.exit(1)

    # Receive corrections
    try:
        client.receive_loop(duration=args.duration, max_messages=args.max_messages)
    finally:
        client.disconnect()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
NTRIP Server for RTK Base Station
Broadcasts RTCM3 corrections from LC29H GPS module to NTRIP clients
"""

import socket
import threading
import logging
import base64
import time
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class NTRIPClient:
    """Represents a connected NTRIP client"""

    def __init__(self, conn: socket.socket, addr: tuple, mountpoint: str):
        self.conn = conn
        self.addr = addr
        self.mountpoint = mountpoint
        self.username = ""
        self.connected_at = datetime.now()
        self.bytes_sent = 0

    def send_data(self, data: bytes) -> bool:
        """Send data to client, return False if failed"""
        try:
            self.conn.sendall(data)
            self.bytes_sent += len(data)
            return True
        except (socket.error, BrokenPipeError) as e:
            logger.warning(f"Failed to send to {self.addr}: {e}")
            return False

    def close(self):
        """Close client connection"""
        try:
            self.conn.close()
        except:
            pass


class NTRIPServer:
    """NTRIP Caster server for broadcasting RTK corrections"""

    def __init__(self, host: str = '0.0.0.0', port: int = 2101):
        """
        Initialize NTRIP server

        Args:
            host: IP address to bind to (0.0.0.0 for all interfaces)
            port: Port number (default 2101 for NTRIP)
        """
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.accept_thread: Optional[threading.Thread] = None
        self.clients: List[NTRIPClient] = []
        self.clients_lock = threading.Lock()
        self.mountpoints: Dict[str, dict] = {}
        self.require_auth = False
        self.credentials: Dict[str, str] = {}  # username: password

    def add_mountpoint(self, name: str, identifier: str = "", format: str = "RTCM 3.3",
                       format_details: str = "1005(10),1074(1),1084(1),1094(1),1124(1),1230(10)",
                       carrier: str = "2", nav_system: str = "GPS+GLO+GAL+BDS",
                       network: str = "FKA", country: str = "USA",
                       lat: float = 0.0, lon: float = 0.0):
        """
        Add mountpoint to NTRIP server

        Args:
            name: Mountpoint name (e.g., "BASE")
            identifier: Station identifier
            format: Data format
            format_details: RTCM message types and rates
            carrier: Carrier phase (0=no, 1=L1, 2=L1+L2)
            nav_system: Navigation systems supported
            network: Network name
            country: Country code
            lat: Station latitude
            lon: Station longitude
        """
        self.mountpoints[name] = {
            'identifier': identifier or name,
            'format': format,
            'format_details': format_details,
            'carrier': carrier,
            'nav_system': nav_system,
            'network': network,
            'country': country,
            'lat': lat,
            'lon': lon,
            'nmea': '1',  # NMEA required
            'solution': '0',  # Single base
            'generator': 'LC29H',
            'compression': 'none',
            'authentication': 'B' if self.require_auth else 'N',
            'fee': 'N',
            'bitrate': '9600'
        }
        logger.info(f"Added mountpoint: {name}")

    def set_authentication(self, username: str, password: str):
        """
        Enable authentication and set credentials

        Args:
            username: Username for authentication
            password: Password for authentication
        """
        self.require_auth = True
        self.credentials[username] = password
        logger.info(f"Authentication enabled for user: {username}")

    def start(self) -> bool:
        """
        Start NTRIP server

        Returns:
            True if server started successfully
        """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True

            # Start accept thread
            self.accept_thread = threading.Thread(target=self._accept_clients, daemon=True)
            self.accept_thread.start()

            logger.info(f"NTRIP server started on {self.host}:{self.port}")
            return True

        except Exception as e:
            logger.error(f"Failed to start NTRIP server: {e}")
            return False

    def stop(self):
        """Stop NTRIP server and disconnect all clients"""
        self.running = False

        # Close all client connections
        with self.clients_lock:
            for client in self.clients:
                client.close()
            self.clients.clear()

        # Close server socket
        if self.server_socket:
            self.server_socket.close()

        if self.accept_thread:
            self.accept_thread.join(timeout=2.0)

        logger.info("NTRIP server stopped")

    def _accept_clients(self):
        """Accept incoming client connections"""
        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                conn, addr = self.server_socket.accept()
                logger.info(f"New connection from {addr}")

                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True
                )
                client_thread.start()

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}")

    def _handle_client(self, conn: socket.socket, addr: tuple):
        """Handle individual client connection"""
        try:
            # Receive HTTP request
            conn.settimeout(10.0)
            request = conn.recv(4096).decode('utf-8', errors='ignore')

            if not request:
                conn.close()
                return

            lines = request.split('\r\n')
            if not lines:
                conn.close()
                return

            # Parse request line
            request_line = lines[0].split()
            if len(request_line) < 3:
                self._send_response(conn, 400, "Bad Request")
                conn.close()
                return

            method = request_line[0]
            path = request_line[1]

            # Handle sourcetable request
            if method == "GET" and path == "/":
                self._send_sourcetable(conn)
                conn.close()
                return

            # Handle mountpoint request
            if method == "GET" and path.startswith("/"):
                mountpoint = path[1:]  # Remove leading /

                # Check if mountpoint exists
                if mountpoint not in self.mountpoints:
                    self._send_response(conn, 404, "Mountpoint not found")
                    conn.close()
                    return

                # Check authentication if required
                if self.require_auth:
                    auth_header = None
                    for line in lines:
                        if line.startswith("Authorization:"):
                            auth_header = line.split(":", 1)[1].strip()
                            break

                    if not auth_header or not self._verify_auth(auth_header):
                        self._send_response(conn, 401, "Unauthorized",
                                          extra_headers="WWW-Authenticate: Basic realm=\"NTRIP\"\r\n")
                        conn.close()
                        return

                # Accept client
                self._send_response(conn, 200, "OK",
                                  extra_headers="Content-Type: gnss/data\r\n")

                # Add client to list
                client = NTRIPClient(conn, addr, mountpoint)
                with self.clients_lock:
                    self.clients.append(client)

                logger.info(f"Client {addr} connected to mountpoint {mountpoint}")
                logger.info(f"Active clients: {len(self.clients)}")

                # Keep connection alive (will be closed when client disconnects or server stops)
                return

            else:
                self._send_response(conn, 400, "Bad Request")
                conn.close()

        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
            conn.close()

    def _send_sourcetable(self, conn: socket.socket):
        """Send NTRIP sourcetable to client"""
        sourcetable = "SOURCETABLE 200 OK\r\n"
        sourcetable += "Server: LC29H-NTRIP-Server/1.0\r\n"
        sourcetable += "Content-Type: text/plain\r\n"
        sourcetable += "Connection: close\r\n\r\n"

        # CAS line (caster info)
        sourcetable += f"CAS;{self.host};{self.port};LC29H RTK Base;LC29H;0;USA;0.00;0.00;http://example.com\r\n"

        # STR lines (stream/mountpoint info)
        for name, info in self.mountpoints.items():
            str_line = f"STR;{name};{info['identifier']};{info['format']};{info['format_details']};"
            str_line += f"{info['carrier']};{info['nav_system']};{info['network']};{info['country']};"
            str_line += f"{info['lat']:.2f};{info['lon']:.2f};{info['nmea']};{info['solution']};"
            str_line += f"{info['generator']};{info['compression']};{info['authentication']};"
            str_line += f"{info['fee']};{info['bitrate']}\r\n"
            sourcetable += str_line

        sourcetable += "ENDSOURCETABLE\r\n"

        try:
            conn.sendall(sourcetable.encode('utf-8'))
            logger.debug("Sent sourcetable")
        except Exception as e:
            logger.error(f"Failed to send sourcetable: {e}")

    def _send_response(self, conn: socket.socket, code: int, message: str, extra_headers: str = ""):
        """Send HTTP response to client"""
        response = f"HTTP/1.1 {code} {message}\r\n"
        response += "Server: LC29H-NTRIP-Server/1.0\r\n"
        response += extra_headers
        response += "\r\n"

        try:
            conn.sendall(response.encode('utf-8'))
        except:
            pass

    def _verify_auth(self, auth_header: str) -> bool:
        """Verify Basic authentication credentials"""
        try:
            if not auth_header.startswith("Basic "):
                return False

            encoded = auth_header[6:]
            decoded = base64.b64decode(encoded).decode('utf-8')
            username, password = decoded.split(":", 1)

            return username in self.credentials and self.credentials[username] == password

        except Exception as e:
            logger.warning(f"Authentication verification failed: {e}")
            return False

    def broadcast_rtcm(self, rtcm_data: bytes, mountpoint: str = None):
        """
        Broadcast RTCM data to all connected clients

        Args:
            rtcm_data: RTCM3 message bytes
            mountpoint: Optional specific mountpoint to broadcast to
        """
        if not rtcm_data:
            return

        disconnected_clients = []

        with self.clients_lock:
            for client in self.clients:
                # Filter by mountpoint if specified
                if mountpoint and client.mountpoint != mountpoint:
                    continue

                # Send data to client
                if not client.send_data(rtcm_data):
                    disconnected_clients.append(client)

            # Remove disconnected clients
            for client in disconnected_clients:
                logger.info(f"Client {client.addr} disconnected from {client.mountpoint}")
                self.clients.remove(client)
                client.close()

    def get_stats(self) -> dict:
        """Get server statistics"""
        with self.clients_lock:
            return {
                'active_clients': len(self.clients),
                'clients': [
                    {
                        'address': f"{c.addr[0]}:{c.addr[1]}",
                        'mountpoint': c.mountpoint,
                        'connected_at': c.connected_at.isoformat(),
                        'bytes_sent': c.bytes_sent
                    }
                    for c in self.clients
                ]
            }

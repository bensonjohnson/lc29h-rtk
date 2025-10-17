#!/usr/bin/env python3
"""
RTK Accuracy Test Script

This script connects to the NTRIP base station and monitors position
accuracy improvements when RTK corrections are received.

For best results, connect an LC29H rover module via serial to see
real-time RTK fix quality and position accuracy.
"""

import socket
import serial
import sys
import time
import argparse
import threading
from datetime import datetime
import base64
from typing import Optional
import math


class PositionMonitor:
    """Monitor GPS position and RTK fix quality"""

    def __init__(self, serial_port: str, baudrate: int = 115200):
        self.port = serial_port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.thread = None

        # Position data
        self.current_position = {
            'lat': 0.0,
            'lon': 0.0,
            'alt': 0.0,
            'fix_quality': 0,
            'fix_type': 'No Fix',
            'satellites': 0,
            'hdop': 0.0,
            'last_update': None
        }

        # Known reference position (for testing accuracy)
        self.reference_position = None

        # Statistics
        self.position_samples = []
        self.fix_quality_history = []

    def connect(self) -> bool:
        """Connect to GPS receiver"""
        try:
            print(f"Connecting to GPS on {self.port}...")
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1
            )
            print("✓ Connected to GPS receiver")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to GPS: {e}")
            return False

    def set_reference_position(self, lat: float, lon: float, alt: float):
        """Set known reference position for accuracy calculations"""
        self.reference_position = {'lat': lat, 'lon': lon, 'alt': alt}
        print(f"Reference position set: {lat:.8f}°, {lon:.8f}°, {alt:.2f}m")

    def start_monitoring(self):
        """Start background thread to read GPS data"""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def _read_loop(self):
        """Background thread to read NMEA sentences"""
        buffer = ""

        while self.running:
            try:
                if self.serial and self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting).decode('ascii', errors='ignore')
                    buffer += data

                    # Process complete NMEA sentences
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if line.startswith('$'):
                            self._process_nmea(line)

                time.sleep(0.01)

            except Exception as e:
                print(f"Error reading GPS: {e}")
                time.sleep(0.5)

    def _process_nmea(self, sentence: str):
        """Process NMEA sentence"""
        try:
            if 'GGA' in sentence:
                parts = sentence.split(',')
                if len(parts) > 9:
                    # Parse GGA sentence
                    lat_str = parts[2]
                    lat_dir = parts[3]
                    lon_str = parts[4]
                    lon_dir = parts[5]
                    fix = parts[6]
                    sats = parts[7]
                    hdop = parts[8]
                    alt = parts[9]

                    fix_types = {
                        '0': 'No Fix',
                        '1': 'GPS Fix',
                        '2': 'DGPS Fix',
                        '4': 'RTK Fixed',
                        '5': 'RTK Float',
                        '6': 'Dead Reckoning'
                    }

                    if lat_str and lon_str:
                        lat = self._nmea_to_decimal(lat_str, lat_dir)
                        lon = self._nmea_to_decimal(lon_str, lon_dir)

                        self.current_position.update({
                            'lat': lat,
                            'lon': lon,
                            'alt': float(alt) if alt else 0.0,
                            'fix_quality': int(fix) if fix else 0,
                            'fix_type': fix_types.get(fix, 'Unknown'),
                            'satellites': int(sats) if sats else 0,
                            'hdop': float(hdop) if hdop else 0.0,
                            'last_update': time.time()
                        })

                        # Store sample for statistics
                        self.position_samples.append({
                            'time': time.time(),
                            'lat': lat,
                            'lon': lon,
                            'alt': float(alt) if alt else 0.0,
                            'fix_quality': int(fix) if fix else 0
                        })

                        # Track fix quality over time
                        self.fix_quality_history.append(int(fix) if fix else 0)
                        if len(self.fix_quality_history) > 1000:
                            self.fix_quality_history.pop(0)

        except Exception as e:
            pass

    def _nmea_to_decimal(self, coord_str: str, direction: str) -> float:
        """Convert NMEA coordinate to decimal degrees"""
        if not coord_str:
            return 0.0

        if direction in ['N', 'S']:
            degrees = float(coord_str[:2])
            minutes = float(coord_str[2:])
        else:
            degrees = float(coord_str[:3])
            minutes = float(coord_str[3:])

        decimal = degrees + (minutes / 60.0)

        if direction in ['S', 'W']:
            decimal = -decimal

        return decimal

    def get_position_accuracy(self) -> Optional[dict]:
        """Calculate position accuracy vs reference"""
        if not self.reference_position:
            return None

        if self.current_position['last_update'] is None:
            return None

        # Check if data is stale
        if time.time() - self.current_position['last_update'] > 5:
            return None

        lat1 = self.current_position['lat']
        lon1 = self.current_position['lon']
        alt1 = self.current_position['alt']

        lat2 = self.reference_position['lat']
        lon2 = self.reference_position['lon']
        alt2 = self.reference_position['alt']

        if lat1 == 0.0 or lon1 == 0.0:
            return None

        # Calculate horizontal distance using Haversine formula
        R = 6371000  # Earth radius in meters

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = (math.sin(dlat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        horizontal_error = R * c

        # Vertical error
        vertical_error = abs(alt1 - alt2)

        # 3D error
        error_3d = math.sqrt(horizontal_error ** 2 + vertical_error ** 2)

        return {
            'horizontal_m': horizontal_error,
            'vertical_m': vertical_error,
            'error_3d_m': error_3d
        }

    def get_statistics(self) -> dict:
        """Get position statistics"""
        if len(self.position_samples) < 2:
            return {}

        # Get recent samples (last 30 seconds)
        recent_samples = [s for s in self.position_samples
                         if time.time() - s['time'] < 30]

        if not recent_samples:
            return {}

        # Calculate position scatter (precision)
        lats = [s['lat'] for s in recent_samples]
        lons = [s['lon'] for s in recent_samples]
        alts = [s['alt'] for s in recent_samples]

        lat_std = self._std_dev(lats)
        lon_std = self._std_dev(lons)
        alt_std = self._std_dev(alts)

        # Approximate horizontal scatter in meters
        lat_std_m = lat_std * 111320  # 1 degree lat ≈ 111.32 km
        lon_std_m = lon_std * 111320 * math.cos(math.radians(lats[0]))

        horizontal_scatter = math.sqrt(lat_std_m ** 2 + lon_std_m ** 2)

        # Fix quality distribution
        fix_counts = {}
        for sample in recent_samples:
            fq = sample['fix_quality']
            fix_counts[fq] = fix_counts.get(fq, 0) + 1

        return {
            'sample_count': len(recent_samples),
            'horizontal_scatter_m': horizontal_scatter,
            'vertical_scatter_m': alt_std,
            'fix_quality_distribution': fix_counts
        }

    def _std_dev(self, values: list) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)

    def disconnect(self):
        """Close GPS connection"""
        self.stop_monitoring()
        if self.serial:
            self.serial.close()


class NTRIPClient:
    """NTRIP client for receiving corrections"""

    def __init__(self, host: str, port: int, mountpoint: str,
                 username: str = None, password: str = None,
                 gps_serial: Optional[serial.Serial] = None):
        self.host = host
        self.port = port
        self.mountpoint = mountpoint
        self.username = username
        self.password = password
        self.gps_serial = gps_serial
        self.socket = None
        self.connected = False
        self.running = False

        # Statistics
        self.bytes_received = 0
        self.messages_received = 0

    def connect(self) -> bool:
        """Connect to NTRIP caster"""
        try:
            print(f"\nConnecting to NTRIP caster {self.host}:{self.port}...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port))

            # Build NTRIP request
            request = f"GET /{self.mountpoint} HTTP/1.1\r\n"
            request += f"Host: {self.host}\r\n"
            request += "User-Agent: NTRIP PythonClient/1.0\r\n"
            request += "Ntrip-Version: Ntrip/2.0\r\n"

            if self.username and self.password:
                auth_str = f"{self.username}:{self.password}"
                auth_bytes = auth_str.encode('ascii')
                auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
                request += f"Authorization: Basic {auth_b64}\r\n"

            request += "Connection: close\r\n"
            request += "\r\n"

            self.socket.send(request.encode('ascii'))
            response = self.socket.recv(4096).decode('ascii', errors='ignore')

            if "200 OK" in response or "ICY 200 OK" in response:
                print("✓ Connected to NTRIP caster")
                self.connected = True
                return True
            else:
                print(f"✗ NTRIP connection failed: {response[:200]}")
                return False

        except Exception as e:
            print(f"✗ NTRIP connection error: {e}")
            return False

    def receive_corrections(self, position_monitor: Optional[PositionMonitor] = None):
        """Receive and forward corrections to GPS"""
        self.running = True
        self.socket.settimeout(5.0)

        print("\n" + "=" * 70)
        print("RECEIVING RTK CORRECTIONS")
        print("=" * 70)
        print("Press Ctrl+C to stop\n")

        start_time = time.time()
        last_display = time.time()

        try:
            while self.running:
                try:
                    data = self.socket.recv(4096)
                    if not data:
                        print("\n✗ Connection closed")
                        break

                    self.bytes_received += len(data)

                    # Forward corrections to GPS if connected
                    if self.gps_serial and self.gps_serial.is_open:
                        self.gps_serial.write(data)

                    # Update display every 2 seconds
                    if time.time() - last_display >= 2.0:
                        elapsed = time.time() - start_time
                        self._display_status(elapsed, position_monitor)
                        last_display = time.time()

                except socket.timeout:
                    # Update display on timeout
                    elapsed = time.time() - start_time
                    self._display_status(elapsed, position_monitor)
                    last_display = time.time()

        except KeyboardInterrupt:
            print("\n\nStopped by user")

        self.running = False

    def _display_status(self, elapsed: float, monitor: Optional[PositionMonitor]):
        """Display real-time status"""
        byte_rate = self.bytes_received / elapsed if elapsed > 0 else 0

        # Build status line
        status = f"\r[{datetime.now().strftime('%H:%M:%S')}] "
        status += f"Corrections: {self.bytes_received:6d} bytes ({byte_rate:.0f} B/s)"

        if monitor:
            pos = monitor.current_position
            if pos['last_update'] and (time.time() - pos['last_update']) < 5:
                status += f" | Fix: {pos['fix_type']:12s} | Sats: {pos['satellites']:2d} | HDOP: {pos['hdop']:.1f}"

                # Show accuracy if reference is set
                accuracy = monitor.get_position_accuracy()
                if accuracy:
                    status += f" | Error: {accuracy['horizontal_m']:.3f}m (H) {accuracy['vertical_m']:.3f}m (V)"
            else:
                status += " | GPS: No data"

        print(status, end='', flush=True)

    def disconnect(self):
        """Close NTRIP connection"""
        self.running = False
        if self.socket:
            self.socket.close()
        self.connected = False


def main():
    parser = argparse.ArgumentParser(
        description='Test RTK accuracy with NTRIP corrections',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor corrections only (no GPS connected)
  python3 test_rtk_accuracy.py localhost 2101 BASE

  # Monitor with GPS rover connected
  python3 test_rtk_accuracy.py localhost 2101 BASE --gps /dev/ttyS0

  # Set reference position to measure accuracy
  python3 test_rtk_accuracy.py localhost 2101 BASE --gps /dev/ttyS0 \\
      --ref-lat 43.56497873 --ref-lon -116.59970771 --ref-alt 742.4959

  # With authentication
  python3 test_rtk_accuracy.py localhost 2101 BASE --gps /dev/ttyS0 \\
      -u user -p pass --ref-lat 43.565 --ref-lon -116.600 --ref-alt 742.5
        """
    )

    parser.add_argument('host', help='NTRIP caster hostname or IP')
    parser.add_argument('port', type=int, help='NTRIP caster port')
    parser.add_argument('mountpoint', help='NTRIP mountpoint')
    parser.add_argument('--gps', help='GPS serial port (e.g., /dev/ttyS0)')
    parser.add_argument('--baudrate', type=int, default=115200, help='GPS baud rate (default: 115200)')
    parser.add_argument('-u', '--username', help='NTRIP username')
    parser.add_argument('-p', '--password', help='NTRIP password')
    parser.add_argument('--ref-lat', type=float, help='Reference latitude for accuracy testing')
    parser.add_argument('--ref-lon', type=float, help='Reference longitude for accuracy testing')
    parser.add_argument('--ref-alt', type=float, help='Reference altitude for accuracy testing')

    args = parser.parse_args()

    position_monitor = None
    gps_serial = None

    # Connect to GPS if specified
    if args.gps:
        position_monitor = PositionMonitor(args.gps, args.baudrate)
        if not position_monitor.connect():
            sys.exit(1)

        gps_serial = position_monitor.serial

        # Set reference position if provided
        if args.ref_lat and args.ref_lon and args.ref_alt:
            position_monitor.set_reference_position(args.ref_lat, args.ref_lon, args.ref_alt)
        else:
            print("Note: No reference position set. Run with --ref-lat/lon/alt to measure accuracy")

        position_monitor.start_monitoring()
        time.sleep(2)  # Let GPS data start flowing

    # Connect to NTRIP
    ntrip = NTRIPClient(
        host=args.host,
        port=args.port,
        mountpoint=args.mountpoint,
        username=args.username,
        password=args.password,
        gps_serial=gps_serial
    )

    if not ntrip.connect():
        if position_monitor:
            position_monitor.disconnect()
        sys.exit(1)

    # Receive corrections
    try:
        ntrip.receive_corrections(position_monitor)
    finally:
        ntrip.disconnect()
        if position_monitor:
            # Print final statistics
            print("\n\n" + "=" * 70)
            print("FINAL STATISTICS")
            print("=" * 70)

            stats = position_monitor.get_statistics()
            if stats:
                print(f"\nPosition Precision (30s window):")
                print(f"  Horizontal scatter: {stats['horizontal_scatter_m']:.3f} m")
                print(f"  Vertical scatter:   {stats['vertical_scatter_m']:.3f} m")
                print(f"  Sample count:       {stats['sample_count']}")

                print(f"\nFix Quality Distribution:")
                fix_names = {0: 'No Fix', 1: 'GPS', 2: 'DGPS', 4: 'RTK Fixed', 5: 'RTK Float'}
                for fq, count in sorted(stats['fix_quality_distribution'].items()):
                    pct = (count / stats['sample_count']) * 100
                    print(f"  {fix_names.get(fq, f'Unknown ({fq})')}: {count} samples ({pct:.1f}%)")

            accuracy = position_monitor.get_position_accuracy()
            if accuracy:
                print(f"\nPosition Accuracy vs Reference:")
                print(f"  Horizontal error: {accuracy['horizontal_m']:.3f} m")
                print(f"  Vertical error:   {accuracy['vertical_m']:.3f} m")
                print(f"  3D error:         {accuracy['error_3d_m']:.3f} m")

            position_monitor.disconnect()


if __name__ == '__main__':
    main()

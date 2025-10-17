#!/usr/bin/env python3
"""
LC29H GPS Serial Communication Module
Handles serial communication with Quectel LC29H GNSS RTK module
"""

import serial
import logging
from typing import Optional, Callable
import threading
import time

logger = logging.getLogger(__name__)


class LC29HSerial:
    """Handle serial communication with LC29H GPS module"""

    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 115200, timeout: float = 1.0):
        """
        Initialize LC29H serial connection

        Args:
            port: Serial port device path
            baudrate: Communication speed (default 115200 for LC29H)
            timeout: Read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn: Optional[serial.Serial] = None
        self.running = False
        self.read_thread: Optional[threading.Thread] = None
        self.rtcm_callback: Optional[Callable[[bytes], None]] = None
        self.nmea_callback: Optional[Callable[[str], None]] = None

        # GPS status tracking
        self.gps_status = {
            'satellites': 0,
            'fix_quality': 0,
            'fix_type': 'No Fix',
            'hdop': 0.0,
            'last_update': None,
            'current_lat': 0.0,
            'current_lon': 0.0,
            'current_alt': 0.0
        }

        # Store configured base position for accuracy calculation
        self.base_position = {'lat': 0.0, 'lon': 0.0, 'alt': 0.0}

    def connect(self) -> bool:
        """
        Open serial connection to LC29H

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            logger.info(f"Connected to LC29H on {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            return False

    def disconnect(self):
        """Close serial connection"""
        self.stop_reading()
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("Disconnected from LC29H")

    def _lla_to_ecef(self, lat: float, lon: float, alt: float) -> tuple:
        """
        Convert WGS84 Latitude, Longitude, Altitude to ECEF coordinates

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            alt: Altitude in meters (ellipsoidal height)

        Returns:
            tuple: (x, y, z) in meters
        """
        import math

        # WGS84 ellipsoid constants
        a = 6378137.0  # Semi-major axis (equatorial radius) in meters
        f = 1 / 298.257223563  # Flattening
        e2 = 2 * f - f * f  # First eccentricity squared

        # Convert to radians
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)

        # Calculate radius of curvature in prime vertical
        N = a / math.sqrt(1 - e2 * math.sin(lat_rad) ** 2)

        # Calculate ECEF coordinates
        x = (N + alt) * math.cos(lat_rad) * math.cos(lon_rad)
        y = (N + alt) * math.cos(lat_rad) * math.sin(lon_rad)
        z = ((1 - e2) * N + alt) * math.sin(lat_rad)

        return x, y, z

    def configure_base_mode(self, lat: float, lon: float, alt: float):
        """
        Configure LC29H as RTK base station with fixed position
        Uses PQTM commands for proper LC29H(BS) initialization

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            alt: Altitude in meters (ellipsoidal height)
        """
        logger.info("Starting LC29H base station configuration...")

        # Store base position for accuracy calculations
        self.base_position = {'lat': lat, 'lon': lon, 'alt': alt}

        # Convert LLA to ECEF XYZ coordinates for PQTMCFGSVIN command
        x, y, z = self._lla_to_ecef(lat, lon, alt)
        logger.info(f"Base position - LAT:{lat:.8f}, LON:{lon:.8f}, ALT:{alt:.4f}m")
        logger.info(f"ECEF coordinates - X:{x:.4f}, Y:{y:.4f}, Z:{z:.4f}")

        # Step 1: Set receiver to base mode
        # PQTMCFGRCVRMODE,W,2 = Write, Mode 2 (Base Station)
        cmd_str = "PQTMCFGRCVRMODE,W,2"
        cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
        self._send_command(cmd)
        logger.info("Set receiver mode to base station")
        time.sleep(0.2)

        # Step 2: Save configuration
        cmd_str = "PQTMSAVEPAR"
        cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
        self._send_command(cmd)
        logger.info("Saved base mode configuration")
        time.sleep(0.5)

        # Step 3: Configure base position with ECEF coordinates
        # PQTMCFGSVIN,W,2,0,0,x,y,z
        # W=write, 2=fixed position mode, 0,0=survey-in params (unused for fixed)
        cmd_str = f"PQTMCFGSVIN,W,2,0,0,{x:.4f},{y:.4f},{z:.4f}"
        cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
        self._send_command(cmd)
        logger.info("Configured fixed base position")
        time.sleep(0.2)

        # Step 4: Save configuration again
        cmd_str = "PQTMSAVEPAR"
        cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
        self._send_command(cmd)
        logger.info("Saved position configuration")
        time.sleep(0.2)

        logger.info("Base station configuration complete")

    def enable_rtcm_output(self, messages: list = None):
        """
        Enable RTCM3 message output from LC29H using PAIR commands

        Args:
            messages: List of RTCM message types to enable
                     Default: [1005, 1074, 1084, 1094, 1124, 1230]
        """
        if messages is None:
            # Standard RTK base station messages
            messages = [1005, 1074, 1084, 1094, 1124, 1230]

        logger.info("Enabling RTCM3 output...")

        # Enable RTCM3 MSM4 messages (MSM7 doesn't save properly per LC29H docs)
        # PAIR432,1 enables MSM4 messages
        cmd_str = "PAIR432,1"
        cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
        self._send_command(cmd)
        logger.info("Enabled RTCM3 MSM4 messages")
        time.sleep(0.1)

        # PAIR434,1 enables antenna position output (1005)
        cmd_str = "PAIR434,1"
        cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
        self._send_command(cmd)
        logger.info("Enabled RTCM3 1005 antenna position messages")
        time.sleep(0.1)

        # Enable NMEA GGA output for GPS status monitoring
        # PAIR062,0,01 enables GGA on output
        cmd_str = "PAIR062,0,01"
        cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
        self._send_command(cmd)
        logger.info("Enabled NMEA GGA output")
        time.sleep(0.1)

        # Save configuration
        cmd_str = "PQTMSAVEPAR"
        cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
        self._send_command(cmd)
        logger.info("Saved RTCM configuration")

        logger.info(f"RTCM output configuration complete")

    def _calc_checksum(self, sentence: str) -> str:
        """Calculate NMEA checksum (XOR of all characters between $ and *)"""
        checksum = 0
        for char in sentence:
            checksum ^= ord(char)
        return f"{checksum:02X}"

    def _send_command(self, command: str):
        """Send command to LC29H"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.write(command.encode('ascii'))
            logger.debug(f"Sent command: {command.strip()}")

    def start_reading(self):
        """Start background thread to read data from GPS"""
        if self.running:
            logger.warning("Already reading from GPS")
            return

        self.running = True
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()
        logger.info("Started GPS data reading thread")

    def stop_reading(self):
        """Stop background reading thread"""
        if self.running:
            self.running = False
            if self.read_thread:
                self.read_thread.join(timeout=2.0)
            logger.info("Stopped GPS data reading thread")

    def _read_loop(self):
        """Background thread to continuously read GPS data"""
        rtcm_buffer = bytearray()
        nmea_buffer = bytearray()

        while self.running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)

                    # Process data - could be NMEA or RTCM3
                    for byte in data:
                        # RTCM3 messages start with 0xD3
                        if byte == 0xD3:
                            if rtcm_buffer:
                                self._process_rtcm(bytes(rtcm_buffer))
                            rtcm_buffer = bytearray([byte])
                        elif rtcm_buffer:
                            rtcm_buffer.append(byte)
                            # RTCM message complete check
                            if len(rtcm_buffer) >= 3:
                                msg_len = ((rtcm_buffer[1] & 0x03) << 8) | rtcm_buffer[2]
                                # 3 header + msg_len + 3 CRC24
                                if len(rtcm_buffer) >= msg_len + 6:
                                    self._process_rtcm(bytes(rtcm_buffer[:msg_len + 6]))
                                    rtcm_buffer = bytearray()
                        else:
                            # NMEA sentence detection (starts with $, ends with \n)
                            if byte == ord(b'$'):
                                nmea_buffer = bytearray([byte])
                            elif nmea_buffer:
                                nmea_buffer.append(byte)
                                if byte == ord(b'\n'):
                                    # Complete NMEA sentence
                                    try:
                                        sentence = nmea_buffer.decode('ascii', errors='ignore').strip()
                                        self._process_nmea(sentence)
                                    except:
                                        pass
                                    nmea_buffer = bytearray()

                time.sleep(0.01)  # Small delay to prevent CPU spinning

            except serial.SerialException as e:
                logger.error(f"Serial read error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in read loop: {e}")

    def _process_rtcm(self, rtcm_data: bytes):
        """Process received RTCM3 message"""
        if len(rtcm_data) < 6:
            return

        # Verify RTCM3 frame
        if rtcm_data[0] == 0xD3:
            msg_type = (rtcm_data[3] << 4) | (rtcm_data[4] >> 4)
            logger.debug(f"Received RTCM3 message type {msg_type}, length {len(rtcm_data)}")

            if self.rtcm_callback:
                self.rtcm_callback(rtcm_data)

    def _process_nmea(self, sentence: str):
        """Process NMEA sentence and extract GPS status"""
        if not sentence.startswith('$'):
            return

        try:
            # Parse GGA sentence for fix quality and satellite count
            if 'GGA' in sentence:
                parts = sentence.split(',')
                if len(parts) > 9:
                    # Fix quality: 0=no fix, 1=GPS, 2=DGPS, 4=RTK fixed, 5=RTK float
                    fix = parts[6]
                    sats = parts[7]
                    hdop = parts[8]
                    alt = parts[9]

                    # Parse position data
                    lat_str = parts[2]
                    lat_dir = parts[3]
                    lon_str = parts[4]
                    lon_dir = parts[5]

                    fix_types = {
                        '0': 'No Fix',
                        '1': 'GPS Fix',
                        '2': 'DGPS Fix',
                        '4': 'RTK Fixed',
                        '5': 'RTK Float',
                        '6': 'Dead Reckoning'
                    }

                    try:
                        self.gps_status['fix_quality'] = int(fix) if fix else 0
                        self.gps_status['fix_type'] = fix_types.get(fix, f'Unknown ({fix})')
                        self.gps_status['satellites'] = int(sats) if sats else 0
                        self.gps_status['hdop'] = float(hdop) if hdop else 0.0

                        # Convert NMEA position format to decimal degrees
                        if lat_str and lon_str:
                            lat = self._nmea_to_decimal(lat_str, lat_dir)
                            lon = self._nmea_to_decimal(lon_str, lon_dir)
                            self.gps_status['current_lat'] = lat
                            self.gps_status['current_lon'] = lon
                            self.gps_status['current_alt'] = float(alt) if alt else 0.0

                        self.gps_status['last_update'] = time.time()
                    except ValueError:
                        pass

            # Call user callback if set
            if self.nmea_callback:
                self.nmea_callback(sentence)

        except Exception as e:
            logger.debug(f"Error parsing NMEA: {e}")

    def _nmea_to_decimal(self, coord_str: str, direction: str) -> float:
        """
        Convert NMEA coordinate format to decimal degrees

        Args:
            coord_str: NMEA coordinate string (e.g., "4356.12345" for lat or "11635.12345" for lon)
            direction: Direction indicator ('N', 'S', 'E', 'W')

        Returns:
            Decimal degrees
        """
        if not coord_str:
            return 0.0

        # For latitude: DDMM.MMMMM, for longitude: DDDMM.MMMMM
        if direction in ['N', 'S']:
            # Latitude: first 2 digits are degrees
            degrees = float(coord_str[:2])
            minutes = float(coord_str[2:])
        else:
            # Longitude: first 3 digits are degrees
            degrees = float(coord_str[:3])
            minutes = float(coord_str[3:])

        decimal = degrees + (minutes / 60.0)

        # Apply direction
        if direction in ['S', 'W']:
            decimal = -decimal

        return decimal

    def get_gps_status(self) -> dict:
        """Get current GPS status with position accuracy"""
        status = self.gps_status.copy()
        # Check if data is stale (no update in 5 seconds)
        if status['last_update']:
            if time.time() - status['last_update'] > 5:
                status['stale'] = True
            else:
                status['stale'] = False
        else:
            status['stale'] = True

        # Calculate position accuracy vs fixed base position
        if (self.base_position['lat'] != 0.0 and
            status['current_lat'] != 0.0 and
            not status['stale']):
            accuracy = self._calculate_position_error(
                status['current_lat'], status['current_lon'], status['current_alt'],
                self.base_position['lat'], self.base_position['lon'], self.base_position['alt']
            )
            status['position_accuracy'] = accuracy
        else:
            status['position_accuracy'] = None

        return status

    def _calculate_position_error(self, current_lat: float, current_lon: float, current_alt: float,
                                    base_lat: float, base_lon: float, base_alt: float) -> dict:
        """
        Calculate position error between current GPS position and fixed base position

        Args:
            current_lat, current_lon, current_alt: Current GPS position
            base_lat, base_lon, base_alt: Configured base station position

        Returns:
            dict with horizontal, vertical, and 3D position errors in meters
        """
        import math

        # Calculate horizontal distance using Haversine formula
        R = 6371000  # Earth radius in meters

        lat1 = math.radians(current_lat)
        lat2 = math.radians(base_lat)
        dlat = math.radians(base_lat - current_lat)
        dlon = math.radians(base_lon - current_lon)

        a = (math.sin(dlat / 2) ** 2 +
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        horizontal_error = R * c

        # Vertical error (altitude difference)
        vertical_error = abs(current_alt - base_alt)

        # 3D position error
        error_3d = math.sqrt(horizontal_error ** 2 + vertical_error ** 2)

        return {
            'horizontal_m': round(horizontal_error, 3),
            'vertical_m': round(vertical_error, 3),
            'error_3d_m': round(error_3d, 3)
        }

    def set_rtcm_callback(self, callback: Callable[[bytes], None]):
        """Set callback function to handle RTCM messages"""
        self.rtcm_callback = callback

    def set_nmea_callback(self, callback: Callable[[str], None]):
        """Set callback function to handle NMEA sentences"""
        self.nmea_callback = callback

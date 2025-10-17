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
            'last_update': None
        }

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

    def configure_base_mode(self, lat: float, lon: float, alt: float):
        """
        Configure LC29H as RTK base station with fixed position

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            alt: Altitude in meters (ellipsoidal height)
        """
        # Send command to set base mode with fixed position
        # PAIR065: Set mode to base station
        cmd = f"$PAIR065,0,1*{self._calc_checksum('PAIR065,0,1')}\r\n"
        self._send_command(cmd)
        time.sleep(0.1)

        # PAIR062: Set fixed base position (lat, lon, alt)
        pos_cmd = f"PAIR062,{lat:.9f},{lon:.9f},{alt:.4f}"
        cmd = f"${pos_cmd}*{self._calc_checksum(pos_cmd)}\r\n"
        self._send_command(cmd)
        logger.info(f"Configured base mode at LAT:{lat}, LON:{lon}, ALT:{alt}")

    def enable_rtcm_output(self, messages: list = None):
        """
        Enable RTCM3 message output from LC29H

        Args:
            messages: List of RTCM message types to enable
                     Default: [1005, 1074, 1084, 1094, 1124, 1230]
        """
        if messages is None:
            # Standard RTK base station messages
            messages = [1005, 1074, 1084, 1094, 1124, 1230]

        # PAIR050: Enable RTCM3 output
        for msg_type in messages:
            cmd_str = f"PAIR050,{msg_type},1"
            cmd = f"${cmd_str}*{self._calc_checksum(cmd_str)}\r\n"
            self._send_command(cmd)
            time.sleep(0.05)

        logger.info(f"Enabled RTCM messages: {messages}")

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
                        self.gps_status['last_update'] = time.time()
                    except ValueError:
                        pass

            # Call user callback if set
            if self.nmea_callback:
                self.nmea_callback(sentence)

        except Exception as e:
            logger.debug(f"Error parsing NMEA: {e}")

    def get_gps_status(self) -> dict:
        """Get current GPS status"""
        status = self.gps_status.copy()
        # Check if data is stale (no update in 5 seconds)
        if status['last_update']:
            if time.time() - status['last_update'] > 5:
                status['stale'] = True
            else:
                status['stale'] = False
        else:
            status['stale'] = True
        return status

    def set_rtcm_callback(self, callback: Callable[[bytes], None]):
        """Set callback function to handle RTCM messages"""
        self.rtcm_callback = callback

    def set_nmea_callback(self, callback: Callable[[str], None]):
        """Set callback function to handle NMEA sentences"""
        self.nmea_callback = callback

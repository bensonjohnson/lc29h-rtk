#!/usr/bin/env python3
"""
RTCM3 Message Parser and Handler
Utilities for parsing and validating RTCM3 messages from LC29H
"""

import struct
import logging

logger = logging.getLogger(__name__)


class RTCM3Parser:
    """Parse and validate RTCM3 messages"""

    # RTCM3 message type names
    MESSAGE_TYPES = {
        1001: "GPS L1 RTK Observables",
        1002: "GPS Extended L1 RTK Observables",
        1003: "GPS L1/L2 RTK Observables",
        1004: "GPS Extended L1/L2 RTK Observables",
        1005: "Stationary RTK Reference Station ARP",
        1006: "Stationary RTK Reference Station ARP with Height",
        1007: "Antenna Descriptor",
        1008: "Antenna Descriptor & Serial Number",
        1009: "GLONASS L1 RTK Observables",
        1010: "GLONASS Extended L1 RTK Observables",
        1011: "GLONASS L1/L2 RTK Observables",
        1012: "GLONASS Extended L1/L2 RTK Observables",
        1013: "System Parameters",
        1019: "GPS Ephemeris",
        1020: "GLONASS Ephemeris",
        1033: "Receiver and Antenna Descriptors",
        1074: "GPS MSM4",
        1075: "GPS MSM5",
        1076: "GPS MSM6",
        1077: "GPS MSM7",
        1084: "GLONASS MSM4",
        1085: "GLONASS MSM5",
        1086: "GLONASS MSM6",
        1087: "GLONASS MSM7",
        1094: "Galileo MSM4",
        1095: "Galileo MSM5",
        1096: "Galileo MSM6",
        1097: "Galileo MSM7",
        1124: "BeiDou MSM4",
        1125: "BeiDou MSM5",
        1126: "BeiDou MSM6",
        1127: "BeiDou MSM7",
        1230: "GLONASS Code-Phase Biases",
    }

    @staticmethod
    def validate_message(data: bytes) -> tuple[bool, int, int]:
        """
        Validate RTCM3 message format and checksum

        Args:
            data: Complete RTCM3 message bytes

        Returns:
            Tuple of (is_valid, message_type, message_length)
        """
        if len(data) < 6:
            return False, 0, 0

        # Check preamble (0xD3)
        if data[0] != 0xD3:
            return False, 0, 0

        # Extract message length (10 bits)
        msg_len = ((data[1] & 0x03) << 8) | data[2]

        # Extract message type (12 bits from first 2 bytes of payload)
        if len(data) >= 5:
            msg_type = (data[3] << 4) | (data[4] >> 4)
        else:
            msg_type = 0

        # Check total length
        expected_len = msg_len + 6  # 3 header + msg_len + 3 CRC24
        if len(data) != expected_len:
            # Only log if this looks like a real RTCM message (not random noise)
            if msg_type > 0:
                logger.debug(f"RTCM message length mismatch: expected {expected_len}, got {len(data)}, type {msg_type}")
            return False, msg_type, msg_len

        # Validate CRC24Q
        if not RTCM3Parser._verify_crc24q(data):
            # Only log known message types (likely corruption of real data)
            if msg_type in RTCM3Parser.MESSAGE_TYPES:
                logger.debug(f"RTCM message type {msg_type} failed CRC24 check")
            return False, msg_type, msg_len

        return True, msg_type, msg_len

    @staticmethod
    def _verify_crc24q(data: bytes) -> bool:
        """
        Verify RTCM3 CRC24Q checksum

        Args:
            data: Complete RTCM3 message including CRC

        Returns:
            True if CRC is valid
        """
        if len(data) < 6:
            return False

        # CRC is last 3 bytes
        msg_crc = (data[-3] << 16) | (data[-2] << 8) | data[-1]

        # Calculate CRC for all bytes except the CRC itself
        calc_crc = RTCM3Parser._calc_crc24q(data[:-3])

        return msg_crc == calc_crc

    @staticmethod
    def _calc_crc24q(data: bytes) -> int:
        """
        Calculate CRC24Q checksum (Qualcomm CRC-24)

        Args:
            data: Data bytes to checksum

        Returns:
            24-bit CRC value
        """
        crc = 0
        for byte in data:
            crc ^= (byte << 16)
            for _ in range(8):
                crc <<= 1
                if crc & 0x1000000:
                    crc ^= 0x1864CFB
        return crc & 0xFFFFFF

    @staticmethod
    def parse_message_1005(data: bytes) -> dict:
        """
        Parse RTCM message 1005 - Stationary RTK Reference Station ARP

        Args:
            data: RTCM message payload (without header and CRC)

        Returns:
            Dictionary with station coordinates
        """
        if len(data) < 19:
            return {}

        # Skip message type (12 bits) and extract fields
        # Reference: RTCM 10403.3 standard
        bits = ''.join(f'{b:08b}' for b in data)

        # Station ID (12 bits)
        station_id = int(bits[12:24], 2)

        # ITRF realization year (6 bits)
        itrf = int(bits[24:30], 2)

        # GPS indicator, GLONASS, Galileo, Reserved (4 bits total)
        # Skip to ECEF coordinates

        # ECEF X (38 bits, signed, 0.0001 m)
        ecef_x_raw = int(bits[34:72], 2)
        if ecef_x_raw & (1 << 37):  # Check sign bit
            ecef_x_raw -= (1 << 38)
        ecef_x = ecef_x_raw * 0.0001

        # ECEF Y (38 bits, signed, 0.0001 m)
        ecef_y_raw = int(bits[72:110], 2)
        if ecef_y_raw & (1 << 37):
            ecef_y_raw -= (1 << 38)
        ecef_y = ecef_y_raw * 0.0001

        # ECEF Z (38 bits, signed, 0.0001 m)
        ecef_z_raw = int(bits[110:148], 2)
        if ecef_z_raw & (1 << 37):
            ecef_z_raw -= (1 << 38)
        ecef_z = ecef_z_raw * 0.0001

        return {
            'message_type': 1005,
            'station_id': station_id,
            'itrf': itrf,
            'ecef_x': ecef_x,
            'ecef_y': ecef_y,
            'ecef_z': ecef_z
        }

    @staticmethod
    def get_message_info(msg_type: int) -> str:
        """Get human-readable message type description"""
        return RTCM3Parser.MESSAGE_TYPES.get(msg_type, f"Unknown Type {msg_type}")


class RTCMMessageBuffer:
    """Buffer for collecting RTCM3 messages from serial stream"""

    def __init__(self):
        self.buffer = bytearray()
        self.messages = []

    def add_data(self, data: bytes):
        """
        Add data to buffer and extract complete RTCM messages

        Args:
            data: Incoming bytes from serial port
        """
        self.buffer.extend(data)
        self._extract_messages()

    def _extract_messages(self):
        """Extract complete RTCM messages from buffer"""
        while len(self.buffer) >= 6:
            # Look for RTCM3 preamble (0xD3)
            preamble_idx = self.buffer.find(0xD3)

            if preamble_idx == -1:
                # No preamble found, clear buffer
                self.buffer.clear()
                return

            if preamble_idx > 0:
                # Remove data before preamble
                self.buffer = self.buffer[preamble_idx:]

            # Check if we have enough bytes for header
            if len(self.buffer) < 3:
                return

            # Extract message length
            msg_len = ((self.buffer[1] & 0x03) << 8) | self.buffer[2]
            total_len = msg_len + 6  # 3 header + msg_len + 3 CRC

            # Check if complete message is available
            if len(self.buffer) < total_len:
                return  # Wait for more data

            # Extract complete message
            msg_data = bytes(self.buffer[:total_len])
            self.buffer = self.buffer[total_len:]

            # Validate and store message
            is_valid, msg_type, _ = RTCM3Parser.validate_message(msg_data)
            if is_valid:
                self.messages.append(msg_data)
                logger.debug(f"Extracted RTCM message type {msg_type}, length {len(msg_data)}")
            else:
                # Only log if it's a recognized message type (not noise)
                if msg_type > 0 and msg_type in RTCM3Parser.MESSAGE_TYPES:
                    logger.debug(f"Invalid RTCM message discarded, type {msg_type}")

    def get_messages(self) -> list[bytes]:
        """
        Get all complete messages and clear internal list

        Returns:
            List of complete RTCM message bytes
        """
        messages = self.messages.copy()
        self.messages.clear()
        return messages

    def has_messages(self) -> bool:
        """Check if any complete messages are available"""
        return len(self.messages) > 0

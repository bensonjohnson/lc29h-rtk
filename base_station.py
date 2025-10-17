#!/usr/bin/env python3
"""
LC29H RTK Base Station Main Script
Runs NTRIP server broadcasting RTK corrections from LC29H GPS module
"""

import sys
import signal
import logging
import yaml
import time
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

from gps_serial import LC29HSerial
from ntrip_server import NTRIPServer
from rtcm_parser import RTCM3Parser, RTCMMessageBuffer
from web_interface import WebInterface


class RTKBaseStation:
    """RTK Base Station coordinator"""

    def __init__(self, config_file: str = 'config.yaml'):
        """
        Initialize RTK base station

        Args:
            config_file: Path to configuration file
        """
        self.config = self._load_config(config_file)
        self.logger = self._setup_logging()
        self.gps = None
        self.ntrip = None
        self.web = None
        self.running = False
        self.rtcm_buffer = RTCMMessageBuffer()
        self.stats = {
            'rtcm_messages': 0,
            'bytes_broadcast': 0,
            'start_time': None
        }

    def _load_config(self, config_file: str) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: Configuration file '{config_file}' not found")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Error parsing configuration file: {e}")
            sys.exit(1)

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO'))

        # Create logger
        logger = logging.getLogger()
        logger.setLevel(log_level)

        # Remove existing handlers
        logger.handlers.clear()

        # Console handler
        if log_config.get('console', True):
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_format = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(console_format)
            logger.addHandler(console_handler)

        # File handler
        log_file = log_config.get('file')
        if log_file:
            # Create log directory if it doesn't exist
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=log_config.get('max_bytes', 10485760),
                backupCount=log_config.get('backup_count', 5)
            )
            file_handler.setLevel(log_level)
            file_format = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_format)
            logger.addHandler(file_handler)

        return logger

    def start(self):
        """Start RTK base station"""
        self.logger.info("=" * 60)
        self.logger.info("LC29H RTK Base Station Starting...")
        self.logger.info("=" * 60)

        # Initialize GPS serial connection
        serial_config = self.config['serial']
        self.gps = LC29HSerial(
            port=serial_config['port'],
            baudrate=serial_config['baudrate'],
            timeout=serial_config.get('timeout', 1.0)
        )

        if not self.gps.connect():
            self.logger.error("Failed to connect to GPS module")
            return False

        # Configure LC29H as base station
        base_config = self.config['base_station']
        self.logger.info(f"Configuring base station position:")
        self.logger.info(f"  LAT: {base_config['latitude']:.8f}°")
        self.logger.info(f"  LON: {base_config['longitude']:.8f}°")
        self.logger.info(f"  ALT: {base_config['altitude']:.2f} m")

        self.gps.configure_base_mode(
            lat=base_config['latitude'],
            lon=base_config['longitude'],
            alt=base_config['altitude']
        )

        # Enable RTCM output
        rtcm_config = self.config['rtcm']
        self.logger.info(f"Enabling RTCM messages: {rtcm_config['messages']}")
        self.gps.enable_rtcm_output(rtcm_config['messages'])

        # Set RTCM callback
        self.gps.set_rtcm_callback(self._handle_rtcm_data)

        # Start GPS reading
        self.gps.start_reading()

        # Initialize NTRIP server
        ntrip_config = self.config['ntrip']
        self.ntrip = NTRIPServer(
            host=ntrip_config['host'],
            port=ntrip_config['port']
        )

        # Configure authentication if enabled
        auth_config = ntrip_config.get('authentication', {})
        if auth_config.get('enabled', False):
            self.ntrip.set_authentication(
                auth_config['username'],
                auth_config['password']
            )
            self.logger.info(f"Authentication enabled for user: {auth_config['username']}")

        # Add mountpoint
        mp_config = ntrip_config['mountpoint']
        station_config = self.config['station']
        self.ntrip.add_mountpoint(
            name=mp_config['name'],
            identifier=mp_config['identifier'],
            format=mp_config['format'],
            format_details=mp_config['format_details'],
            carrier=station_config['carrier'],
            nav_system=station_config['nav_system'],
            network=station_config['network'],
            country=station_config['country'],
            lat=base_config['latitude'],
            lon=base_config['longitude']
        )

        # Start NTRIP server
        if not self.ntrip.start():
            self.logger.error("Failed to start NTRIP server")
            self.gps.disconnect()
            return False

        self.running = True
        self.stats['start_time'] = time.time()

        # Start web interface
        web_config = self.config.get('web', {})
        if web_config.get('enabled', True):
            web_host = web_config.get('host', '0.0.0.0')
            web_port = web_config.get('port', 5000)
            self.web = WebInterface(self, host=web_host, port=web_port)
            self.web.start()
            self.logger.info(f"Web interface available at http://{self._get_ip_address()}:{web_port}")

        self.logger.info("=" * 60)
        self.logger.info(f"RTK Base Station running on port {ntrip_config['port']}")
        self.logger.info(f"Mountpoint: /{mp_config['name']}")
        self.logger.info(f"NTRIP URL: ntrip://{self._get_ip_address()}:{ntrip_config['port']}/{mp_config['name']}")
        self.logger.info("=" * 60)

        return True

    def stop(self):
        """Stop RTK base station"""
        self.logger.info("Stopping RTK Base Station...")
        self.running = False

        if self.ntrip:
            self.ntrip.stop()

        if self.gps:
            self.gps.disconnect()

        self._print_stats()
        self.logger.info("RTK Base Station stopped")

    def _handle_rtcm_data(self, rtcm_data: bytes):
        """
        Handle RTCM data received from GPS

        Args:
            rtcm_data: RTCM3 message bytes
        """
        # Validate message
        is_valid, msg_type, msg_len = RTCM3Parser.validate_message(rtcm_data)

        if is_valid:
            # Broadcast to NTRIP clients
            if self.ntrip:
                self.ntrip.broadcast_rtcm(rtcm_data)
                self.stats['rtcm_messages'] += 1
                self.stats['bytes_broadcast'] += len(rtcm_data)

                # Log message info periodically
                if self.stats['rtcm_messages'] % 100 == 0:
                    self.logger.debug(
                        f"RTCM stats - Messages: {self.stats['rtcm_messages']}, "
                        f"Bytes: {self.stats['bytes_broadcast']}, "
                        f"Clients: {len(self.ntrip.clients)}"
                    )
        else:
            # Only log warnings for recognized message types (not noise/partial data)
            if msg_type > 0 and msg_type in RTCM3Parser.MESSAGE_TYPES:
                self.logger.warning(f"Invalid RTCM message received, type {msg_type}")

    def _print_stats(self):
        """Print session statistics"""
        if self.stats['start_time']:
            uptime = time.time() - self.stats['start_time']
            self.logger.info("Session Statistics:")
            self.logger.info(f"  Uptime: {uptime:.1f} seconds ({uptime/3600:.2f} hours)")
            self.logger.info(f"  RTCM Messages: {self.stats['rtcm_messages']}")
            self.logger.info(f"  Bytes Broadcast: {self.stats['bytes_broadcast']}")
            if uptime > 0:
                self.logger.info(f"  Avg Rate: {self.stats['rtcm_messages']/uptime:.2f} msg/sec")

    def _get_ip_address(self) -> str:
        """Get system IP address for display"""
        import socket
        try:
            # Connect to external address to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "localhost"

    def run(self):
        """Main run loop"""
        if not self.start():
            return 1

        # Setup signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            self.logger.info("\nReceived shutdown signal")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Status update loop
        try:
            while self.running:
                time.sleep(10)

                # Print status update
                if self.ntrip:
                    stats = self.ntrip.get_stats()
                    if stats['active_clients'] > 0:
                        self.logger.info(
                            f"Active clients: {stats['active_clients']}, "
                            f"RTCM messages sent: {self.stats['rtcm_messages']}"
                        )

        except KeyboardInterrupt:
            self.logger.info("\nShutdown requested")
            self.stop()
            return 0

        return 0


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='LC29H RTK Base Station - NTRIP Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run with default config.yaml
  %(prog)s -c myconfig.yaml   # Run with custom config file
  %(prog)s --check-serial     # Check if GPS serial port is accessible

For more information, see the README.md file.
        """
    )

    parser.add_argument(
        '-c', '--config',
        default='config.yaml',
        help='Configuration file path (default: config.yaml)'
    )

    parser.add_argument(
        '--check-serial',
        action='store_true',
        help='Check if serial port is accessible and exit'
    )

    parser.add_argument(
        '--no-web',
        action='store_true',
        help='Disable web interface'
    )

    args = parser.parse_args()

    # Check serial port if requested
    if args.check_serial:
        config = yaml.safe_load(open(args.config))
        port = config['serial']['port']
        if os.path.exists(port):
            print(f"✓ Serial port {port} exists")
            # Check permissions
            if os.access(port, os.R_OK | os.W_OK):
                print(f"✓ Serial port {port} is readable and writable")
                return 0
            else:
                print(f"✗ Serial port {port} is not accessible")
                print(f"  Run: sudo chmod 666 {port}")
                print(f"  Or add user to dialout group: sudo usermod -a -G dialout $USER")
                return 1
        else:
            print(f"✗ Serial port {port} does not exist")
            print(f"  Available serial ports:")
            for dev in Path('/dev').glob('tty*'):
                if 'ttyS' in str(dev) or 'ttyAMA' in str(dev) or 'USB' in str(dev):
                    print(f"    {dev}")
            return 1

    # Run base station
    base_station = RTKBaseStation(args.config)

    # Override web interface setting if --no-web flag is provided
    if args.no_web:
        if 'web' not in base_station.config:
            base_station.config['web'] = {}
        base_station.config['web']['enabled'] = False

    return base_station.run()


if __name__ == '__main__':
    sys.exit(main())

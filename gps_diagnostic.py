#!/usr/bin/env python3
"""
GPS Diagnostic Tool
Verify LC29H GPS is connected and receiving data
"""

import serial
import time
import sys
import argparse

def test_serial_connection(port='/dev/ttyS0', baudrate=115200, duration=5):
    """
    Test serial connection and display incoming data

    Args:
        port: Serial port path
        baudrate: Communication speed
        duration: How long to listen (seconds)
    """
    print("=" * 70)
    print("LC29H GPS Diagnostic Tool")
    print("=" * 70)
    print(f"\nSerial Port: {port}")
    print(f"Baudrate: {baudrate}")
    print(f"Listening for {duration} seconds...\n")
    print("-" * 70)

    try:
        ser = serial.Serial(port, baudrate, timeout=1)

        nmea_count = 0
        rtcm_count = 0
        total_bytes = 0
        start_time = time.time()

        print("Receiving data:\n")

        while time.time() - start_time < duration:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                total_bytes += len(data)

                # Try to decode as text (NMEA)
                try:
                    text = data.decode('ascii', errors='ignore')
                    lines = text.split('\n')
                    for line in lines:
                        if line.startswith('$'):
                            nmea_count += 1
                            # Print first few NMEA sentences
                            if nmea_count <= 5:
                                print(f"  NMEA: {line.strip()}")
                except:
                    pass

                # Check for RTCM (binary starting with 0xD3)
                for i in range(len(data)):
                    if data[i] == 0xD3:
                        rtcm_count += 1
                        if rtcm_count <= 3:
                            print(f"  RTCM: Detected binary message starting at byte {i}")

            time.sleep(0.1)

        ser.close()

        print("\n" + "-" * 70)
        print("\nDiagnostic Results:")
        print("=" * 70)

        elapsed = time.time() - start_time

        if total_bytes == 0:
            print("❌ NO DATA RECEIVED")
            print("\nPossible issues:")
            print("  - GPS module not powered")
            print("  - Wrong serial port")
            print("  - Incorrect baudrate")
            print("  - Wiring problem (TX/RX swapped?)")
            return False

        print(f"✓ Total bytes received: {total_bytes}")
        print(f"✓ Data rate: {total_bytes/elapsed:.1f} bytes/sec")

        if nmea_count > 0:
            print(f"✓ NMEA sentences detected: {nmea_count}")
            print(f"  Rate: {nmea_count/elapsed:.1f} sentences/sec")
        else:
            print("⚠ No NMEA sentences detected")

        if rtcm_count > 0:
            print(f"✓ RTCM messages detected: {rtcm_count}")
            print(f"  Rate: {rtcm_count/elapsed:.1f} messages/sec")
            print("  → Base station mode is active!")
        else:
            print("⚠ No RTCM messages detected")
            print("  → Base station mode may not be configured")

        print("\n" + "=" * 70)

        if nmea_count > 0 or rtcm_count > 0:
            print("✓ GPS CONNECTION IS WORKING")
            if rtcm_count > 0:
                print("✓ BASE STATION MODE IS ACTIVE")
            return True
        else:
            print("⚠ GPS is sending data but format is unexpected")
            return True

    except serial.SerialException as e:
        print(f"\n❌ Serial port error: {e}")
        print("\nPossible fixes:")
        print(f"  - Check permissions: sudo chmod 666 {port}")
        print(f"  - Check if port exists: ls -l {port}")
        print("  - Run with sudo: sudo python3 gps_diagnostic.py")
        return False
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def check_satellite_info(port='/dev/ttyS0', baudrate=115200, duration=10):
    """
    Parse NMEA sentences to show satellite information
    """
    print("\n" + "=" * 70)
    print("Satellite Information")
    print("=" * 70)
    print(f"Listening for {duration} seconds...\n")

    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        buffer = ""
        start_time = time.time()

        gga_found = False
        gsv_found = False

        while time.time() - start_time < duration:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode('ascii', errors='ignore')
                buffer += data

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()

                    # GGA - Position and fix data
                    if line.startswith('$GNGGA') or line.startswith('$GPGGA'):
                        parts = line.split(',')
                        if len(parts) > 9:
                            fix = parts[6]
                            sats = parts[7]
                            hdop = parts[8]
                            alt = parts[9]

                            fix_type = {
                                '0': 'No Fix',
                                '1': 'GPS Fix',
                                '2': 'DGPS Fix',
                                '4': 'RTK Fixed',
                                '5': 'RTK Float'
                            }.get(fix, f'Unknown ({fix})')

                            if not gga_found:
                                print(f"Position Fix Quality: {fix_type}")
                                print(f"Satellites in use: {sats}")
                                print(f"HDOP: {hdop}")
                                print(f"Altitude: {alt} m")
                                gga_found = True

                    # GSV - Satellites in view
                    if line.startswith('$GNGSV') or line.startswith('$GPGSV'):
                        if not gsv_found:
                            parts = line.split(',')
                            if len(parts) > 3:
                                total_sats = parts[3]
                                print(f"\nSatellites in view: {total_sats}")
                                gsv_found = True

            if gga_found and gsv_found:
                break

            time.sleep(0.1)

        ser.close()

        if not gga_found:
            print("⚠ No position data received")
            print("  GPS may still be acquiring satellites")

        print("\n" + "=" * 70)

    except Exception as e:
        print(f"Error reading satellite info: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Diagnostic tool for LC29H GPS module'
    )

    parser.add_argument(
        '-p', '--port',
        default='/dev/ttyS0',
        help='Serial port (default: /dev/ttyS0)'
    )

    parser.add_argument(
        '-b', '--baudrate',
        type=int,
        default=115200,
        help='Baudrate (default: 115200)'
    )

    parser.add_argument(
        '-d', '--duration',
        type=int,
        default=5,
        help='How long to listen in seconds (default: 5)'
    )

    parser.add_argument(
        '-s', '--satellites',
        action='store_true',
        help='Show satellite information'
    )

    args = parser.parse_args()

    # Run basic diagnostic
    result = test_serial_connection(args.port, args.baudrate, args.duration)

    # Show satellite info if requested
    if args.satellites and result:
        check_satellite_info(args.port, args.baudrate, 10)

    sys.exit(0 if result else 1)

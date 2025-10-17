#!/usr/bin/env python3
"""
Convert ECEF coordinates to Latitude, Longitude, Altitude (WGS84)
"""

import math
import sys

def ecef_to_lla(x, y, z):
    """
    Convert ECEF (Earth-Centered, Earth-Fixed) coordinates to
    Latitude, Longitude, Altitude in WGS84 datum

    Args:
        x, y, z: ECEF coordinates in meters

    Returns:
        tuple: (latitude_deg, longitude_deg, altitude_m)
    """
    # WGS84 ellipsoid constants
    a = 6378137.0  # Semi-major axis (equatorial radius) in meters
    f = 1 / 298.257223563  # Flattening
    e2 = 2 * f - f * f  # First eccentricity squared

    # Calculate longitude
    lon = math.atan2(y, x)

    # Calculate latitude and altitude iteratively
    p = math.sqrt(x * x + y * y)
    lat = math.atan2(z, p * (1 - e2))

    # Iterate to improve accuracy
    for _ in range(5):
        N = a / math.sqrt(1 - e2 * math.sin(lat) * math.sin(lat))
        alt = p / math.cos(lat) - N
        lat = math.atan2(z, p * (1 - e2 * N / (N + alt)))

    # Final altitude calculation
    N = a / math.sqrt(1 - e2 * math.sin(lat) * math.sin(lat))
    alt = p / math.cos(lat) - N

    # Convert to degrees
    lat_deg = math.degrees(lat)
    lon_deg = math.degrees(lon)

    return lat_deg, lon_deg, alt


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 ecef_to_lla.py <X> <Y> <Z>")
        print("Example: python3 ecef_to_lla.py -2072860.7317 -4139459.9752 4373707.3810")
        sys.exit(1)

    try:
        x = float(sys.argv[1])
        y = float(sys.argv[2])
        z = float(sys.argv[3])

        lat, lon, alt = ecef_to_lla(x, y, z)

        print("\n" + "=" * 60)
        print("ECEF to WGS84 Conversion")
        print("=" * 60)
        print(f"\nInput ECEF Coordinates:")
        print(f"  X: {x:15.4f} m")
        print(f"  Y: {y:15.4f} m")
        print(f"  Z: {z:15.4f} m")
        print(f"\nOutput WGS84 Coordinates:")
        print(f"  Latitude:  {lat:12.8f}°")
        print(f"  Longitude: {lon:12.8f}°")
        print(f"  Altitude:  {alt:12.4f} m (ellipsoidal height)")
        print("\n" + "=" * 60)
        print("Config file format:")
        print("=" * 60)
        print(f"base_station:")
        print(f"  latitude: {lat:.8f}")
        print(f"  longitude: {lon:.8f}")
        print(f"  altitude: {alt:.4f}")
        print("=" * 60 + "\n")

    except ValueError as e:
        print(f"Error: Invalid coordinate values - {e}")
        sys.exit(1)

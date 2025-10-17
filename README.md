# LC29H RTK Base Station - NTRIP Server

A Python-based NTRIP server that broadcasts RTK corrections from a Quectel LC29H GNSS module connected via GPIO serial port.

## Features

- Serial communication with LC29H GPS module via GPIO UART
- Configures LC29H as RTK base station with fixed position
- NTRIP caster server for broadcasting RTCM3 corrections
- Support for multi-constellation GNSS (GPS, GLONASS, Galileo, BeiDou)
- RTCM3 message parsing and validation
- **Web dashboard** for real-time status monitoring
- Optional authentication for NTRIP clients
- Comprehensive logging with rotation
- Status monitoring and statistics
- Automated systemd service installation

## Hardware Requirements

- Quectel LC29H GNSS RTK module
- Raspberry Pi or similar SBC with GPIO UART
- GPS antenna with clear sky view for base station

## Wiring

Connect LC29H to GPIO serial port:

```
LC29H          SBC (e.g., Raspberry Pi)
-----          ------------------------
VCC      -->   3.3V or 5V (check LC29H specs)
GND      -->   GND
TX       -->   RX (GPIO 15, /dev/ttyS0)
RX       -->   TX (GPIO 14, /dev/ttyS0)
```

## Quick Installation

The easiest way to install is using the automated install script:

```bash
# Copy the template configuration file
cp config.yaml.template config.yaml

# Edit config.yaml to set your base station coordinates
nano config.yaml

# Run the installer (will prompt for systemd setup)
sudo ./install.sh
```

The installer will:
- Install Python dependencies
- Configure serial port permissions
- Create systemd service
- Optionally enable and start the service

### Manual Installation

1. Clone or download this repository:

```bash
cd /home/benson/lc29h-rtk
```

2. Copy and configure the configuration file:

```bash
cp config.yaml.template config.yaml
nano config.yaml  # Edit your base station coordinates
```

3. Install Python dependencies:

```bash
pip3 install -r requirements.txt
```

4. Enable serial port on Raspberry Pi (if needed):

Edit `/boot/config.txt` and add:
```
enable_uart=1
```

Disable serial console in `/boot/cmdline.txt` by removing `console=serial0,115200`

Reboot:
```bash
sudo reboot
```

5. Check serial port access:

```bash
python3 base_station.py --check-serial
```

If permission denied, add your user to dialout group:
```bash
sudo usermod -a -G dialout $USER
# Log out and back in for changes to take effect
```

## Configuration

**Important**: The repository includes `config.yaml.template` as a reference. Copy it to `config.yaml` and edit with your settings:

```bash
cp config.yaml.template config.yaml
nano config.yaml
```

The `config.yaml` file is gitignored to protect your station coordinates and credentials.

### Important Settings

1. **Serial Port**: Set the correct GPIO serial port
   - Raspberry Pi: `/dev/ttyS0`, `/dev/ttyAMA0`, or `/dev/serial0`
   - Check available ports: `ls /dev/tty*`

2. **Base Station Position**: Set accurate fixed coordinates
   ```yaml
   base_station:
     latitude: 37.7749      # Your base station latitude (WGS84)
     longitude: -122.4194   # Your base station longitude (WGS84)
     altitude: 10.0         # Ellipsoidal height in meters
   ```

   To get accurate coordinates:
   - Use a professional surveying service
   - Run GPS in static mode for 24+ hours and post-process
   - Use online PPP (Precise Point Positioning) services

3. **NTRIP Server Settings**:
   ```yaml
   ntrip:
     host: 0.0.0.0         # Listen on all interfaces
     port: 2101            # Standard NTRIP port
     mountpoint:
       name: BASE          # Your mountpoint name
   ```

4. **Web Dashboard** (optional):
   ```yaml
   web:
     enabled: true         # Enable/disable web interface
     host: 0.0.0.0         # Bind to all interfaces
     port: 5000            # Web dashboard port
   ```

5. **Authentication** (optional):
   ```yaml
   ntrip:
     authentication:
       enabled: true
       username: youruser
       password: yourpass
   ```

## Running the Server

### Manual Start

Start the base station:

```bash
python3 base_station.py
```

Run with custom config:

```bash
python3 base_station.py -c custom_config.yaml
```

Disable web interface:

```bash
python3 base_station.py --no-web
```

Run as background service:

```bash
nohup python3 base_station.py > output.log 2>&1 &
```

### Systemd Service

If you used the install script, manage with systemd:

```bash
# Start service
sudo systemctl start lc29h-rtk-base

# Stop service
sudo systemctl stop lc29h-rtk-base

# Restart service
sudo systemctl restart lc29h-rtk-base

# View status
sudo systemctl status lc29h-rtk-base

# View logs
sudo journalctl -u lc29h-rtk-base -f

# Enable at boot
sudo systemctl enable lc29h-rtk-base

# Disable at boot
sudo systemctl disable lc29h-rtk-base
```

## Web Dashboard

Access the real-time monitoring dashboard at:

```
http://YOUR_IP:5000
```

The dashboard displays:
- Server status and uptime
- RTCM message statistics
- Active NTRIP clients
- Base station position
- Message rates and throughput
- Configuration details

Auto-refreshes every 2 seconds.

## Connecting NTRIP Clients

Clients can connect using:

- **URL**: `ntrip://YOUR_IP:2101/BASE`
- **Host**: Your server IP address
- **Port**: 2101
- **Mountpoint**: BASE (or your configured mountpoint name)
- **Username/Password**: If authentication is enabled

### Example NTRIP Client URLs

For use in RTK rovers, survey apps, or GIS software:

```
ntrip://192.168.1.100:2101/BASE
```

With authentication:
```
ntrip://user:pass@192.168.1.100:2101/BASE
```


## Logs

Logs are written to `logs/base_station.log` with automatic rotation.

View logs:
```bash
tail -f logs/base_station.log
```

## RTCM Messages

Default RTCM3 messages broadcast:

- **1005**: Stationary RTK reference station ARP (10 sec)
- **1074**: GPS MSM4 observations (1 sec)
- **1084**: GLONASS MSM4 observations (1 sec)
- **1094**: Galileo MSM4 observations (1 sec)
- **1124**: BeiDou MSM4 observations (1 sec)
- **1230**: GLONASS code-phase biases (10 sec)

These provide multi-constellation RTK corrections for cm-level positioning.

## Troubleshooting

### Serial Port Issues

Check if port exists:
```bash
ls -l /dev/ttyS0
```

Test serial communication:
```bash
sudo cat /dev/ttyS0
# Should see GPS data streaming (NMEA sentences or binary data)
```

### No RTCM Data

1. Check LC29H is in base mode
2. Verify antenna has clear sky view
3. Check serial baudrate matches LC29H config (default: 115200)
4. Review logs for errors

### NTRIP Connection Issues

1. Check firewall allows ports 2101 (NTRIP) and 5000 (web):
   ```bash
   sudo ufw allow 2101
   sudo ufw allow 5000
   ```

2. Test NTRIP server locally:
   ```bash
   curl http://localhost:2101/
   # Should return sourcetable
   ```

3. Check from remote client:
   ```bash
   curl http://YOUR_IP:2101/
   ```

### Web Dashboard Not Loading

1. Check if web interface is enabled in `config.yaml`
2. Verify port 5000 is not in use: `sudo netstat -tlnp | grep 5000`
3. Check logs for Flask errors: `tail -f logs/base_station.log`
4. Try accessing locally first: `curl http://localhost:5000`

## Performance

Expected performance:
- RTCM message rate: ~1-10 Hz depending on message types
- Data rate: ~5-10 kbps per client
- Supports 10+ simultaneous NTRIP clients
- Base accuracy: 1-2 cm horizontal (with accurate fixed position)

## License

This software is provided as-is for RTK base station applications.

## References

- [Quectel LC29H Product Page](https://www.quectel.com/product/lc29h)
- [RTCM 10403.3 Standard](https://www.rtcm.org/)
- [NTRIP Protocol](https://igs.bkg.bund.de/ntrip/about)

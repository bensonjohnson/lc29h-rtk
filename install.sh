#!/bin/bash
#
# LC29H RTK Base Station Installation Script
# This script installs the base station as a systemd service
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory (where the base station code is)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_NAME="lc29h-rtk-base"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo -e "${GREEN}LC29H RTK Base Station Installation${NC}"
echo "======================================"
echo ""

# Check if running as root for systemd installation
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    echo "Usage: sudo ./install.sh"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

echo "Installation directory: $SCRIPT_DIR"
echo "Running as user: $ACTUAL_USER"
echo ""

# Step 1: Check Python version
echo -e "${YELLOW}[1/7]${NC} Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "  Found Python $PYTHON_VERSION"

# Step 2: Install Python dependencies
echo -e "${YELLOW}[2/7]${NC} Installing Python dependencies..."
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    sudo -u $ACTUAL_USER python3 -m pip install --user --break-system-packages -r "$SCRIPT_DIR/requirements.txt" || {
        echo -e "${YELLOW}Warning: pip install failed, trying with sudo...${NC}"
        pip3 install --break-system-packages -r "$SCRIPT_DIR/requirements.txt"
    }
    echo "  Dependencies installed"
else
    echo -e "${RED}Error: requirements.txt not found${NC}"
    exit 1
fi

# Step 3: Check configuration file
echo -e "${YELLOW}[3/7]${NC} Checking configuration..."
if [ ! -f "$SCRIPT_DIR/config.yaml" ]; then
    echo -e "${RED}Error: config.yaml not found${NC}"
    echo "Please create a config.yaml file before installing"
    exit 1
fi
echo "  Configuration file found"

# Step 4: Setup serial port permissions
echo -e "${YELLOW}[4/7]${NC} Setting up serial port permissions..."

# Install udev rules for serial ports
if [ -f "$SCRIPT_DIR/99-serial-permissions.rules" ]; then
    cp "$SCRIPT_DIR/99-serial-permissions.rules" /etc/udev/rules.d/
    udevadm control --reload-rules
    udevadm trigger
    echo "  udev rules installed"
fi

# Add user to dialout and tty groups
if ! groups $ACTUAL_USER | grep -q dialout; then
    echo "  Adding $ACTUAL_USER to dialout group..."
    usermod -a -G dialout $ACTUAL_USER
    echo -e "${YELLOW}  Note: Group changes take effect after service starts${NC}"
else
    echo "  User $ACTUAL_USER already in dialout group"
fi

if ! groups $ACTUAL_USER | grep -q tty; then
    echo "  Adding $ACTUAL_USER to tty group..."
    usermod -a -G tty $ACTUAL_USER
else
    echo "  User $ACTUAL_USER already in tty group"
fi

# Check and set permissions on serial port
SERIAL_PORT=$(grep -A1 "^serial:" "$SCRIPT_DIR/config.yaml" | grep "port:" | cut -d':' -f2 | tr -d ' ')
if [ -e "$SERIAL_PORT" ]; then
    echo "  Serial port $SERIAL_PORT exists"
    chgrp dialout "$SERIAL_PORT" 2>/dev/null || true
    chmod 660 "$SERIAL_PORT" 2>/dev/null || true
    echo "  Permissions set on $SERIAL_PORT"
    ls -l "$SERIAL_PORT"
else
    echo -e "${YELLOW}Warning: Serial port $SERIAL_PORT not found${NC}"
    echo "  Available serial ports:"
    ls -l /dev/tty{S,AMA,USB}* 2>/dev/null || echo "    None found"
fi

# Step 5: Create logs directory
echo -e "${YELLOW}[5/7]${NC} Creating logs directory..."
mkdir -p "$SCRIPT_DIR/logs"
chown $ACTUAL_USER:$ACTUAL_USER "$SCRIPT_DIR/logs"
echo "  Logs directory created"

# Step 6: Create systemd service file
echo -e "${YELLOW}[6/7]${NC} Creating systemd service..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=LC29H RTK Base Station NTRIP Server
Documentation=https://github.com/your-repo/lc29h-rtk
After=network.target

[Service]
Type=simple
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/base_station.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

# Environment
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

echo "  Service file created: $SERVICE_FILE"

# Step 7: Enable and start service
echo -e "${YELLOW}[7/7]${NC} Configuring systemd service..."
systemctl daemon-reload
echo "  Systemd daemon reloaded"

# Ask user if they want to enable and start now
echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "Service management commands:"
echo "  Start service:    sudo systemctl start $SERVICE_NAME"
echo "  Stop service:     sudo systemctl stop $SERVICE_NAME"
echo "  Restart service:  sudo systemctl restart $SERVICE_NAME"
echo "  View status:      sudo systemctl status $SERVICE_NAME"
echo "  View logs:        sudo journalctl -u $SERVICE_NAME -f"
echo "  Enable at boot:   sudo systemctl enable $SERVICE_NAME"
echo "  Disable at boot:  sudo systemctl disable $SERVICE_NAME"
echo ""

read -p "Do you want to enable the service to start at boot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl enable $SERVICE_NAME
    echo -e "${GREEN}Service enabled at boot${NC}"
fi

echo ""
read -p "Do you want to start the service now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl start $SERVICE_NAME
    echo -e "${GREEN}Service started${NC}"
    echo ""
    echo "Checking service status..."
    sleep 2
    systemctl status $SERVICE_NAME --no-pager || true
    echo ""
    echo "View live logs with: sudo journalctl -u $SERVICE_NAME -f"
fi

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "Configuration file: $SCRIPT_DIR/config.yaml"
echo "Edit the config file and restart the service to apply changes."
echo ""

# Check if web interface is enabled
if grep -q "enabled: true" "$SCRIPT_DIR/config.yaml"; then
    WEB_PORT=$(grep -A3 "^web:" "$SCRIPT_DIR/config.yaml" | grep "port:" | cut -d':' -f2 | tr -d ' ')
    echo -e "${GREEN}Web interface will be available at: http://$(hostname -I | awk '{print $1}'):${WEB_PORT:-5000}${NC}"
fi

exit 0

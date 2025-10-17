#!/bin/bash
#
# Fix Serial Port Permissions
# Run this script with sudo to fix serial port access issues
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${GREEN}Fixing Serial Port Permissions${NC}"
echo "================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    echo "Usage: sudo ./fix-serial-permissions.sh"
    exit 1
fi

# Get actual user
ACTUAL_USER="${SUDO_USER:-$USER}"

echo "Step 1: Installing udev rules..."
cp "$SCRIPT_DIR/99-serial-permissions.rules" /etc/udev/rules.d/
echo "  udev rules installed"

echo "Step 2: Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger
echo "  udev rules reloaded"

echo "Step 3: Checking user groups..."
if ! groups $ACTUAL_USER | grep -q dialout; then
    echo "  Adding $ACTUAL_USER to dialout group..."
    usermod -a -G dialout $ACTUAL_USER
    echo -e "${YELLOW}  Note: User needs to log out and back in for group changes${NC}"
else
    echo "  User already in dialout group"
fi

if ! groups $ACTUAL_USER | grep -q tty; then
    echo "  Adding $ACTUAL_USER to tty group..."
    usermod -a -G tty $ACTUAL_USER
    echo -e "${YELLOW}  Note: User needs to log out and back in for group changes${NC}"
else
    echo "  User already in tty group"
fi

echo "Step 4: Setting immediate permissions on /dev/ttyS0..."
if [ -e /dev/ttyS0 ]; then
    chgrp dialout /dev/ttyS0
    chmod 660 /dev/ttyS0
    echo "  Permissions set on /dev/ttyS0"
    ls -l /dev/ttyS0
else
    echo -e "${YELLOW}  Warning: /dev/ttyS0 not found${NC}"
fi

echo ""
echo -e "${GREEN}Serial port permissions fixed!${NC}"
echo ""
echo "If the service is running, restart it:"
echo "  sudo systemctl restart lc29h-rtk-base"
echo ""

exit 0

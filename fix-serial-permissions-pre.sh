#!/bin/bash
# Fix serial port permissions before starting service
# This runs as root via systemd ExecStartPre

# Set permissions on ttyS0
if [ -e /dev/ttyS0 ]; then
    chgrp dialout /dev/ttyS0
    chmod 660 /dev/ttyS0
fi

exit 0

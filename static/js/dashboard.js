// Dashboard JavaScript for RTK Base Station Status
let config = null;
let map = null;
let marker = null;

// RTCM message type descriptions
const RTCM_DESCRIPTIONS = {
    1005: "Station Coordinates",
    1006: "Station Coordinates + Height",
    1074: "GPS MSM4",
    1075: "GPS MSM5",
    1084: "GLONASS MSM4",
    1085: "GLONASS MSM5",
    1094: "Galileo MSM4",
    1095: "Galileo MSM5",
    1124: "BeiDou MSM4",
    1125: "BeiDou MSM5",
    1230: "GLONASS Biases"
};

// Format bytes to human readable
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

// Format number with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Format date/time
function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString();
}

// Update status indicator
function updateStatusIndicator(status) {
    const indicator = document.getElementById('statusIndicator');
    const dot = indicator.querySelector('.status-dot');
    const text = indicator.querySelector('.status-text');

    dot.className = 'status-dot ' + status;
    text.textContent = status.charAt(0).toUpperCase() + status.slice(1);
}

// Update statistics
function updateStats(stats) {
    // Server status
    document.getElementById('serverStatus').textContent = stats.status.toUpperCase();
    document.getElementById('uptime').textContent = stats.uptime_formatted || '-';
    document.getElementById('startTime').textContent = formatDateTime(stats.start_time);

    // GPS status
    if (stats.gps_status) {
        const gps = stats.gps_status;
        document.getElementById('fixType').textContent = gps.fix_type || 'Unknown';
        document.getElementById('satellites').textContent = gps.satellites || '0';
        document.getElementById('hdop').textContent = gps.hdop ? gps.hdop.toFixed(2) : '-';

        // Signal status with indicator
        const signalElement = document.getElementById('signalStatus');
        if (gps.stale) {
            signalElement.textContent = '⚠ Stale';
            signalElement.style.color = '#f59e0b';
        } else {
            signalElement.textContent = '✓ Active';
            signalElement.style.color = '#10b981';
        }

        // Position accuracy
        if (gps.position_accuracy) {
            const acc = gps.position_accuracy;
            document.getElementById('horizontalError').textContent = acc.horizontal_m.toFixed(3) + ' m';
            document.getElementById('verticalError').textContent = acc.vertical_m.toFixed(3) + ' m';
            document.getElementById('error3d').textContent = acc.error_3d_m.toFixed(3) + ' m';

            // Accuracy status with color coding
            const accuracyElement = document.getElementById('accuracyStatus');
            const error3d = acc.error_3d_m;
            if (error3d < 0.1) {
                accuracyElement.textContent = '✓ Excellent';
                accuracyElement.style.color = '#10b981';
            } else if (error3d < 0.5) {
                accuracyElement.textContent = '✓ Good';
                accuracyElement.style.color = '#10b981';
            } else if (error3d < 2.0) {
                accuracyElement.textContent = '⚠ Moderate';
                accuracyElement.style.color = '#f59e0b';
            } else {
                accuracyElement.textContent = '⚠ Poor';
                accuracyElement.style.color = '#ef4444';
            }
        } else {
            document.getElementById('horizontalError').textContent = '-';
            document.getElementById('verticalError').textContent = '-';
            document.getElementById('error3d').textContent = '-';
            document.getElementById('accuracyStatus').textContent = 'Calculating...';
            document.getElementById('accuracyStatus').style.color = '#6b7280';
        }
    }

    // RTCM statistics
    document.getElementById('rtcmMessages').textContent = formatNumber(stats.rtcm_messages);
    document.getElementById('bytesSent').textContent = formatBytes(stats.bytes_broadcast);
    document.getElementById('messageRate').textContent = stats.message_rate.toFixed(2) + ' msg/s';
    document.getElementById('byteRate').textContent = formatBytes(stats.byte_rate) + '/s';

    // Client info
    document.getElementById('clientCount').textContent = stats.active_clients;

    // Update client list
    const clientList = document.getElementById('clientList');
    if (stats.active_clients === 0) {
        clientList.innerHTML = '<p class="no-clients">No clients connected</p>';
    } else {
        let html = '';
        stats.clients.forEach(client => {
            const connectedTime = formatDateTime(client.connected_at);
            const duration = calculateDuration(client.connected_at);
            html += `
                <div class="client-item">
                    <div class="client-address">${client.address}</div>
                    <div class="client-details">
                        <span><label>Mountpoint:</label> ${client.mountpoint}</span>
                        <span><label>Connected:</label> ${duration}</span>
                        <span><label>Sent:</label> ${formatBytes(client.bytes_sent)}</span>
                    </div>
                </div>
            `;
        });
        clientList.innerHTML = html;
    }

    // Update status indicator
    updateStatusIndicator(stats.status);

    // Update last update time
    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
}

// Calculate connection duration
function calculateDuration(connectedAt) {
    const start = new Date(connectedAt);
    const now = new Date();
    const diff = Math.floor((now - start) / 1000); // seconds

    const hours = Math.floor(diff / 3600);
    const minutes = Math.floor((diff % 3600) / 60);
    const seconds = diff % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m ${seconds}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
    } else {
        return `${seconds}s`;
    }
}

// Initialize map
function initMap(lat, lon) {
    // Create map centered on base station
    map = L.map('map').setView([lat, lon], 16);

    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);

    // Create custom icon for base station
    const baseIcon = L.divIcon({
        className: 'base-station-marker',
        html: '<div style="background: #667eea; width: 24px; height: 24px; border-radius: 50%; border: 3px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.3);"></div>',
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });

    // Add marker for base station
    marker = L.marker([lat, lon], { icon: baseIcon }).addTo(map);

    // Add popup with coordinates
    marker.bindPopup(`
        <strong>RTK Base Station</strong><br>
        Lat: ${lat.toFixed(8)}°<br>
        Lon: ${lon.toFixed(8)}°
    `).openPopup();

    // Add circle showing approximate coverage area (10km radius)
    L.circle([lat, lon], {
        color: '#667eea',
        fillColor: '#667eea',
        fillOpacity: 0.1,
        radius: 10000
    }).addTo(map);
}

// Update configuration display
function updateConfig(cfg) {
    config = cfg;

    // Base station position
    document.getElementById('latitude').textContent = cfg.base_station.latitude.toFixed(8) + '°';
    document.getElementById('longitude').textContent = cfg.base_station.longitude.toFixed(8) + '°';
    document.getElementById('altitude').textContent = cfg.base_station.altitude.toFixed(2) + ' m';

    // Initialize map with base station location
    if (!map) {
        initMap(cfg.base_station.latitude, cfg.base_station.longitude);
    }

    // NTRIP configuration
    document.getElementById('ntripPort').textContent = cfg.ntrip.port;
    document.getElementById('mountpoint').textContent = cfg.ntrip.mountpoint;
    document.getElementById('authEnabled').textContent = cfg.ntrip.authentication_enabled ? 'Yes' : 'No';

    // Build connection URL
    const hostname = window.location.hostname || 'localhost';
    const url = `ntrip://${hostname}:${cfg.ntrip.port}/${cfg.ntrip.mountpoint}`;
    document.getElementById('connectionUrl').textContent = url;

    // RTCM message types
    const rtcmTypesDiv = document.getElementById('rtcmTypes');
    let html = '';
    cfg.rtcm.messages.forEach(msgType => {
        const desc = RTCM_DESCRIPTIONS[msgType] || 'Unknown';
        html += `<div class="rtcm-badge">${msgType} - ${desc}</div>`;
    });
    rtcmTypesDiv.innerHTML = html;
}

// Fetch and update status
async function fetchStatus() {
    try {
        const response = await fetch('/api/status');
        if (!response.ok) throw new Error('Failed to fetch status');
        const stats = await response.json();
        updateStats(stats);
    } catch (error) {
        console.error('Error fetching status:', error);
        updateStatusIndicator('error');
    }
}

// Fetch configuration (once on load)
async function fetchConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) throw new Error('Failed to fetch config');
        const cfg = await response.json();
        updateConfig(cfg);
    } catch (error) {
        console.error('Error fetching config:', error);
    }
}

// Initialize dashboard
async function init() {
    await fetchConfig();
    await fetchStatus();

    // Auto-refresh every 2 seconds
    setInterval(fetchStatus, 2000);
}

// Start when page loads
document.addEventListener('DOMContentLoaded', init);

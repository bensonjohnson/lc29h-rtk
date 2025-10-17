// Dashboard JavaScript for RTK Base Station Status
let config = null;

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

// Update configuration display
function updateConfig(cfg) {
    config = cfg;

    // Base station position
    document.getElementById('latitude').textContent = cfg.base_station.latitude.toFixed(8) + '°';
    document.getElementById('longitude').textContent = cfg.base_station.longitude.toFixed(8) + '°';
    document.getElementById('altitude').textContent = cfg.base_station.altitude.toFixed(2) + ' m';

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

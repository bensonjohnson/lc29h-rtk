#!/usr/bin/env python3
"""
Flask Web Interface for RTK Base Station Status
Provides real-time monitoring dashboard
"""

from flask import Flask, render_template, jsonify
import logging
import time
from datetime import datetime, timedelta
from threading import Thread

logger = logging.getLogger(__name__)


class WebInterface:
    """Flask web interface for base station monitoring"""

    def __init__(self, base_station, host='0.0.0.0', port=5000):
        """
        Initialize web interface

        Args:
            base_station: RTKBaseStation instance
            host: Interface to bind to
            port: Port number
        """
        self.base_station = base_station
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.app.logger.setLevel(logging.WARNING)  # Reduce Flask logging

        # Disable Flask startup messages
        import logging as flask_logging
        log = flask_logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        self._setup_routes()
        self.server_thread = None

    def _setup_routes(self):
        """Setup Flask routes"""

        @self.app.route('/')
        def index():
            """Render main dashboard"""
            return render_template('index.html')

        @self.app.route('/api/status')
        def api_status():
            """Get current server status"""
            try:
                stats = self._get_stats()
                return jsonify(stats)
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/config')
        def api_config():
            """Get current configuration"""
            try:
                config = self._get_config_info()
                return jsonify(config)
            except Exception as e:
                logger.error(f"Error getting config: {e}")
                return jsonify({'error': str(e)}), 500

    def _get_stats(self):
        """Get current statistics"""
        uptime = 0
        if self.base_station.stats['start_time']:
            uptime = time.time() - self.base_station.stats['start_time']

        # Get NTRIP server stats
        ntrip_stats = {'active_clients': 0, 'clients': []}
        if self.base_station.ntrip:
            ntrip_stats = self.base_station.ntrip.get_stats()

        # Calculate rates
        msg_rate = 0
        byte_rate = 0
        if uptime > 0:
            msg_rate = self.base_station.stats['rtcm_messages'] / uptime
            byte_rate = self.base_station.stats['bytes_broadcast'] / uptime

        # Get GPS status
        gps_status = {'satellites': 0, 'fix_type': 'Unknown', 'hdop': 0.0, 'stale': True}
        if self.base_station.gps:
            gps_status = self.base_station.gps.get_gps_status()

        return {
            'status': 'running' if self.base_station.running else 'stopped',
            'uptime': uptime,
            'uptime_formatted': str(timedelta(seconds=int(uptime))),
            'start_time': datetime.fromtimestamp(self.base_station.stats['start_time']).isoformat() if self.base_station.stats['start_time'] else None,
            'rtcm_messages': self.base_station.stats['rtcm_messages'],
            'bytes_broadcast': self.base_station.stats['bytes_broadcast'],
            'message_rate': round(msg_rate, 2),
            'byte_rate': round(byte_rate, 2),
            'active_clients': ntrip_stats['active_clients'],
            'clients': ntrip_stats['clients'],
            'gps_status': gps_status,
            'timestamp': datetime.now().isoformat()
        }

    def _get_config_info(self):
        """Get configuration information"""
        config = self.base_station.config

        return {
            'serial': {
                'port': config['serial']['port'],
                'baudrate': config['serial']['baudrate']
            },
            'base_station': {
                'latitude': config['base_station']['latitude'],
                'longitude': config['base_station']['longitude'],
                'altitude': config['base_station']['altitude']
            },
            'ntrip': {
                'host': config['ntrip']['host'],
                'port': config['ntrip']['port'],
                'mountpoint': config['ntrip']['mountpoint']['name'],
                'identifier': config['ntrip']['mountpoint']['identifier'],
                'authentication_enabled': config['ntrip'].get('authentication', {}).get('enabled', False)
            },
            'rtcm': {
                'messages': config['rtcm']['messages']
            },
            'station': config.get('station', {})
        }

    def start(self):
        """Start web interface in background thread"""
        self.server_thread = Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        logger.info(f"Web interface started on http://{self.host}:{self.port}")

    def _run_server(self):
        """Run Flask server"""
        self.app.run(
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False,
            threaded=True
        )

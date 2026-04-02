#!/usr/bin/env python3
"""
Simple HTTP server for Sapphire AI Dashboard
"""

import http.server
import json
import socketserver
import subprocess
from urllib.parse import urlparse

PORT = 8088

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
        
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/':
            self.serve_dashboard()
        elif parsed.path == '/api/status':
            self.serve_api_status()
        else:
            super().do_GET()
            
    def serve_dashboard(self):
        try:
            with open('trading_intelligence_dashboard.html', 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "Dashboard not found")
            
    def serve_api_status(self):
        # Collect status from all services
        status = {
            "timestamp": subprocess.check_output(['date', '+%Y-%m-%d %H:%M:%S']).decode().strip(),
            "services": {
                "ai_orchestrator": {"port": 8087, "status": "unknown"},
                "mac_bridge": {"port": 8083, "status": "unknown"},
                "windows_webhook": {"port": 9090, "host": "100.71.10.48", "status": "unknown"},
            }
        }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status, indent=2).encode())

if __name__ == "__main__":
    import os
    os.chdir('/Users/aribs')
    
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"🌐 Sapphire Dashboard serving at http://localhost:{PORT}")
        print("Press Ctrl+C to stop")
        httpd.serve_forever()

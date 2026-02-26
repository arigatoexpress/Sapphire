"""
Sapphire OS - Log Viewer Dashboard

Simple web interface for viewing structured logs from Firestore.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from google.cloud import firestore

# Log viewer dashboard - queries Firestore for system logs

app = FastAPI(title="Sapphire Log Viewer")
db = firestore.Client(project="sapphire-479610")

LOGS_COLLECTION = "system_logs"

def get_logs(service: Optional[str] = None, 
             level: Optional[str] = None,
             event_type: Optional[str] = None,
             hours: int = 24,
             limit: int = 100) -> List[Dict]:
    """Query logs from Firestore"""
    
    # Build query
    query = db.collection(LOGS_COLLECTION)
    
    # Time filter
    since = datetime.utcnow() - timedelta(hours=hours)
    query = query.where("timestamp", ">=", since.isoformat())
    
    # Service filter
    if service:
        query = query.where("service", "==", service)
    
    # Level filter
    if level:
        query = query.where("level", "==", level.upper())
    
    # Event type filter
    if event_type:
        query = query.where("event_type", "==", event_type)
    
    # Order by timestamp desc
    query = query.order_by("timestamp", direction=firestore.Query.DESCENDING)
    query = query.limit(limit)
    
    # Execute
    docs = query.stream()
    logs = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        logs.append(data)
    
    return logs

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Main dashboard HTML"""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Sapphire OS - Log Viewer</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
        }
        h1 { color: #3b82f6; margin-bottom: 20px; }
        .filters {
            background: #1e293b;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }
        .filters select, .filters input {
            background: #334155;
            color: #e2e8f0;
            border: 1px solid #475569;
            padding: 8px 12px;
            border-radius: 4px;
        }
        .filters button {
            background: #3b82f6;
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 4px;
            cursor: pointer;
        }
        .filters button:hover { background: #2563eb; }
        .log-entry {
            background: #1e293b;
            border-left: 4px solid #64748b;
            padding: 12px;
            margin-bottom: 8px;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
        }
        .log-entry.DEBUG { border-left-color: #64748b; }
        .log-entry.INFO { border-left-color: #3b82f6; }
        .log-entry.WARNING { border-left-color: #f59e0b; }
        .log-entry.ERROR { border-left-color: #ef4444; }
        .log-entry.CRITICAL { border-left-color: #dc2626; background: #450a0a; }
        .log-header {
            display: flex;
            gap: 15px;
            margin-bottom: 5px;
            opacity: 0.8;
        }
        .log-time { color: #94a3b8; }
        .log-service { color: #60a5fa; font-weight: bold; }
        .log-level { 
            padding: 2px 6px; 
            border-radius: 3px; 
            font-size: 11px;
            font-weight: bold;
        }
        .log-level.DEBUG { background: #475569; }
        .log-level.INFO { background: #1e40af; }
        .log-level.WARNING { background: #92400e; }
        .log-level.ERROR { background: #991b1b; }
        .log-level.CRITICAL { background: #7f1d1d; }
        .log-message { color: #f1f5f9; margin: 5px 0; }
        .log-meta {
            color: #94a3b8;
            font-size: 11px;
            margin-top: 5px;
        }
        .stats {
            background: #1e293b;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }
        .stat-box {
            text-align: center;
        }
        .stat-value {
            font-size: 28px;
            font-weight: bold;
            color: #3b82f6;
        }
        .stat-label {
            color: #94a3b8;
            font-size: 12px;
            text-transform: uppercase;
        }
        #loading { text-align: center; padding: 40px; color: #64748b; }
    </style>
</head>
<body>
    <h1>🔷 Sapphire OS - Log Viewer</h1>
    
    <div class="stats">
        <div class="stat-box">
            <div class="stat-value" id="total-logs">-</div>
            <div class="stat-label">Total Logs</div>
        </div>
        <div class="stat-box">
            <div class="stat-value" id="error-count">-</div>
            <div class="stat-label">Errors</div>
        </div>
        <div class="stat-box">
            <div class="stat-value" id="signal-count">-</div>
            <div class="stat-label">Signals</div>
        </div>
        <div class="stat-box">
            <div class="stat-value" id="last-hour">-</div>
            <div class="stat-label">Last Hour</div>
        </div>
    </div>
    
    <div class="filters">
        <select id="service-filter">
            <option value="">All Services</option>
            <option value="webhook">Webhook</option>
            <option value="trading">Trading</option>
            <option value="self_improvement">Self-Improvement</option>
        </select>
        
        <select id="level-filter">
            <option value="">All Levels</option>
            <option value="DEBUG">Debug</option>
            <option value="INFO">Info</option>
            <option value="WARNING">Warning</option>
            <option value="ERROR">Error</option>
            <option value="CRITICAL">Critical</option>
        </select>
        
        <select id="hours-filter">
            <option value="1">Last Hour</option>
            <option value="6">Last 6 Hours</option>
            <option value="24" selected>Last 24 Hours</option>
            <option value="168">Last Week</option>
        </select>
        
        <input type="text" id="search-filter" placeholder="Search message...">
        
        <button onclick="loadLogs()">Refresh</button>
    </div>
    
    <div id="logs-container">
        <div id="loading">Loading logs...</div>
    </div>
    
    <script>
        async function loadLogs() {
            const container = document.getElementById('logs-container');
            container.innerHTML = '<div id="loading">Loading logs...</div>';
            
            const service = document.getElementById('service-filter').value;
            const level = document.getElementById('level-filter').value;
            const hours = document.getElementById('hours-filter').value;
            
            const params = new URLSearchParams();
            if (service) params.append('service', service);
            if (level) params.append('level', level);
            params.append('hours', hours);
            params.append('limit', '100');
            
            try {
                const response = await fetch('/api/logs?' + params.toString());
                const data = await response.json();
                
                updateStats(data.logs);
                renderLogs(data.logs);
            } catch (err) {
                container.innerHTML = `<div style="color: #ef4444; padding: 20px;">Error loading logs: ${err.message}</div>`;
            }
        }
        
        function updateStats(logs) {
            document.getElementById('total-logs').textContent = logs.length;
            document.getElementById('error-count').textContent = logs.filter(l => 
                l.level === 'ERROR' || l.level === 'CRITICAL'
            ).length;
            document.getElementById('signal-count').textContent = logs.filter(l => 
                l.event_type && l.event_type.includes('signal')
            ).length;
            
            const oneHourAgo = new Date(Date.now() - 3600000).toISOString();
            document.getElementById('last-hour').textContent = logs.filter(l => 
                l.timestamp > oneHourAgo
            ).length;
        }
        
        function renderLogs(logs) {
            const container = document.getElementById('logs-container');
            const search = document.getElementById('search-filter').value.toLowerCase();
            
            if (logs.length === 0) {
                container.innerHTML = '<div style="padding: 40px; text-align: center; color: #64748b;">No logs found</div>';
                return;
            }
            
            const filtered = search 
                ? logs.filter(l => JSON.stringify(l).toLowerCase().includes(search))
                : logs;
            
            container.innerHTML = filtered.map(log => `
                <div class="log-entry ${log.level}">
                    <div class="log-header">
                        <span class="log-time">${new Date(log.timestamp).toLocaleString()}</span>
                        <span class="log-service">${log.service}</span>
                        <span class="log-level ${log.level}">${log.level}</span>
                        ${log.event_type ? `<span style="color: #a855f7;">${log.event_type}</span>` : ''}
                    </div>
                    <div class="log-message">${escapeHtml(log.message)}</div>
                    ${renderMeta(log)}
                </div>
            `).join('');
        }
        
        function renderMeta(log) {
            const meta = Object.entries(log)
                .filter(([k]) => !['id', 'timestamp', 'service', 'level', 'message', 'severity'].includes(k))
                .map(([k, v]) => `${k}: ${JSON.stringify(v).substring(0, 100)}`)
                .join(' | ');
            return meta ? `<div class="log-meta">${meta}</div>` : '';
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Auto-refresh every 30 seconds
        setInterval(loadLogs, 30000);
        
        // Initial load
        loadLogs();
    </script>
</body>
</html>
"""

@app.get("/api/logs")
async def api_logs(
    service: Optional[str] = None,
    level: Optional[str] = None,
    event_type: Optional[str] = None,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000)
):
    """API endpoint for fetching logs"""
    logs = get_logs(service, level, event_type, hours, limit)
    return {"logs": logs, "count": len(logs)}

@app.get("/api/stats")
async def api_stats():
    """Get log statistics"""
    # Get last 24h
    since = datetime.utcnow() - timedelta(hours=24)
    
    logs_ref = db.collection(LOGS_COLLECTION)
    query = logs_ref.where("timestamp", ">=", since.isoformat())
    docs = list(query.stream())
    
    total = len(docs)
    errors = sum(1 for d in docs if d.to_dict().get("level") in ["ERROR", "CRITICAL"])
    signals = sum(1 for d in docs if "signal" in str(d.to_dict().get("event_type", "")))
    
    # By service
    services = {}
    for d in docs:
        svc = d.to_dict().get("service", "unknown")
        services[svc] = services.get(svc, 0) + 1
    
    return {
        "total": total,
        "errors": errors,
        "signals": signals,
        "by_service": services
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)

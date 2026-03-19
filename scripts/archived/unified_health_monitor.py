#!/usr/bin/env python3
"""
Sapphire Unified Health Monitor
Checks status of all system components:
- Pi cluster (rari1, rari2)
- Windows webhook
- Cloud Run services
- Firestore connectivity
- Trading metrics
"""

import json
import os
import sys
import subprocess
import asyncio
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from firebase_admin import credentials, firestore, initialize_app

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '6826484357')
GCP_PROJECT = os.getenv('GCP_PROJECT', 'sapphire-479610')

# Service endpoints
RARI1_IP = os.getenv("RARI1_IP", "100.120.191.1")
RARI2_IP = os.getenv("RARI2_IP", "100.87.225.89")
WINDOWS_IP = os.getenv("WINDOWS_IP", "100.71.10.48")
WINDOWS_WEBHOOK_PORT = int(os.getenv("WINDOWS_WEBHOOK_PORT", "9090"))
WINDOWS_TV_AGENT_PORT = int(os.getenv("WINDOWS_TV_AGENT_PORT", "8081"))
OPTIONAL_HEALTH_CATEGORIES = {
    item.strip()
    for item in os.getenv("OPTIONAL_HEALTH_CATEGORIES", "windows").split(",")
    if item.strip()
}
OPTIONAL_HEALTH_NAMES = {
    item.strip()
    for item in os.getenv("OPTIONAL_HEALTH_NAMES", "windows_webhook,windows_tv_agent").split(",")
    if item.strip()
}

CLOUD_RUN_SERVICES = [
    {"name": "sapphire-gateway", "paths": ["/health", "/webhook/health"], "ok_statuses": [200]},
    {"name": "agentic-pm-hub", "paths": ["/health", "/"], "ok_statuses": [200]},
    {"name": "tho-agent", "paths": ["/health", "/"], "ok_statuses": [200]},
    {"name": "blanga-bis-beta", "paths": ["/", "/api/bis/health"], "ok_statuses": [200]},
    {"name": "sapphire-unified-frontend", "paths": ["/health", "/"], "ok_statuses": [200, 401, 403]},
    {"name": "sapphire-scout-sandbox", "paths": ["/health", "/"], "ok_statuses": [200]},
    {"name": "sapphire-alpha", "paths": ["/health", "/"], "ok_statuses": [200]},
    {"name": "sapphire-telegram-bot", "paths": ["/health", "/"], "ok_statuses": [200, 401, 403]},
    {"name": "sapphire-unified-jobs", "paths": ["/health", "/"], "ok_statuses": [200, 401, 403]},
]

PI_SERVICES = {
    'rari1': {
        'ip': RARI1_IP,
        'services': [
            {'name': 'research_output', 'port': 8000, 'paths': ['/output/latest_hourly.json'], 'ok_statuses': [200]},
        ]
    },
    'rari2': {
        'ip': RARI2_IP,
        'services': [
            {'name': 'lighter_gateway', 'port': 8080, 'paths': ['/health'], 'ok_statuses': [200]},
        ]
    }
}


@dataclass
class HealthStatus:
    """Health status for a single component"""
    name: str
    category: str  # 'pi', 'windows', 'cloud', 'firestore'
    healthy: bool
    response_time_ms: float
    last_checked: str
    error: Optional[str] = None
    details: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class UnifiedHealthMonitor:
    """Unified health monitoring for Sapphire trading system"""
    
    def __init__(self):
        self.status_history: List[HealthStatus] = []
        self.alert_state_file = Path.home() / '.sapphire_health_state.json'
        self.state = self._load_state()
        self.db = None
        self._init_firestore()
        
    def _init_firestore(self):
        """Initialize Firestore connection"""
        try:
            # Try to get existing app
            self.db = firestore.client()
        except ValueError:
            # Initialize new app
            try:
                cred = credentials.ApplicationDefault()
                initialize_app(cred, {'projectId': GCP_PROJECT})
                self.db = firestore.client()
            except Exception as e:
                print(f"Warning: Firestore not available: {e}")
                
    def _load_state(self) -> Dict:
        """Load alert state to prevent spam"""
        if self.alert_state_file.exists():
            with open(self.alert_state_file) as f:
                return json.load(f)
        return {
            'last_alert': None,
            'alert_count': 0,
            'service_states': {}
        }
    
    def _save_state(self):
        """Save alert state"""
        with open(self.alert_state_file, 'w') as f:
            json.dump(self.state, f)
    
    def _should_alert(self, service: str, cooldown_minutes: int = 30) -> bool:
        """Check if enough time has passed since last alert"""
        now = datetime.now()
        last = self.state['service_states'].get(service, {}).get('last_alert')
        if last:
            last_time = datetime.fromisoformat(last)
            if now - last_time < timedelta(minutes=cooldown_minutes):
                return False
        
        if service not in self.state['service_states']:
            self.state['service_states'][service] = {}
        self.state['service_states'][service]['last_alert'] = now.isoformat()
        self.state['alert_count'] += 1
        return True
    
    async def check_http_endpoint(
        self, 
        session: aiohttp.ClientSession,
        name: str,
        url: str,
        category: str,
        timeout: int = 10,
        ok_statuses: Optional[List[int]] = None,
    ) -> HealthStatus:
        """Check a single HTTP endpoint"""
        start = datetime.now()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                elapsed = (datetime.now() - start).total_seconds() * 1000
                status_set = set(ok_statuses or [200])
                healthy = response.status in status_set
                if not healthy and response.status in (401, 403) and any(code in status_set for code in (401, 403)):
                    healthy = True
                
                try:
                    details = await response.json()
                except:
                    details = {'status_code': response.status}

                if response.status in (401, 403):
                    details['auth_protected'] = True
                details['url'] = url
                
                return HealthStatus(
                    name=name,
                    category=category,
                    healthy=healthy,
                    response_time_ms=round(elapsed, 2),
                    last_checked=datetime.now().isoformat(),
                    error=None if healthy else f"HTTP {response.status}",
                    details=details
                )
        except asyncio.TimeoutError:
            return HealthStatus(
                name=name,
                category=category,
                healthy=False,
                response_time_ms=(datetime.now() - start).total_seconds() * 1000,
                last_checked=datetime.now().isoformat(),
                error="Timeout",
                details=None
            )
        except Exception as e:
            return HealthStatus(
                name=name,
                category=category,
                healthy=False,
                response_time_ms=(datetime.now() - start).total_seconds() * 1000,
                last_checked=datetime.now().isoformat(),
                error=str(e)[:100],
                details=None
            )
    
    async def check_pi_services(self) -> List[HealthStatus]:
        """Check all Pi services"""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for pi_name, pi_config in PI_SERVICES.items():
                for service in pi_config['services']:
                    tasks.append(self._check_pi_service(session, pi_name, pi_config['ip'], service))
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(HealthStatus(
                    name=f"pi_error_{i}",
                    category='pi',
                    healthy=False,
                    response_time_ms=0,
                    last_checked=datetime.now().isoformat(),
                    error=str(result)[:100],
                    details=None
                ))
            else:
                processed.append(result)
        
        return processed

    async def _check_pi_service(
        self,
        session: aiohttp.ClientSession,
        pi_name: str,
        ip: str,
        service: Dict[str, Any],
    ) -> HealthStatus:
        """Probe one Pi service using multiple candidate paths."""
        service_name = f"{pi_name}_{service['name']}"
        paths = service.get('paths') or [service.get('path', '/')]
        ok_statuses = service.get('ok_statuses', [200])

        last_result = None
        for path in paths:
            url = f"http://{ip}:{service['port']}{path}"
            last_result = await self.check_http_endpoint(
                session,
                service_name,
                url,
                'pi',
                ok_statuses=ok_statuses,
            )
            if last_result.healthy:
                return last_result

        return last_result if last_result is not None else HealthStatus(
            name=service_name,
            category='pi',
            healthy=False,
            response_time_ms=0,
            last_checked=datetime.now().isoformat(),
            error='No paths configured',
            details=None,
        )
    
    async def check_windows_services(self) -> List[HealthStatus]:
        """Check Windows webhook and TV agent endpoints."""
        async with aiohttp.ClientSession() as session:
            webhook = await self.check_http_endpoint(
                session,
                'windows_webhook',
                f'http://{WINDOWS_IP}:{WINDOWS_WEBHOOK_PORT}/webhook/health',
                'windows'
            )
            if not webhook.healthy:
                webhook = await self.check_http_endpoint(
                    session,
                    'windows_webhook',
                    f'http://{WINDOWS_IP}:{WINDOWS_WEBHOOK_PORT}/status',
                    'windows'
                )
            if not webhook.healthy:
                webhook = await self.check_http_endpoint(
                    session,
                    'windows_webhook',
                    f'http://{WINDOWS_IP}:{WINDOWS_WEBHOOK_PORT}/',
                    'windows'
                )

            tv_agent = await self.check_http_endpoint(
                session,
                'windows_tv_agent',
                f'http://{WINDOWS_IP}:{WINDOWS_TV_AGENT_PORT}/health',
                'windows'
            )
            if not tv_agent.healthy:
                tv_agent = await self.check_http_endpoint(
                    session,
                    'windows_tv_agent',
                    f'http://{WINDOWS_IP}:{WINDOWS_TV_AGENT_PORT}/',
                    'windows'
                )

            return [webhook, tv_agent]
    
    async def check_cloud_run_services(self) -> List[HealthStatus]:
        """Check all Cloud Run services"""
        results = []
        async with aiohttp.ClientSession() as session:
            for service in CLOUD_RUN_SERVICES:
                service_name = service['name']
                paths = service.get('paths', ['/'])
                ok_statuses = service.get('ok_statuses', [200])
                project_hash = '267358751314'  # GCP project number
                base_url = f"https://{service_name}-{project_hash}.us-central1.run.app"

                result = None
                for path in paths:
                    url = f"{base_url}{path}"
                    result = await self.check_http_endpoint(
                        session,
                        service_name,
                        url,
                        'cloud',
                        timeout=15,
                        ok_statuses=ok_statuses,
                    )
                    if result.healthy:
                        break

                if result is not None:
                    results.append(result)
        
        return results
    
    def check_firestore(self) -> HealthStatus:
        """Check Firestore connectivity"""
        start = datetime.now()
        try:
            if self.db:
                # Try to read a document
                docs = list(self.db.collection('system_logs').limit(1).stream())
                elapsed = (datetime.now() - start).total_seconds() * 1000
                return HealthStatus(
                    name='firestore',
                    category='firestore',
                    healthy=True,
                    response_time_ms=round(elapsed, 2),
                    last_checked=datetime.now().isoformat(),
                    error=None,
                    details={'collections_accessible': True}
                )
            else:
                return HealthStatus(
                    name='firestore',
                    category='firestore',
                    healthy=False,
                    response_time_ms=0,
                    last_checked=datetime.now().isoformat(),
                    error='Firestore not initialized',
                    details=None
                )
        except Exception as e:
            return HealthStatus(
                name='firestore',
                category='firestore',
                healthy=False,
                response_time_ms=(datetime.now() - start).total_seconds() * 1000,
                last_checked=datetime.now().isoformat(),
                error=str(e)[:100],
                details=None
            )
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks"""
        print(f"[{datetime.now().isoformat()}] Starting health checks...")
        
        # Run async checks
        pi_results, cloud_results, windows_results = await asyncio.gather(
            self.check_pi_services(),
            self.check_cloud_run_services(),
            self.check_windows_services()
        )
        
        # Run sync checks
        firestore_result = self.check_firestore()
        
        # Combine all results
        all_results = pi_results + cloud_results + windows_results + [firestore_result]
        core_results = [r for r in all_results if not self._is_optional_service(r)]
        optional_results = [r for r in all_results if self._is_optional_service(r)]
        core_unhealthy = [r for r in core_results if not r.healthy]
        optional_degraded = [r for r in optional_results if not r.healthy]

        # Categorize results
        summary = {
            'timestamp': datetime.now().isoformat(),
            # Core health excludes optional edge categories (for resilient production gating).
            'overall_healthy': all(r.healthy for r in core_results),
            'total_services': len(core_results),
            'healthy_count': sum(1 for r in core_results if r.healthy),
            'unhealthy_count': len(core_unhealthy),
            # Full visibility across all monitored services.
            'all_total_services': len(all_results),
            'all_healthy_count': sum(1 for r in all_results if r.healthy),
            'all_unhealthy_count': sum(1 for r in all_results if not r.healthy),
            'optional_total': len(optional_results),
            'optional_degraded_count': len(optional_degraded),
            'by_category': {
                'pi': [r.to_dict() for r in all_results if r.category == 'pi'],
                'windows': [r.to_dict() for r in all_results if r.category == 'windows'],
                'cloud': [r.to_dict() for r in all_results if r.category == 'cloud'],
                'firestore': [r.to_dict() for r in all_results if r.category == 'firestore']
            },
            'unhealthy_services': [
                r.to_dict() for r in core_unhealthy
            ],
            'optional_degraded_services': [
                r.to_dict() for r in optional_degraded
            ],
        }
        
        # Store in Firestore if available
        if self.db:
            try:
                self.db.collection('health_checks').document().set(summary)
                # Also update current status document
                self.db.collection('system_status').document('current').set(summary)
            except Exception as e:
                print(f"Failed to store health check: {e}")
        
        # Check for alerts
        await self._send_alerts(all_results)
        
        print(f"[{datetime.now().isoformat()}] Health checks complete: "
              f"{summary['healthy_count']}/{summary['total_services']} healthy")
        
        return summary

    def _is_optional_service(self, status: HealthStatus) -> bool:
        if status.category in OPTIONAL_HEALTH_CATEGORIES:
            return True
        return status.name in OPTIONAL_HEALTH_NAMES

    async def _send_alerts(self, results: List[HealthStatus]):
        """Send Telegram alerts for unhealthy services"""
        unhealthy = [r for r in results if (not r.healthy and not self._is_optional_service(r))]

        if not unhealthy:
            return
        
        # Check if we should send alert
        if not self._should_alert('health_alert', cooldown_minutes=15):
            return
        
        # Build alert message
        lines = [
            "🚨 *Sapphire Health Alert*",
            f"_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
            "",
            f"*{len(unhealthy)} services unhealthy:*",
            ""
        ]
        
        for r in unhealthy:
            emoji = {
                'pi': '🥧',
                'windows': '🪟',
                'cloud': '☁️',
                'firestore': '🔥'
            }.get(r.category, '⚠️')
            lines.append(f"{emoji} *{r.name}*: {r.error or 'Unknown error'}")
        
        message = '\n'.join(lines)
        
        # Send Telegram alert
        if TELEGRAM_BOT_TOKEN:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'text': message,
                    'parse_mode': 'Markdown'
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            print(f"Alert sent for {len(unhealthy)} unhealthy services")
                        else:
                            print(f"Failed to send alert: {resp.status}")
            except Exception as e:
                print(f"Failed to send Telegram alert: {e}")
        else:
            print(f"[ALERT - no token] {message}")
        
        self._save_state()
    
    def get_system_status(self) -> Dict:
        """Get current system status from Firestore"""
        if not self.db:
            return {'error': 'Firestore not available'}
        
        try:
            doc = self.db.collection('system_status').document('current').get()
            if doc.exists:
                return doc.to_dict()
            else:
                return {'error': 'No status data available'}
        except Exception as e:
            return {'error': str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Sapphire Unified Health Monitor')
    parser.add_argument('--check', action='store_true', help='Run health check once')
    parser.add_argument('--watch', action='store_true', help='Run continuous monitoring')
    parser.add_argument('--interval', type=int, default=300, help='Check interval in seconds')
    parser.add_argument('--status', action='store_true', help='Show current status')
    args = parser.parse_args()
    
    monitor = UnifiedHealthMonitor()
    
    if args.status:
        status = monitor.get_system_status()
        print(json.dumps(status, indent=2))
    
    elif args.check:
        result = asyncio.run(monitor.run_all_checks())
        print(json.dumps(result, indent=2))
    
    elif args.watch:
        print(f"Starting continuous monitoring (interval: {args.interval}s)...")
        while True:
            try:
                asyncio.run(monitor.run_all_checks())
                print(f"Sleeping {args.interval}s...")
                import time
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\n👋 Monitor stopped")
                break
    
    else:
        print("Usage: unified_health_monitor.py --check | --watch | --status")
        print("\nExamples:")
        print("  Run single check:  ./unified_health_monitor.py --check")
        print("  Continuous monitor: ./unified_health_monitor.py --watch")
        print("  Show last status:  ./unified_health_monitor.py --status")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Sapphire Health Monitor
Background monitoring script for alerting on system issues
Can be run as Cloud Run job, Cloud Function, or locally
"""

import os
import sys
from datetime import datetime

import requests

# Configuration
CONFIG = {
    'sapphire_url': os.environ.get('SAPPHIRE_URL', 'https://sapphirealpha.xyz'),
    'alert_threshold': float(os.environ.get('ALERT_THRESHOLD', '0.7')),
    'webhook_url': os.environ.get('ALERT_WEBHOOK_URL', ''),  # For Slack/Discord
    'telegram_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
    'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID', ''),
    'services_to_monitor': [
        'gateway',
        'gateway_signal_ingress',
        'alpha_engine',
        'pm_hub',
        'rari1_research_output',
        'rari2_trading_api',
        'rari2_lighter_api',
    ]
}


class HealthMonitor:
    def __init__(self):
        self.previous_status = {}
        self.alert_count = 0

    def check_health(self) -> dict:
        """Check system health and return status"""
        try:
            resp = requests.get(
                f"{CONFIG['sapphire_url']}/api/status",
                timeout=10
            )

            if resp.status_code != 200:
                return {
                    'status': 'error',
                    'message': f'HTTP {resp.status_code}',
                    'timestamp': datetime.utcnow().isoformat()
                }

            data = resp.json()
            by_category = data.get('by_category', {})

            # Count services
            total = 0
            healthy = 0
            degraded = []

            for category, services in by_category.items():
                for svc in services:
                    name = svc.get('name', 'unknown')
                    is_healthy = svc.get('healthy', False)
                    response_time = svc.get('response_time_ms', 0)

                    total += 1
                    if is_healthy:
                        healthy += 1
                    else:
                        degraded.append({
                            'name': name,
                            'category': category,
                            'response_time': response_time
                        })

            ratio = healthy / total if total > 0 else 0

            status = {
                'status': 'healthy' if ratio == 1.0 else 'degraded' if ratio >= CONFIG['alert_threshold'] else 'critical',
                'healthy': healthy,
                'total': total,
                'ratio': ratio,
                'degraded_services': degraded,
                'timestamp': datetime.utcnow().isoformat()
            }

            return status

        except requests.exceptions.Timeout:
            return {
                'status': 'critical',
                'message': 'Timeout checking health',
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                'status': 'critical',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def send_alert(self, status: dict):
        """Send alert via configured channels"""
        message = self._format_alert(status)

        # Send to webhook (Slack/Discord)
        if CONFIG['webhook_url']:
            self._send_webhook(message)

        # Send to Telegram
        if CONFIG['telegram_token'] and CONFIG['telegram_chat_id']:
            self._send_telegram(message)

        # Print to stdout (for Cloud Logging)
        print(f"ALERT: {message}")

    def _format_alert(self, status: dict) -> str:
        """Format alert message"""
        status_emoji = {
            'healthy': '✅',
            'degraded': '⚠️',
            'critical': '❌'
        }

        emoji = status_emoji.get(status['status'], '❓')

        msg = f"{emoji} Sapphire Health Alert\n\n"
        msg += f"Status: {status['status'].upper()}\n"

        if 'healthy' in status:
            msg += f"Services: {status['healthy']}/{status['total']} healthy\n"

        if 'degraded_services' in status and status['degraded_services']:
            msg += "\nDegraded Services:\n"
            for svc in status['degraded_services']:
                msg += f"  • {svc['name']} ({svc['category']})\n"

        if 'message' in status:
            msg += f"\nError: {status['message']}\n"

        msg += f"\nTime: {status['timestamp']}"

        return msg

    def _send_webhook(self, message: str):
        """Send alert to webhook (Slack/Discord compatible)"""
        try:
            payload = {
                'text': message,
                'username': 'Sapphire Health Monitor'
            }

            # Try Slack format first
            resp = requests.post(
                CONFIG['webhook_url'],
                json=payload,
                timeout=10
            )

            if resp.status_code != 200:
                # Try Discord format
                discord_payload = {
                    'content': message
                }
                requests.post(
                    CONFIG['webhook_url'],
                    json=discord_payload,
                    timeout=10
                )
        except Exception as e:
            print(f"Webhook error: {e}")

    def _send_telegram(self, message: str):
        """Send alert via Telegram"""
        try:
            url = f"https://api.telegram.org/bot{CONFIG['telegram_token']}/sendMessage"
            payload = {
                'chat_id': CONFIG['telegram_chat_id'],
                'text': message,
                'parse_mode': 'Markdown'
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Telegram error: {e}")

    def run_check(self):
        """Run a single health check"""
        status = self.check_health()

        # Determine if alert is needed
        should_alert = False

        if status['status'] in ['degraded', 'critical']:
            should_alert = True

        # Alert on status change
        current_key = f"{status.get('healthy', 0)}/{status.get('total', 0)}"
        if hasattr(self, 'previous_key') and self.previous_key != current_key:
            if status['status'] == 'healthy' and self.previous_status.get('status') != 'healthy':
                # Recovery alert
                should_alert = True

        self.previous_key = current_key
        self.previous_status = status

        if should_alert:
            self.send_alert(status)
            self.alert_count += 1

        return status

    def run_continuous(self, interval: int = 60):
        """Run continuous monitoring"""
        import time

        print(f"Starting health monitor (interval: {interval}s)")
        print(f"Alert threshold: {CONFIG['alert_threshold']*100:.0f}%")
        print(f"URL: {CONFIG['sapphire_url']}")
        print("-" * 50)

        while True:
            status = self.run_check()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: {status['status']}")
            time.sleep(interval)


def main():
    """Main entry point"""
    monitor = HealthMonitor()

    # Check if running in Cloud Run (one-shot mode)
    if os.environ.get('K_SERVICE'):
        # Run once and exit
        status = monitor.run_check()
        sys.exit(0 if status['status'] == 'healthy' else 1)
    else:
        # Run continuously
        interval = int(os.environ.get('CHECK_INTERVAL', '60'))
        monitor.run_continuous(interval)


if __name__ == '__main__':
    main()

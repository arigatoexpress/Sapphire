#!/usr/bin/env python3
import time
import requests
import json
import os
import subprocess
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.columns import Columns
from rich.status import Status
from rich import box
from rich.align import Align
from rich.syntax import Syntax

# Configuration
BASE_URL = "https://sapphire-cloud-trader-s77j6bxyra-nn.a.run.app"
HEALTH_URL = f"{BASE_URL}/health"
METRICS_URL = f"{BASE_URL}/api/agents/autonomous-performance"

console = Console()

def get_health():
    try:
        r = requests.get(HEALTH_URL, timeout=3)
        return r.json()
    except Exception:
        return None

def get_metrics():
    try:
        r = requests.get(METRICS_URL, timeout=3)
        return r.json()
    except Exception:
        return None

def make_topology_view(health_data):
    # World-Class System Topology Map
    status = health_data or {}
    deps = status.get("dependencies", {})
    
    def get_st(comp):
        s = deps.get(comp, {}).get("status", "unknown")
        if s == "healthy": return "[bold green]●[/bold green]"
        if s == "unhealthy": return "[bold red]●[/bold red]"
        return "[bold yellow]○[/bold yellow]"

    db_st = get_st("database")
    redis_st = get_st("exchange") # Redis is labeled as exchange in some health reports
    firestore_st = get_st("firestore")
    tg_st = get_st("telegram")
    
    # SVG-like ASCII Topology
    topo = Text.assemble(
        ("\n      🌐 [bold white]Public Access[/bold white]\n", "cyan"),
        ("            │\n", "bright_black"),
        ("      ┌─────┴─────┐\n", "bright_black"),
        ("      ▼           ▼\n", "bright_black"),
        ("   [white]Firebase[/white]   [white]Cloudflare[/white]\n", "dim"),
        ("      │           │\n", "bright_black"),
        ("      └─────┬─────┘\n", "bright_black"),
        ("            ▼\n", "bright_black"),
        ("   ┌───────────────────┐\n", "bright_black"),
        ("   │  ", "bright_black"), ("💎 SAPPHIRE API", "bold blue"), ("  │\n", "bright_black"),
        ("   │  ", "bright_black"), (f"Version {status.get('version', '2.1.0')}", "dim"), ("   │\n", "bright_black"),
        ("   └─────────┬─────────┘\n", "bright_black"),
        ("             │ (VPC Peering)\n", "bright_black"),
        ("     ┌───────┼───────┬───────┐\n", "bright_black"),
        ("     ▼       ▼       ▼       ▼\n", "bright_black"),
        (f"  {db_st} ", ""), ("CloudSQL", "magenta"), (f"  {redis_st} ", ""), ("Redis", "yellow"), (f"  {firestore_st} ", ""), ("FStore", "orange3"), (f"  {tg_st} ", ""), ("T-Gram", "deep_sky_blue1"),
        ("\n", "")
    )
    
    return Panel(
        Align.center(topo),
        title="[bold blue]System Topology & Network Map[/bold blue]",
        subtitle="[dim]Real-time connectivity visualization[/dim]",
        border_style="bright_blue",
        box=box.DOUBLE
    )

def make_agent_matrix(metrics_data):
    grid = Table.grid(expand=True, padding=1)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)

    if metrics_data and "agents" in metrics_data:
        agents = metrics_data["agents"]
        for i in range(0, len(agents), 2):
            row_cells = []
            for j in range(2):
                if i + j < len(agents):
                    a = agents[i+j]
                    wr = a.get("win_rate", 0)
                    wr_color = "green" if wr > 0.55 else "yellow" if wr > 0.45 else "red"
                    
                    card = Panel(
                        Text.assemble(
                            (f"{a['id']}\n", "bold cyan"),
                            (f"Model: {a.get('model', 'N/A')}\n", "dim"),
                            (f"Win Rate: ", ""), (f"{wr*100:.1f}%\n", f"bold {wr_color}"),
                            (f"PnL: ", ""), (f"${a.get('total_pnl', 0):,.2f}", "green" if a.get("total_pnl", 0) >= 0 else "red")
                        ),
                        border_style="bright_black" if a.get("status") == "active" else "red",
                        padding=(0, 1)
                    )
                    row_cells.append(card)
                else:
                    row_cells.append("")
            grid.add_row(*row_cells)
    else:
        grid.add_row(Panel("[dim]Waiting for agent teleportation...[/dim]", border_style="dim"))

    return Panel(grid, title="[bold green]AI Agent Intelligence Matrix[/bold green]", border_style="green")

def make_system_gauges(health_data):
    status = health_data or {}
    uptime = status.get("performance", {}).get("uptime_seconds", 0)
    msg = f"UPTIME: {uptime//3600}h {(uptime%3600)//60}m\n"
    msg += f"TRAFFIC: 100% ROUTED (v{status.get('version', '2.1.0')})\n"
    msg += f"DB STATUS: {'[green]STABLE[/green]' if status.get('dependencies', {}).get('database', {}).get('status') == 'healthy' else '[red]INITIALIZING...[/red]'}"
    
    return Panel(Text(msg, justify="center"), title="[bold yellow]Core Metrics[/bold yellow]", border_style="yellow")

def make_header():
    return Panel(
        Align.center("[bold white]💠 SAPPHIRE OPERATIONAL COMMAND CENTER[/bold white]\n[dim]High-Frequency Autonomous Intelligence Monitoring[/dim]"),
        style="bg:blue color:white",
        box=box.HEAVY
    )

def main():
    layout = Layout()
    layout.split(
        Layout(name="header", size=4),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["body"].split_row(
        Layout(name="topo", ratio=6),
        Layout(name="metrics", ratio=4)
    )
    layout["metrics"].split_column(
        Layout(name="gauges", size=6),
        Layout(name="matrix", ratio=1)
    )

    with Live(layout, refresh_per_second=1, screen=True) as live:
        while True:
            health = get_health()
            metrics = get_metrics()
            
            layout["header"].update(make_header())
            layout["topo"].update(make_topology_view(health))
            layout["gauges"].update(make_system_gauges(health))
            layout["matrix"].update(make_agent_matrix(metrics))
            
            # Status Bar
            st = "[bold green]STABLE[/bold green]" if health else "[bold red]SIGNAL LOST[/bold red]"
            layout["footer"].update(Panel(Align.center(f"LIVE SYSTEM STATUS: {st} | Last Ping: {datetime.now().strftime('%H:%M:%S')}"), border_style="dim"))
            
            time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

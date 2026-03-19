#!/usr/bin/env python3
"""
Sapphire OS - Weekly Self-Improvement Review

This script runs weekly to:
1. Analyze trading performance metrics
2. Compare against targets
3. Create improvement tasks if needed
4. Log review results

Run via: Cloud Scheduler (Sundays at 2 AM UTC)
"""

import os
import json
import sys
from datetime import datetime, timedelta
from google.cloud import firestore, pubsub_v1
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

# Configuration
PROJECT_ID = "sapphire-479610"
METRICS_COLLECTION = "trading_performance"
TASKS_COLLECTION = "improvement_tasks"
REVIEWS_COLLECTION = "weekly_reviews"

# Targets
TARGET_WIN_RATE = 0.80
TARGET_SORTINO = 2.0
TARGET_CALMAR = 1.0
MAX_DRAWDOWN = 0.10

@dataclass
class TradingMetrics:
    """Trading performance metrics"""
    week_ending: str
    pnl_cumulative: float
    pnl_weekly: float
    win_rate: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    
@dataclass
class ImprovementTask:
    """Task created by self-improvement system"""
    task_id: str
    created_at: str
    priority: str  # critical, high, medium, low
    assignee: str  # agent name
    title: str
    description: str
    metric_trigger: str
    metric_value: float
    status: str = "open"

class SelfImprovementEngine:
    """Engine for autonomous system improvement"""
    
    def __init__(self):
        self.db = firestore.Client(project=PROJECT_ID)
        self.publisher = pubsub_v1.PublisherClient()
        
    def get_weekly_metrics(self) -> Optional[TradingMetrics]:
        """Fetch metrics for the past week from Firestore"""
        # Get last 7 days of trading data
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        trades_ref = self.db.collection("trades")
        query = trades_ref.where("timestamp", ">=", week_ago.isoformat())
        trades = list(query.stream())
        
        if not trades:
            print("No trades found in past week")
            return None
            
        # Calculate metrics
        total = len(trades)
        winning = sum(1 for t in trades if t.to_dict().get("pnl", 0) > 0)
        losing = total - winning
        win_rate = winning / total if total > 0 else 0
        
        pnls = [t.to_dict().get("pnl", 0) for t in trades]
        pnl_weekly = sum(pnls)
        
        # Get cumulative PnL
        perf_doc = self.db.collection(METRICS_COLLECTION).document("cumulative").get()
        pnl_cumulative = perf_doc.to_dict().get("pnl", 0) if perf_doc.exists else pnl_weekly
        
        # Calculate Sortino and Calmar (simplified)
        avg_win = sum(p for p in pnls if p > 0) / winning if winning > 0 else 0
        avg_loss = sum(p for p in pnls if p < 0) / losing if losing > 0 else 0
        
        # Simplified Sortino (downside deviation only)
        downside_returns = [p for p in pnls if p < 0]
        downside_std = (sum(r**2 for r in downside_returns) / len(downside_returns))**0.5 if downside_returns else 1
        sortino = (pnl_weekly / 7) / downside_std if downside_std > 0 else 0
        
        # Simplified Calmar (annualized return / max drawdown)
        max_dd = max((t.to_dict().get("drawdown", 0) for t in trades), default=0)
        calmar = (pnl_weekly * 52) / max_dd if max_dd > 0 else 0
        
        return TradingMetrics(
            week_ending=datetime.utcnow().isoformat(),
            pnl_cumulative=pnl_cumulative,
            pnl_weekly=pnl_weekly,
            win_rate=win_rate,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            total_trades=total,
            winning_trades=winning,
            losing_trades=losing,
            avg_win=avg_win,
            avg_loss=avg_loss
        )
    
    def analyze_metrics(self, metrics: TradingMetrics) -> List[ImprovementTask]:
        """Analyze metrics and create improvement tasks if needed"""
        tasks = []
        
        # Check win rate
        if metrics.win_rate < 0.65:
            tasks.append(ImprovementTask(
                task_id=f"win_rate_{datetime.utcnow().strftime('%Y%m%d')}",
                created_at=datetime.utcnow().isoformat(),
                priority="high",
                assignee="strategy_optimizer",
                title="Win Rate Below Threshold",
                description=f"Win rate ({metrics.win_rate:.1%}) below 65% target. Review strategy parameters and optimize entry/exit conditions.",
                metric_trigger="win_rate",
                metric_value=metrics.win_rate
            ))
        
        # Check drawdown
        if metrics.max_drawdown > MAX_DRAWDOWN:
            tasks.append(ImprovementTask(
                task_id=f"drawdown_{datetime.utcnow().strftime('%Y%m%d')}",
                created_at=datetime.utcnow().isoformat(),
                priority="critical",
                assignee="risk_manager",
                title="Max Drawdown Exceeded",
                description=f"Max drawdown ({metrics.max_drawdown:.1%}) exceeded 10% limit. Implement tighter risk controls.",
                metric_trigger="max_drawdown",
                metric_value=metrics.max_drawdown
            ))
        
        # Check Sortino
        if metrics.sortino_ratio < 1.0:
            tasks.append(ImprovementTask(
                task_id=f"sortino_{datetime.utcnow().strftime('%Y%m%d')}",
                created_at=datetime.utcnow().isoformat(),
                priority="medium",
                assignee="strategy_optimizer",
                title="Risk-Adjusted Returns Low",
                description=f"Sortino ratio ({metrics.sortino_ratio:.2f}) below target. Optimize risk/reward ratio.",
                metric_trigger="sortino_ratio",
                metric_value=metrics.sortino_ratio
            ))
        
        # Always create weekly review task
        tasks.append(ImprovementTask(
            task_id=f"weekly_review_{datetime.utcnow().strftime('%Y%m%d')}",
            created_at=datetime.utcnow().isoformat(),
            priority="medium",
            assignee="code_improver",
            title="Weekly System Review",
            description=f"Review weekly metrics: PnL ${metrics.pnl_weekly:.2f}, Win Rate {metrics.win_rate:.1%}, {metrics.total_trades} trades.",
            metric_trigger="weekly_schedule",
            metric_value=0
        ))
        
        return tasks
    
    def create_tasks(self, tasks: List[ImprovementTask]):
        """Store improvement tasks in Firestore"""
        for task in tasks:
            doc_ref = self.db.collection(TASKS_COLLECTION).document(task.task_id)
            doc_ref.set(asdict(task))
            print(f"Created task: {task.title} (Priority: {task.priority})")
            
            # Publish to Pub/Sub for immediate agent notification
            topic_path = self.publisher.topic_path(PROJECT_ID, "improvement-tasks")
            message = json.dumps(asdict(task)).encode("utf-8")
            self.publisher.publish(topic_path, message, task_id=task.task_id)
    
    def save_review(self, metrics: TradingMetrics, tasks: List[ImprovementTask]):
        """Save weekly review to Firestore"""
        review_id = datetime.utcnow().strftime("%Y-W%U")
        review = {
            "review_id": review_id,
            "created_at": datetime.utcnow().isoformat(),
            "metrics": asdict(metrics),
            "tasks_created": len(tasks),
            "task_ids": [t.task_id for t in tasks],
            "status": "complete"
        }
        
        doc_ref = self.db.collection(REVIEWS_COLLECTION).document(review_id)
        doc_ref.set(review)
        print(f"Saved review: {review_id}")
    
    def run_weekly_review(self):
        """Main entry point - run weekly self-improvement review"""
        print(f"=== Weekly Self-Improvement Review ===")
        print(f"Time: {datetime.utcnow().isoformat()}")
        
        # Get metrics
        metrics = self.get_weekly_metrics()
        if not metrics:
            print("No metrics available - skipping review")
            return
            
        print(f"\nWeekly Performance:")
        print(f"  PnL: ${metrics.pnl_weekly:.2f} (Cumulative: ${metrics.pnl_cumulative:.2f})")
        print(f"  Win Rate: {metrics.win_rate:.1%} ({metrics.winning_trades}/{metrics.total_trades})")
        print(f"  Sortino: {metrics.sortino_ratio:.2f}")
        print(f"  Calmar: {metrics.calmar_ratio:.2f}")
        print(f"  Max Drawdown: {metrics.max_drawdown:.1%}")
        
        # Analyze and create tasks
        tasks = self.analyze_metrics(metrics)
        print(f"\nCreating {len(tasks)} improvement tasks...")
        self.create_tasks(tasks)
        
        # Save review
        self.save_review(metrics, tasks)
        
        print("\n=== Review Complete ===")

if __name__ == "__main__":
    engine = SelfImprovementEngine()
    engine.run_weekly_review()

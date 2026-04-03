"""
Monte Carlo Risk Simulation for HFT

Validates survival probability and capital growth trajectory:
- Target: 70-80% survival probability over 24 months
- Max drawdown: 30% limit
- Expected path to $500K from $50
- 1000+ simulation runs

Research findings: Critical for validating $50→$500K feasibility
"""

from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np

from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class MonteCarloConfig:
    """Configuration for Monte Carlo simulation"""
    initial_capital: float = 50.0
    target_capital: float = 500000.0
    num_simulations: int = 1000
    trading_days: int = 720  # 24 months * 30 days
    trades_per_day: int = 50  # Target for HFT
    win_prob: float = 0.55  # Conservative 55%
    avg_win_pct: float = 0.5  # 0.5% per winning trade
    avg_loss_pct: float = 0.3  # 0.3% per losing trade
    risk_per_trade_pct: float = 1.0  # 1% risk per trade
    max_drawdown_limit: float = 0.30  # 30% max drawdown
    daily_loss_limit_pct: float = 20.0  # 20% daily loss limit
    

class MonteCarloSimulator:
    """
    Monte Carlo Simulation for HFT Risk Assessment
    
    Features:
    - Path-dependent simulation
    - Realistic trade distributions
    - Risk management rules enforcement
    - Multiple outcome scenarios
    - Confidence interval estimation
    """
    
    def __init__(self, config: MonteCarloConfig):
        self.config = config
        self.simulation_results = []
        self.successful_paths = []
        self.failed_paths = []
        
        logger.info("[RANDOM] Monte Carlo Simulator initialized")
        logger.info(f"[TARGET] Target: ${config.initial_capital:.0f} → ${config.target_capital:.0f}")
        logger.info(f"[DATA] Simulations: {config.num_simulations}")
    
    def simulate_single_trade(self,
                             capital: float,
                             win_prob: float = None) -> tuple[float, bool]:
        """
        Simulate a single trade outcome
        
        Args:
            capital: Current capital
            win_prob: Win probability (uses config default if None)
            
        Returns:
            Tuple of (pnl, is_win)
        """
        if win_prob is None:
            win_prob = self.config.win_prob
        
        # Determine if trade wins
        is_win = np.random.random() < win_prob
        
        # Calculate P&L
        if is_win:
            # Winning trade: avg_win_pct with some variance
            win_pct = np.random.normal(
                self.config.avg_win_pct,
                self.config.avg_win_pct * 0.5  # 50% std dev
            )
            win_pct = max(0.1, win_pct)  # Minimum 0.1%
            pnl = capital * (self.config.risk_per_trade_pct / 100.0) * win_pct
        else:
            # Losing trade: avg_loss_pct with some variance
            loss_pct = np.random.normal(
                self.config.avg_loss_pct,
                self.config.avg_loss_pct * 0.3
            )
            loss_pct = max(0.05, loss_pct)  # Minimum 0.05%
            pnl = -capital * (self.config.risk_per_trade_pct / 100.0) * loss_pct
        
        return pnl, is_win
    
    def simulate_single_day(self,
                           capital: float,
                           trades_per_day: int = None) -> tuple[float, dict]:
        """
        Simulate a single day of trading
        
        Args:
            capital: Starting capital for the day
            trades_per_day: Number of trades (uses config default if None)
            
        Returns:
            Tuple of (ending_capital, day_stats)
        """
        if trades_per_day is None:
            trades_per_day = self.config.trades_per_day
        
        starting_capital = capital
        daily_pnl = 0.0
        wins = 0
        losses = 0
        peak_capital_today = capital
        max_drawdown_today = 0.0
        
        for _ in range(trades_per_day):
            pnl, is_win = self.simulate_single_trade(capital)
            
            capital += pnl
            daily_pnl += pnl
            
            if is_win:
                wins += 1
            else:
                losses += 1
            
            # Track intraday drawdown
            peak_capital_today = max(peak_capital_today, capital)
            current_drawdown = (peak_capital_today - capital) / peak_capital_today
            max_drawdown_today = max(max_drawdown_today, current_drawdown)
            
            # Check daily loss limit
            daily_loss_pct = (capital - starting_capital) / starting_capital
            if daily_loss_pct < -self.config.daily_loss_limit_pct / 100.0:
                # Hit daily loss limit - stop trading for the day
                break
            
            # Check if wiped out
            if capital <= 0:
                capital = 0
                break
        
        day_stats = {
            'starting_capital': starting_capital,
            'ending_capital': capital,
            'daily_pnl': daily_pnl,
            'daily_return': daily_pnl / starting_capital if starting_capital > 0 else 0,
            'wins': wins,
            'losses': losses,
            'win_rate': wins / (wins + losses) if (wins + losses) > 0 else 0,
            'max_drawdown_today': max_drawdown_today
        }
        
        return capital, day_stats
    
    def simulate_single_path(self,
                            path_id: int = 0,
                            verbose: bool = False) -> dict:
        """
        Simulate a single capital growth path
        
        Args:
            path_id: Path identifier
            verbose: Whether to log progress
            
        Returns:
            Dictionary of simulation results
        """
        capital = self.config.initial_capital
        daily_capitals = [capital]
        daily_stats = []
        
        peak_capital = capital
        max_drawdown = 0.0
        wiped_out = False
        days_to_target = None
        
        for day in range(self.config.trading_days):
            # Simulate day
            capital, day_stat = self.simulate_single_day(capital)
            daily_capitals.append(capital)
            daily_stats.append(day_stat)
            
            # Update peak and drawdown
            peak_capital = max(peak_capital, capital)
            current_drawdown = (peak_capital - capital) / peak_capital
            max_drawdown = max(max_drawdown, current_drawdown)
            
            # Check if wiped out
            if capital <= 0:
                wiped_out = True
                if verbose:
                    logger.info(f"Path {path_id}: Wiped out on day {day}")
                break
            
            # Check if reached target
            if capital >= self.config.target_capital and days_to_target is None:
                days_to_target = day + 1
                if verbose:
                    logger.info(f"Path {path_id}: Reached target on day {day}")
            
            # Check drawdown limit
            if max_drawdown > self.config.max_drawdown_limit:
                if verbose:
                    logger.warning(f"Path {path_id}: Exceeded max drawdown on day {day}")
        
        # Calculate final statistics
        final_capital = capital
        total_return = (final_capital - self.config.initial_capital) / self.config.initial_capital
        success = final_capital >= self.config.target_capital
        
        result = {
            'path_id': path_id,
            'final_capital': final_capital,
            'total_return': total_return,
            'max_drawdown': max_drawdown,
            'days_to_target': days_to_target,
            'wiped_out': wiped_out,
            'success': success,
            'daily_capitals': daily_capitals,
            'daily_stats': daily_stats
        }
        
        return result
    
    def run_simulation(self, save_paths: bool = False) -> dict:
        """
        Run full Monte Carlo simulation
        
        Args:
            save_paths: Whether to save individual paths (memory intensive)
            
        Returns:
            Dictionary of aggregated results
        """
        logger.info(f"[RANDOM] Running {self.config.num_simulations} Monte Carlo simulations...")
        
        self.simulation_results = []
        self.successful_paths = []
        self.failed_paths = []
        
        # Run simulations
        for i in range(self.config.num_simulations):
            result = self.simulate_single_path(path_id=i, verbose=(i % 100 == 0))
            self.simulation_results.append(result)
            
            if result['success']:
                if save_paths:
                    self.successful_paths.append(result)
            else:
                if save_paths:
                    self.failed_paths.append(result)
            
            # Progress update
            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i + 1}/{self.config.num_simulations} simulations")
        
        # Aggregate results
        aggregated = self.aggregate_results()
        
        logger.info("[OK] Monte Carlo simulation complete")
        logger.info(f"[DATA] Success rate: {aggregated['success_rate']:.1%}")
        logger.info(f"[MONEY] Median final capital: ${aggregated['median_final_capital']:.2f}")
        logger.info(f"[DOWN] Median max drawdown: {aggregated['median_max_drawdown']:.1%}")
        
        return aggregated
    
    def aggregate_results(self) -> dict:
        """
        Aggregate simulation results
        
        Returns:
            Dictionary of summary statistics
        """
        if not self.simulation_results:
            return {}
        
        # Extract metrics
        final_capitals = [r['final_capital'] for r in self.simulation_results]
        total_returns = [r['total_return'] for r in self.simulation_results]
        max_drawdowns = [r['max_drawdown'] for r in self.simulation_results]
        days_to_target = [r['days_to_target'] for r in self.simulation_results if r['days_to_target'] is not None]
        
        successes = sum(1 for r in self.simulation_results if r['success'])
        wipeouts = sum(1 for r in self.simulation_results if r['wiped_out'])
        
        # Calculate statistics
        aggregated = {
            'num_simulations': len(self.simulation_results),
            'success_rate': successes / len(self.simulation_results),
            'wipeout_rate': wipeouts / len(self.simulation_results),
            
            # Final capital statistics
            'mean_final_capital': np.mean(final_capitals),
            'median_final_capital': np.median(final_capitals),
            'std_final_capital': np.std(final_capitals),
            'min_final_capital': np.min(final_capitals),
            'max_final_capital': np.max(final_capitals),
            'p25_final_capital': np.percentile(final_capitals, 25),
            'p75_final_capital': np.percentile(final_capitals, 75),
            
            # Return statistics
            'mean_total_return': np.mean(total_returns),
            'median_total_return': np.median(total_returns),
            'std_total_return': np.std(total_returns),
            
            # Drawdown statistics
            'mean_max_drawdown': np.mean(max_drawdowns),
            'median_max_drawdown': np.median(max_drawdowns),
            'max_drawdown_observed': np.max(max_drawdowns),
            'p95_max_drawdown': np.percentile(max_drawdowns, 95),
            
            # Time to target
            'mean_days_to_target': np.mean(days_to_target) if days_to_target else None,
            'median_days_to_target': np.median(days_to_target) if days_to_target else None,
            'min_days_to_target': np.min(days_to_target) if days_to_target else None,
        }
        
        # Confidence intervals (95%)
        aggregated['ci_95_final_capital'] = (
            np.percentile(final_capitals, 2.5),
            np.percentile(final_capitals, 97.5)
        )
        
        return aggregated
    
    def plot_results(self, num_paths_to_plot: int = 100, save_path: str | None = None):
        """
        Plot simulation results
        
        Args:
            num_paths_to_plot: Number of paths to visualize
            save_path: Path to save figure (optional)
        """
        if not self.simulation_results:
            logger.warning("No simulation results to plot")
            return
        
        try:
            fig, axes = plt.subplots(2, 2, figsize=(15, 10))
            
            # Plot 1: Capital paths
            ax1 = axes[0, 0]
            for i, result in enumerate(self.simulation_results[:num_paths_to_plot]):
                capitals = result['daily_capitals']
                color = 'green' if result['success'] else 'red'
                alpha = 0.3 if result['success'] else 0.2
                ax1.plot(capitals, color=color, alpha=alpha, linewidth=0.5)
            
            ax1.axhline(y=self.config.target_capital, color='blue', linestyle='--', label='Target')
            ax1.axhline(y=self.config.initial_capital, color='black', linestyle='-', alpha=0.5)
            ax1.set_xlabel('Trading Days')
            ax1.set_ylabel('Capital ($)')
            ax1.set_title(f'Capital Growth Paths (showing {num_paths_to_plot} of {len(self.simulation_results)})')
            ax1.set_yscale('log')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Plot 2: Final capital distribution
            ax2 = axes[0, 1]
            final_capitals = [r['final_capital'] for r in self.simulation_results]
            ax2.hist(final_capitals, bins=50, edgecolor='black', alpha=0.7)
            ax2.axvline(x=self.config.target_capital, color='blue', linestyle='--', label='Target')
            ax2.axvline(x=np.median(final_capitals), color='red', linestyle='--', label='Median')
            ax2.set_xlabel('Final Capital ($)')
            ax2.set_ylabel('Frequency')
            ax2.set_title('Distribution of Final Capital')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            # Plot 3: Max drawdown distribution
            ax3 = axes[1, 0]
            max_drawdowns = [r['max_drawdown'] * 100 for r in self.simulation_results]
            ax3.hist(max_drawdowns, bins=50, edgecolor='black', alpha=0.7)
            ax3.axvline(x=self.config.max_drawdown_limit * 100, color='red', linestyle='--', label='Limit')
            ax3.set_xlabel('Max Drawdown (%)')
            ax3.set_ylabel('Frequency')
            ax3.set_title('Distribution of Maximum Drawdown')
            ax3.legend()
            ax3.grid(True, alpha=0.3)
            
            # Plot 4: Days to target (for successful paths)
            ax4 = axes[1, 1]
            days_to_target = [r['days_to_target'] for r in self.simulation_results if r['days_to_target'] is not None]
            if days_to_target:
                ax4.hist(days_to_target, bins=30, edgecolor='black', alpha=0.7)
                ax4.axvline(x=np.median(days_to_target), color='red', linestyle='--', label='Median')
                ax4.set_xlabel('Days to Target')
                ax4.set_ylabel('Frequency')
                ax4.set_title(f'Days to Reach ${self.config.target_capital:.0f} (Successful Paths)')
                ax4.legend()
                ax4.grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Plot saved to {save_path}")
            
            plt.close()
            
        except Exception as e:
            logger.error(f"[ERROR] Plotting error: {e}")
    
    def get_risk_assessment(self) -> dict:
        """
        Get comprehensive risk assessment
        
        Returns:
            Dictionary of risk metrics
        """
        if not self.simulation_results:
            return {}
        
        aggregated = self.aggregate_results()
        
        # Risk assessment
        risk_assessment = {
            'survival_probability': 1 - aggregated['wipeout_rate'],
            'success_probability': aggregated['success_rate'],
            'risk_of_ruin': aggregated['wipeout_rate'],
            'expected_final_capital': aggregated['mean_final_capital'],
            'median_outcome': aggregated['median_final_capital'],
            'worst_case_5pct': aggregated['ci_95_final_capital'][0],
            'best_case_5pct': aggregated['ci_95_final_capital'][1],
            'expected_max_drawdown': aggregated['mean_max_drawdown'],
            'p95_max_drawdown': aggregated['p95_max_drawdown'],
            'median_days_to_target': aggregated['median_days_to_target'],
            'assessment': self._generate_assessment(aggregated)
        }
        
        return risk_assessment
    
    def _generate_assessment(self, aggregated: dict) -> str:
        """Generate textual risk assessment"""
        success_rate = aggregated['success_rate']
        survival_rate = 1 - aggregated['wipeout_rate']
        
        if success_rate >= 0.5 and survival_rate >= 0.7:
            return "ACCEPTABLE - Good probability of success with manageable risk"
        elif success_rate >= 0.3 and survival_rate >= 0.6:
            return "MODERATE - Possible but requires excellent execution"
        elif survival_rate >= 0.5:
            return "HIGH RISK - Low probability of reaching target, high survival risk"
        else:
            return "EXTREME RISK - Very high probability of account wipeout"


def run_quick_assessment(initial_capital: float = 50.0,
                         target_capital: float = 500000.0,
                         win_prob: float = 0.55) -> dict:
    """
    Run quick Monte Carlo assessment
    
    Args:
        initial_capital: Starting capital
        target_capital: Target capital
        win_prob: Win probability
        
    Returns:
        Risk assessment dictionary
    """
    config = MonteCarloConfig(
        initial_capital=initial_capital,
        target_capital=target_capital,
        num_simulations=100,  # Quick assessment
        win_prob=win_prob
    )
    
    simulator = MonteCarloSimulator(config)
    simulator.run_simulation()
    
    return simulator.get_risk_assessment()



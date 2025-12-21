import asyncio
import logging

from cloud_trader.experiment_tracker import get_experiment_tracker
from cloud_trader.order_manager import OrderManager
from cloud_trader.safety import get_safety_switch
from cloud_trader.state_manager import get_state_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_components():
    logger.info("Verifying Safety Components...")

    # 1. Experiment Tracker
    tracker = get_experiment_tracker()
    tracker.start_experiment("verification_test", "components load correctly")
    tracker.track_metric("test_metric", 100)
    logger.info("✅ ExperimentTracker initialized and tracking")

    # 2. State Manager
    state = get_state_manager()
    state.save_checkpoint({"status": "ok"}, is_pristine=True)
    loaded = state.load_last_good_state()
    assert loaded["status"] == "ok"
    logger.info("✅ StateManager saved and loaded checkpoint")

    # 3. Safety Switch
    safety = get_safety_switch()
    safety.heartbeat("test")
    assert safety.check_health() == True
    logger.info("✅ SafetySwitch health check passed")

    # 4. Order Manager (Mock exchange)
    class MockExchange:
        async def cancel_order(self, s, i):
            return True

    om = OrderManager(MockExchange())
    logger.info("✅ OrderManager initialized")

    logger.info("🎉 All System Components Verified!")


if __name__ == "__main__":
    asyncio.run(verify_components())

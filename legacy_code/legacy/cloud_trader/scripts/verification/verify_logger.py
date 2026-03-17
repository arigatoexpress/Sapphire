import json

from cloud_trader.logger import ContextLogger, get_logger


def test_logging():
    logger = get_logger("test_logger")

    # 1. Test Standard Log
    print("--- Test 1: Standard Log ---")
    logger.info("This is a standard log")

    # 2. Test Context Log
    print("\n--- Test 2: Context Log ---")
    ctx_logger = ContextLogger(logger, {"user_id": 123, "symbol": "BTC"})
    ctx_logger.info("This is a context log")

    # 3. Test Error Log
    print("\n--- Test 3: Error Log ---")
    try:
        1 / 0
    except Exception as e:
        logger.error("Math error occurred", exc_info=True)


if __name__ == "__main__":
    test_logging()

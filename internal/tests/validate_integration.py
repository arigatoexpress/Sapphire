"""
Quick validation of autonomous trading system integration.
Checks that all components can be imported and are properly wired.
"""


def validate_integration():
    print("🔍 AUTONOMOUS TRADING SYSTEM - VALIDATION")
    print("=" * 60)

    errors = []
    warnings = []

    # Test 1: Core module imports
    print("\n1️⃣ Testing core module imports...")
    try:
        from cloud_trader import trading_service

        print("   ✅ trading_service imported")
    except Exception as e:
        errors.append(f"trading_service import failed: {e}")
        print(f"   ❌ trading_service import failed: {e}")

    try:
        from cloud_trader.autonomous_components_init import init_autonomous_components

        print("   ✅ autonomous_components_init imported")
    except Exception as e:
        errors.append(f"autonomous_components_init import failed: {e}")
        print(f"   ❌ autonomous_components_init import failed: {e}")

    # Test 2: Component imports
    print("\n2️⃣ Testing component imports...")
    components = [
        ("DataStore", "cloud_trader.data_store"),
        ("AutonomousAgent", "cloud_trader.autonomous_agent"),
        ("PlatformRouter", "cloud_trader.platform_router"),
        ("MarketScanner", "cloud_trader.market_scanner"),
    ]

    for name, module in components:
        try:
            __import__(module)
            print(f"   ✅ {name} imported from {module}")
        except Exception as e:
            errors.append(f"{name} import failed: {e}")
            print(f"   ❌ {name} import failed: {e}")

    # Test 3: Check trading_service has new attributes
    print("\n3️⃣ Checking TradingService integration...")
    try:
        from cloud_trader.trading_service import MinimalTradingService

        # Check if class has placeholders for autonomous components
        required_attrs = ["data_store", "autonomous_agents", "platform_router", "market_scanner"]

        # We can't instantiate without full setup, but we can check the __init__
        import inspect

        init_source = inspect.getsource(MinimalTradingService.__init__)

        for attr in required_attrs:
            if f"self.{attr}" in init_source:
                print(f"   ✅ {attr} initialized in __init__")
            else:
                warnings.append(f"{attr} not found in __init__")
                print(f"   ⚠️  {attr} not explicitly set in __init__")

    except Exception as e:
        errors.append(f"TradingService check failed: {e}")
        print(f"   ❌ TradingService check failed: {e}")

    # Test 4: Check helper methods exist
    print("\n4️⃣ Checking helper methods...")
    try:
        import inspect

        from cloud_trader.trading_service import MinimalTradingService

        methods = inspect.getmembers(MinimalTradingService, predicate=inspect.isfunction)
        method_names = [name for name, _ in methods]

        required_methods = [
            "_get_account_balance",
            "_get_current_price",
            "_agent_learning_feedback",
        ]

        for method in required_methods:
            if method in method_names:
                print(f"   ✅ {method} exists")
            else:
                errors.append(f"Missing method: {method}")
                print(f"   ❌ {method} not found")

    except Exception as e:
        errors.append(f"Method check failed: {e}")
        print(f"   ❌ Method check failed: {e}")

    # Test 5: Check _execute_winning_strategy was updated
    print("\n5️⃣ Checking _execute_winning_strategy refactor...")
    try:
        import inspect

        from cloud_trader.trading_service import MinimalTradingService

        source = inspect.getsource(MinimalTradingService._execute_winning_strategy)

        # Look for autonomous system keywords
        autonomous_keywords = [
            "market_scanner",
            "autonomous_agents",
            "platform_router",
            "formulate_thesis",
        ]

        found_keywords = []
        for keyword in autonomous_keywords:
            if keyword in source:
                found_keywords.append(keyword)
                print(f"   ✅ Found '{keyword}' in method")

        if len(found_keywords) >= 3:
            print(
                f"   ✅ Method appears to use autonomous architecture ({len(found_keywords)}/4 keywords)"
            )
        else:
            warnings.append(
                f"_execute_winning_strategy may not be fully refactored (only {len(found_keywords)}/4 keywords)"
            )
            print(f"   ⚠️  Only found {len(found_keywords)}/4 autonomous keywords")

    except Exception as e:
        warnings.append(f"_execute_winning_strategy check failed: {e}")
        print(f"   ⚠️  Could not verify _execute_winning_strategy: {e}")

    # Final Report
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)

    if not errors and not warnings:
        print("\n✅ ALL VALIDATIONS PASSED")
        print("\nThe autonomous trading system is properly integrated and ready for testing.")
        return True
    else:
        if warnings:
            print(f"\n⚠️  {len(warnings)} WARNING(S):")
            for w in warnings:
                print(f"   - {w}")

        if errors:
            print(f"\n❌ {len(errors)} ERROR(S):")
            for e in errors:
                print(f"   - {e}")
            print("\n⛔ Fix errors before deploying.")
            return False
        else:
            print("\n✅ NO CRITICAL ERRORS (warnings are acceptable)")
            return True


if __name__ == "__main__":
    import sys

    success = validate_integration()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/sapphire/controller')

from watchlist_manager import get_watchlist_manager
from symbol_analyzer import SymbolAnalyzer
import asyncio

print("🔍 SAPPHIRE WATCHLIST ANALYZER")
print("=" * 60)
print()

# Show watchlist summary
manager = get_watchlist_manager()
summary = manager.get_watchlist_summary()

print("📊 WATCHLIST ORGANIZED:")
print("-" * 60)
print(f"Total Symbols: {summary['total_symbols']}")
print(f"  • Tradable: {summary['tradable_count']}")
print(f"  • Pair Analysis: {summary['pair_analysis_count']}")
print()

print("📈 BY CATEGORY:")
for cat, info in summary['categories'].items():
    if info['count'] > 0:
        cat_name = cat.replace('_', ' ').title()
        print(f"  {cat_name}: {info['count']} symbols")
        for sym in info['symbols']:
            profile = manager.get_symbol(sym)
            if profile:
                print(f"    • {sym}: {profile.name} (Priority: {profile.priority.name})")
print()

print("🎯 HIGH PRIORITY FOCUS:")
print("-" * 60)
for sym in summary['high_priority']:
    profile = manager.get_symbol(sym)
    if profile:
        print(f"  {sym:8} - {profile.notes[:50]}")
print()

print("✅ TRADABLE ASSETS (What You Actually Trade):")
print("-" * 60)
for sym in manager.get_tradable():
    print(f"  {sym.symbol:8} {sym.name:20} [{sym.instrument_type.upper()}]")
print()

print("📊 PAIR ANALYSIS (Charting Only):")
print("-" * 60)
for sym in manager.get_pair_analysis():
    print(f"  {sym.symbol:8} {sym.name:20}")
    print(f"    └─ Strategy: {sym.notes}")
print()

# Run analysis
print("🤖 RUNNING ANALYSIS...")
print("-" * 60)
analyzer = SymbolAnalyzer()
results = asyncio.run(analyzer.analyze_all_symbols())

print(f"✅ Analyzed {len(results)} symbols")
print()

# Show report
print(analyzer.generate_analysis_report())
print()

# Recommendations
recommendations = manager.get_recommendations()
if recommendations:
    print("💡 RECOMMENDATIONS:")
    print("-" * 60)
    for sym, rec in recommendations:
        print(f"  {sym}: {rec}")
else:
    print("✅ Watchlist looks good - no changes recommended")

print()
print("=" * 60)
print("Analysis complete! Use Telegram commands:")
print("  /watchlist - Show organized watchlist")
print("  /analyze - Run fresh analysis")
print("  /opportunities - Show trading opportunities")

#!/usr/bin/env python3
"""Compatibility launcher.

Use the updated v2 app implementation.
"""

from sapphire_commander_v2 import SapphireOperatorCompanion


if __name__ == "__main__":
    app = SapphireOperatorCompanion()
    app.run()

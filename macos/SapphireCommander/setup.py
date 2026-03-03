#!/usr/bin/env python3
"""
Setup script for packaging Sapphire Commander as macOS .app bundle
"""

from setuptools import setup

APP = ['sapphire_commander_v2.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'icon.icns',  # You can add a custom icon
    'plist': {
        'CFBundleName': 'Sapphire Commander',
        'CFBundleDisplayName': 'Sapphire Commander',
        'CFBundleIdentifier': 'com.sapphire.commander',
        'CFBundleVersion': '2.0.0',
        'CFBundleShortVersionString': '2.0.0',
        'LSUIElement': True,  # Run as menu bar app (no dock icon)
        'NSHumanReadableCopyright': '© 2026 Sapphire Inc.',
    },
    'packages': ['rumps', 'requests', 'plyer'],
    'includes': ['subprocess', 'webbrowser', 'threading', 'datetime'],
}

setup(
    name='Sapphire Commander',
    version='2.0.0',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)

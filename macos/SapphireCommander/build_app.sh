#!/bin/bash
# Build Sapphire Commander as macOS .app bundle

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Sapphire Commander v2.0 - macOS App Builder             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found"
    exit 1
fi

echo "✓ Python found: $(python3 --version)"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip3 install -q -r requirements.txt

# Build app
echo ""
echo "Building macOS app bundle..."
python3 setup.py py2app

# Check if build succeeded
if [ -d "dist/Sapphire Commander.app" ]; then
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "App location:"
    echo "  dist/Sapphire Commander.app"
    echo ""
    echo "To install:"
    echo "  1. Open Finder"
    echo "  2. Drag 'Sapphire Commander.app' to Applications folder"
    echo "  3. Double-click to launch"
    echo ""
    echo "Or run directly:"
    echo "  open 'dist/Sapphire Commander.app'"
    echo ""
    
    # Show app info
    APP_SIZE=$(du -sh "dist/Sapphire Commander.app" | cut -f1)
    echo "App size: $APP_SIZE"
else
    echo "❌ Build failed - app bundle not found"
    exit 1
fi

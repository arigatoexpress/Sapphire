#!/bin/bash
# Test Swift version compilation

echo "Sapphire Commander (Swift) - Build Test"
echo "========================================"
echo ""

# Check if Xcode is installed
if ! command -v xcodebuild &> /dev/null; then
    echo "✗ Xcode not found"
    echo "  Please install Xcode from the Mac App Store"
    exit 1
fi

echo "✓ Xcode found: $(xcodebuild -version | head -1)"

# Check if project exists
PROJECT_DIR="SapphireCommander.xcodeproj"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "✗ Project not found at $PROJECT_DIR"
    exit 1
fi

echo "✓ Project found"

# Try to build
echo ""
echo "Attempting to build..."
if xcodebuild -project "$PROJECT_DIR" -scheme SapphireCommander -destination 'platform=macOS' build > /tmp/build.log 2>&1; then
    echo "✓ Build successful"
    echo ""
    echo "To run the app:"
    echo "  open $PROJECT_DIR"
    echo "  Then click Run in Xcode"
else
    echo "✗ Build failed"
    echo ""
    echo "Build log:"
    tail -30 /tmp/build.log
    exit 1
fi

#!/bin/bash
# Build a self-contained archive for offline deployment on Raspberry Pi Zero 2W
# Run this script on a machine WITH internet access.
# The resulting .tar.gz can be transferred to the Pi via USB stick, SCP, etc.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
PACKAGE_NAME="lpc11xx-isp-flasher"

echo "========================================="
echo "Building standalone package"
echo "========================================="

# Clean previous builds
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR/$PACKAGE_NAME"
mkdir -p "$DIST_DIR"

# Copy application files
echo "Copying application files..."
cp "$SCRIPT_DIR/lpc1115_flasher.py" "$BUILD_DIR/$PACKAGE_NAME/"
cp "$SCRIPT_DIR/lpc1115_isp_enhanced.py" "$BUILD_DIR/$PACKAGE_NAME/"
cp "$SCRIPT_DIR/diagnostic.py" "$BUILD_DIR/$PACKAGE_NAME/"
cp "$SCRIPT_DIR/config.example.ini" "$BUILD_DIR/$PACKAGE_NAME/"
cp "$SCRIPT_DIR/README.md" "$BUILD_DIR/$PACKAGE_NAME/" 2>/dev/null || true

# Download wheel packages for Raspberry Pi (armv7l / aarch64)
echo ""
echo "Downloading dependencies for Raspberry Pi..."
mkdir -p "$BUILD_DIR/$PACKAGE_NAME/wheels"

# Download for both armhf (Pi Zero 2W 32-bit) and aarch64 (64-bit)
pip3 download --dest "$BUILD_DIR/$PACKAGE_NAME/wheels" \
    --platform linux_armv7l --platform linux_aarch64 --platform manylinux2014_aarch64 --platform manylinux2014_armv7l \
    --python-version 3 --no-deps \
    pyserial intelhex 2>/dev/null || \
pip3 download --dest "$BUILD_DIR/$PACKAGE_NAME/wheels" \
    --no-deps pyserial intelhex

# Create install script for offline Pi
cat > "$BUILD_DIR/$PACKAGE_NAME/install.sh" << 'EOF'
#!/bin/bash
# Offline installation script for Raspberry Pi
# Transfer this entire folder to the Pi, then run this script.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "LPC11xx ISP Flasher - Offline Install"
echo "========================================="

# Install system package for RPi.GPIO (usually pre-installed on Raspberry Pi OS)
echo "Checking RPi.GPIO..."
if ! python3 -c "import RPi.GPIO" 2>/dev/null; then
    echo "  Installing python3-rpi.gpio from system packages..."
    sudo apt-get install -y python3-rpi.gpio 2>/dev/null || true
    if ! python3 -c "import RPi.GPIO" 2>/dev/null; then
        echo "  ERROR: RPi.GPIO not available. Install manually:"
        echo "    sudo apt-get install python3-rpi.gpio"
        exit 1
    fi
fi
echo "  ✓ RPi.GPIO available"

# Install wheels
echo ""
echo "Installing Python packages from local wheels..."
pip3 install --break-system-packages --no-index --find-links "$SCRIPT_DIR/wheels" \
    pyserial intelhex 2>/dev/null || \
pip3 install --no-index --find-links "$SCRIPT_DIR/wheels" \
    pyserial intelhex

echo ""
echo "✓ Installation complete!"
echo ""
echo "Usage:"
echo "  sudo python3 $SCRIPT_DIR/lpc1115_flasher.py write firmware.hex"
echo "  sudo python3 $SCRIPT_DIR/lpc1115_flasher.py id"
echo ""
echo "Copy config.example.ini to config.ini and adjust if needed."
EOF
chmod +x "$BUILD_DIR/$PACKAGE_NAME/install.sh"

# Create the archive
echo ""
echo "Creating archive..."
cd "$BUILD_DIR"
tar -czf "$DIST_DIR/${PACKAGE_NAME}.tar.gz" "$PACKAGE_NAME"

echo ""
echo "========================================="
echo "✓ Build complete!"
echo "========================================="
echo ""
echo "Output: dist/${PACKAGE_NAME}.tar.gz"
echo ""
echo "Deploy to Raspberry Pi:"
echo "  1. Copy dist/${PACKAGE_NAME}.tar.gz to the Pi (USB, SCP, etc.)"
echo "  2. On the Pi:"
echo "     tar -xzf ${PACKAGE_NAME}.tar.gz"
echo "     cd ${PACKAGE_NAME}"
echo "     ./install.sh"

# Cleanup build dir
rm -rf "$BUILD_DIR"

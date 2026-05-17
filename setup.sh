#!/bin/bash
# Setup script for LPC1115 ISP Flasher on Raspberry Pi Zero 2W

set -e

echo "========================================="
echo "LPC1115 ISP Flasher - Setup Script"
echo "========================================="
echo ""

# Check if running on Raspberry Pi
if [ ! -f /etc/os-release ]; then
    echo "Warning: Could not detect OS"
fi

# Update package manager
echo "Updating package manager..."
sudo apt-get update

# Install system dependencies
echo ""
echo "Installing system dependencies..."
sudo apt-get install -y python3-pip python3-dev python3-rpi.gpio git

# Check UART is enabled
echo ""
echo "Checking UART configuration..."
if grep -q "enable_uart=1" /boot/firmware/config.txt 2>/dev/null || \
   grep -q "enable_uart=1" /boot/config.txt 2>/dev/null; then
    echo "  ✓ UART is enabled"
else
    echo "  ⚠ UART may not be enabled"
    echo "    To enable UART, edit /boot/firmware/config.txt (or /boot/config.txt)"
    echo "    and add or ensure this line exists:"
    echo "    enable_uart=1"
    echo ""
    echo "    Also disable the serial console login:"
    echo "    sudo raspi-config"
    echo "    → 3 Interface Options"
    echo "    → I6 Serial Port"
    echo "    → No (disable serial console)"
    echo "    → Yes (enable UART hardware)"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check device tree overlay
echo ""
echo "Checking device tree configuration..."
if grep -q "dtoverlay=disable-bt" /boot/firmware/config.txt 2>/dev/null || \
   grep -q "dtoverlay=disable-bt" /boot/config.txt 2>/dev/null; then
    echo "  ✓ Bluetooth is disabled (frees UART)"
elif grep -q "dtoverlay=miniuart-bt" /boot/firmware/config.txt 2>/dev/null || \
     grep -q "dtoverlay=miniuart-bt" /boot/config.txt 2>/dev/null; then
    echo "  ℹ Bluetooth uses miniuart (UART may still work)"
else
    echo "  ⚠ Bluetooth still uses primary UART"
    echo "    For Pi Zero 2W, disable Bluetooth or use miniuart"
    echo "    Edit /boot/firmware/config.txt (or /boot/config.txt):"
    echo "    Add: dtoverlay=disable-bt"
    echo "    OR: dtoverlay=miniuart-bt"
    echo ""
fi

# Check GPIO access permissions
echo ""
echo "Checking GPIO access permissions..."
if groups | grep -q gpio; then
    echo "  ✓ User is in gpio group"
else
    echo "  ⚠ User is not in gpio group"
    echo "    Running: sudo usermod -a -G gpio $USER"
    sudo usermod -a -G gpio $USER
    echo "    Note: You may need to log out and back in"
fi

# Install Python requirements
echo ""
echo "Installing Python requirements..."
pip3 install -r requirements.txt

echo ""
echo "========================================="
echo "Setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Verify your Raspberry Pi configuration (UART, GPIO)"
echo "  2. Connect the hardware:"
echo "     - GPIO17 (Pin 11) → ISP_Enable"
echo "     - GPIO18 (Pin 12) → Reset"
echo "     - Pin 8 (GPIO14)  → UART RX from LPC1115 (ISP_TX)"
echo "     - Pin 10 (GPIO15) → UART TX to LPC1115 (ISP_RX)"
echo "     - GND → GND"
echo "     - 3.3V → VCC (optional, if LPC not powered)"
echo ""
echo "  3. Place your Intel Hex file in the same directory"
echo ""
echo "  4. Run the flasher:"
echo "     sudo python3 lpc1115_flasher.py your_program.hex"
echo ""
echo "For more information, see README.md"

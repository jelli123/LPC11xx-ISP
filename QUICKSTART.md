# Quick Start Guide

## Prerequisites

- Raspberry Pi Zero 2W running Raspberry Pi OS
- LPC1115 microcontroller
- Appropriate wiring (see Hardware Setup section)
- Intel Hex file to flash

## Step-by-Step Setup

### 1. Hardware Connections

Connect your Raspberry Pi to LPC1115:

```
Raspberry Pi Pin    →    LPC1115 Pin
───────────────────      ────────────
Pin 11 (GPIO17)    →    ISP_Enable
Pin 12 (GPIO18)    →    Reset
Pin 8 (GPIO14)     →    ISP_RX
Pin 10 (GPIO15)    →    ISP_TX
Pin 6 or 9 (GND)   →    GND
Pin 1 or 17 (3.3V) →    VCC (optional)
```

### 2. Enable UART on Raspberry Pi

```bash
sudo raspi-config
# Go to: Interface Options → Serial Port
# Disable: "Would you like a login shell to be accessible over serial?"
# Enable: "Would you like the serial port hardware to be enabled?"
# Reboot
```

### 3. Clone or Copy Files

Copy all files to a directory on your Raspberry Pi:

```bash
mkdir ~/lpc-flasher
cd ~/lpc-flasher
# Copy all files here
```

### 4. Run Setup Script

```bash
cd ~/lpc-flasher
chmod +x setup.sh
sudo ./setup.sh
```

This will:
- Install required system packages
- Install Python dependencies
- Configure GPIO permissions
- Verify UART is enabled

### 5. Run Diagnostic (Optional but Recommended)

Test your hardware setup before flashing:

```bash
sudo python3 diagnostic.py
```

This will test:
- Python version and dependencies
- GPIO pin access
- UART communication
- ISP mode entry sequence
- Available hex files

### 6. Flash Your Program

```bash
sudo python3 lpc1115_flasher.py your_program.hex
```

Example output:
```
==================================================
LPC1115 ISP Flasher
==================================================
Hex file: blink.hex

Setting up GPIO pins...
  ✓ GPIO pins configured

Loading hex file: blink.hex
  ✓ Hex file loaded (2048 bytes)

Entering ISP mode...
  ✓ ISP mode entered

Initializing ISP connection...
  ✓ ISP connection established

Verifying chip signature...
  Part ID: 0x25001115
  ✓ LPC1115 detected

Flashing program...
  ✓ Program flashed successfully

Verifying flash...
  ✓ Flash verification passed

Resetting LPC1115...
  ✓ LPC1115 reset and running

==================================================
✓ Flashing completed successfully!
==================================================
```

## Troubleshooting

### Port Permission Denied

```bash
# Add user to groups
sudo usermod -a -G gpio $USER
sudo usermod -a -G dialout $USER

# Log out and back in, or:
newgrp gpio
newgrp dialout
```

### UART Not Found

```bash
# Check available ports
ls -la /dev/tty*

# Should see /dev/ttyAMA0 for hardware UART
```

### Serial Port Busy

```bash
# Find what's using it
sudo lsof /dev/ttyAMA0

# Stop serial console service
sudo systemctl stop serial-getty@ttyAMA0.service
sudo systemctl disable serial-getty@ttyAMA0.service
```

### Autobaud Fails

1. Check UART connections (TX/RX reversed?)
2. Verify 3.3V logic levels
3. Check LPC1115 has power
4. Verify crystal frequency (12MHz typical)

### Chip Not Detected

1. Verify ISP mode entry (GPIO17/18 toggles)
2. Check Reset pulse is long enough
3. Verify chip is powered and not held in reset
4. Try manual autobaud with diagnostic tool

## File Description

### Main Programs

- **lpc1115_flasher.py** - Main flasher program
- **lpc1115_isp_enhanced.py** - Enhanced ISP protocol implementation
- **diagnostic.py** - Hardware and connection diagnostic tool

### Configuration

- **config.example.ini** - Example configuration file
- **requirements.txt** - Python package dependencies

### Documentation

- **README.md** - Comprehensive documentation
- **QUICKSTART.md** - This file

### Setup

- **setup.sh** - Automated setup script

## Advanced Usage

### Using Custom Config File

```bash
cp config.example.ini config.ini
# Edit config.ini as needed
# Then use in your code (to be implemented)
```

### Custom GPIO Pins

Edit the pin assignments in `lpc1115_flasher.py`:

```python
RESET_PIN = 18      # Change to your GPIO pin
ISP_ENABLE_PIN = 17 # Change to your GPIO pin
```

### Different UART Port

Edit UART settings in `lpc1115_flasher.py`:

```python
UART_PORT = '/dev/ttyAMA0'  # Or /dev/ttyUSB0
UART_BAUDRATE = 115200        # Change if needed
```

## Tips & Tricks

1. **Always use sudo** when flashing (GPIO requires root)
2. **Keep wires short** for UART connections
3. **Use a logic analyzer** to debug UART issues
4. **Read LPC1115 datasheet** for more info
5. **Back up working firmware** before experimenting

## More Information

- See README.md for comprehensive documentation
- See lpc1115_isp_enhanced.py for API reference
- Check diagnostic output for specific issues

---

**Last Updated**: May 2026
**Author**: GPIO Flasher Project
**Version**: 1.0

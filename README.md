# LPC1115 ISP Flasher for Raspberry Pi Zero 2W

A Python program to flash Intel Hex files to LPC1115 microcontrollers using ISP (In-System Programming) mode via a Raspberry Pi Zero 2W.

## Features

- ✓ GPIO control for ISP enable and reset pins
- ✓ UART/Serial communication for ISP protocol
- ✓ Intel Hex file parsing and validation
- ✓ LPC1115 chip signature verification
- ✓ Automatic autobaud and synchronization
- ✓ Flash memory programming
- ✓ Flash memory verification
- ✓ Clean reset after programming

## Hardware Setup

### Required Components

- Raspberry Pi Zero 2W
- LPC1115 microcontroller
- USB-Serial adapter OR direct Raspberry Pi UART connection
- Jumper wires
- 3.3V logic level shifter (optional, if using 5V LPC1115)

### Pinout Connections

**Raspberry Pi GPIO Pinout (BCM numbering):**

```
                    |--USB--|
         GND  ---1 [|]  2 --- 5V
         GPIO2 -3 [|]  4 --- 5V
         GPIO3 -5 [|]  6 --- GND
         GPIO4 -7 [|]  8 --- GPIO14 (UART TX) → LPC1115 ISP_RX
         GND  ---9 [|] 10 --- GPIO15 (UART RX) ← LPC1115 ISP_TX
        GPIO17-11 [|] 12 --- GPIO18 (Reset)
        GPIO27-13 [|] 14 --- GND
        GPIO22-15 [|] 16 --- GPIO23
         3.3V-17 [|] 18 --- GPIO24
        GPIO10-19 [|] 20 --- GND
         GPIO9-21 [|] 22 --- GPIO25
        GPIO11-23 [|] 24 --- GPIO8
         GND  -25 [|] 26 --- GPIO7
         ID_SD-27 [|] 28 --- ID_SC
         GPIO5-29 [|] 30 --- GND
         GPIO6-31 [|] 32 --- GPIO12
        GPIO13-33 [|] 34 --- GND
        GPIO19-35 [|] 36 --- GPIO16
        GPIO26-37 [|] 38 --- GPIO20
         GND  -39 [|] 40 --- GPIO21
```

### Wiring Diagram

```
Raspberry Pi Zero 2W              LPC1115
─────────────────────              ─────

GPIO17 (Pin 11) ───────────────→ ISP_Enable (active high)
GPIO18 (Pin 12) ───────────────→ Reset_Pin (active low)
GPIO14 (Pin 8)  ───────────────→ ISP_RX (UART input)
GPIO15 (Pin 10) ←───────────────  ISP_TX (UART output)
GND   (Pin 6,9, etc) ──────────→ GND
3.3V  (Pin 1,17) ──────────────→ VCC (if needed)
```

### Important Notes

1. **Logic Levels**: Ensure all connections use 3.3V logic levels. If your LPC1115 board uses 5V:
   - Use a logic level shifter for GPIO signals
   - UART typically tolerates 3.3V on RX from 5V source

2. **Power Supply**: 
   - LPC1115 can be powered from Raspberry Pi 3.3V if current draw is low
   - For higher current, use separate 3.3V power supply

3. **Decoupling**: Add 0.1µF capacitor between VCC and GND near LPC1115

4. **Pull-up resistors**: Some designs may need 10kΩ pull-ups on GPIO17 and GPIO18

## Installation

### 1. Prerequisites

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade

# Enable UART (if not already enabled)
sudo raspi-config
# Interface Options → Serial Port → Enable UART (disable console)
```

### 2. Run Setup Script

```bash
chmod +x setup.sh
sudo ./setup.sh
```

This will:
- Install Python 3 and required libraries
- Configure GPIO permissions
- Verify UART settings
- Install Python dependencies

### 3. Manual Installation (Alternative)

```bash
# Install system packages
sudo apt-get install -y python3-pip python3-rpi.gpio

# Install Python packages
pip3 install -r requirements.txt
```

## Usage

### Basic Usage

```bash
sudo python3 lpc1115_flasher.py your_program.hex
```

### With Verbose Output

```bash
sudo python3 lpc1115_flasher.py your_program.hex -v
```

### Example Session

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
  1. Setting ISP_Enable (GPIO17) HIGH
  2. Setting Reset (GPIO18) HIGH
  3. Setting Reset (GPIO18) LOW
  4. Setting ISP_Enable (GPIO17) LOW
  5. Setting Reset (GPIO18) HIGH
  ✓ ISP mode entered

Initializing ISP connection...
  Performing autobaud synchronization...
    ✓ Autobaud successful
  ✓ ISP connection established

Verifying chip signature...
  Reading Part ID...
  Part ID: 0x25001115
  ✓ LPC1115 detected

Flashing program...
  Found 1 flash segment(s)
    Flashing 0x0000 - 0x0800 (2048 bytes)
      Data size: 2048 bytes
  ✓ Program flashed successfully

Verifying flash...
  ✓ Flash verification passed

Resetting LPC1115...
  1. Setting Reset (GPIO18) HIGH
  2. Setting Reset (GPIO18) LOW
  3. Setting Reset (GPIO18) HIGH
  ✓ LPC1115 reset and running

==================================================
✓ Flashing completed successfully!
==================================================
```

## ISP Protocol Implementation

### Autobaud Sequence

The LPC1115 bootloader supports autobaud detection. The sequence is:

1. Power on with ISP mode enabled
2. Send autobaud character ('?') at 115200 baud
3. Bootloader measures bit timing and synchronizes
4. Send empty command (0x0D) to verify synchronization

### Command Format

ISP commands follow this format:
```
<COMMAND> [PARAMETERS] 0D
```

- Commands are hex strings (e.g., "54" for Read Part ID)
- Parameters are space-separated hex values
- Each command ends with 0D (carriage return)

### Common Commands

- **54 0D** - Read Part ID (returns 4 bytes)
- **5A 01 00 00 0D** - Read Unique ID (returns 16 bytes)
- **52 <start> <end> 0D** - Erase Sectors
- **57 <addr> <length> 0D** - Write to RAM
- **50 <flash_addr> <ram_addr> <len> 0D** - Copy RAM to Flash
- **56 <addr> <length> 0D** - Read from RAM

## Troubleshooting

### "Error: RPi.GPIO not installed"

```bash
sudo apt-get install python3-rpi.gpio
# OR
pip3 install RPi.GPIO
```

### "Error: intelhex not installed"

```bash
pip3 install intelhex
```

### "Error opening serial port: [Errno 16] Device or resource busy"

The serial port is already in use. Check:
```bash
# Find what's using the port
sudo lsof /dev/ttyAMA0

# If serial console is running
sudo systemctl disable serial-getty@ttyAMA0.service
sudo systemctl stop serial-getty@ttyAMA0.service
```

### Autobaud fails / "Synchronization failed"

1. **Check UART pins**: Verify GPIO14/15 connections
2. **Check voltage**: Ensure 3.3V logic levels
3. **Check baud rate**: Should be 115200 by default
4. **Check ISP mode**: Verify GPIO17/18 control
5. **Check crystal**: LPC1115 needs accurate clock for autobaud

### No response from LPC1115

1. **Verify power**: Check LPC1115 is powered and has stable 3.3V
2. **Check reset sequence**: Verify GPIO18 transitions
3. **Check ISP enable**: Verify GPIO17 is LOW during operation
4. **Oscilloscope**: Check UART signals on GPIO14/15
5. **Check firmware**: Some LPC1115 variants need different init

### Flash verification failed

1. **Verify connections**: Check all wires are secure
2. **Check timing**: Some LPC1115 variants need longer delays
3. **Check flash content**: Verify hex file is valid
4. **Erase before flash**: Some sectors may need pre-erase

## Advanced Configuration

### Custom UART Port

Edit `lpc1115_flasher.py` and modify:
```python
UART_PORT = '/dev/ttyAMA0'  # Or /dev/ttyUSB0 for USB adapter
```

### Different Baud Rates

```python
UART_BAUDRATE = 115200  # Change to desired rate
```

### Custom GPIO Pins

Edit `lpc1115_flasher.py`:
```python
RESET_PIN = 18      # Your GPIO pin for reset
ISP_ENABLE_PIN = 17 # Your GPIO pin for ISP enable
```

## References

- [LPC1115 User Manual](https://www.nxp.com/docs/en/user-manual/UM10398.pdf)
- [Raspberry Pi GPIO Documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
- [ISP Protocol Details](https://www.nxp.com/docs/en/user-manual/UM10398.pdf) - Section on ISP

## Notes

### ISP Mode Entry Sequence

The ISP mode entry sequence implemented follows the LPC1100 user manual:

```
Initial State (Running Normal Code):
  ISP_Enable = 0 (LOW)
  Reset = 1 (HIGH)

Entry Sequence:
  1. Set ISP_Enable = 1 (HIGH)  ← Prepare for ISP mode
  2. Set Reset = 1 (HIGH)        ← Hold in reset
  3. Set Reset = 0 (LOW)         ← Apply reset pulse
  4. Set ISP_Enable = 0 (LOW)    ← Bootloader checks ISP_Enable
  5. Set Reset = 1 (HIGH)        ← Release reset, start bootloader
  
Bootloader Running:
  Waits for autobaud on UART
```

### ISP Exit and Normal Operation

```
Exit Sequence:
  1. Set Reset = 1 (HIGH)  ← Prepare for reset
  2. Set Reset = 0 (LOW)   ← Apply reset pulse
  3. Set Reset = 1 (HIGH)  ← Release reset, run user code
  
ISP_Enable = X (don't care, bootloader not running)
```

## Performance

Typical flashing times for 32KB LPC1115:

- Erase: ~100ms
- Write: ~500ms (data dependent)
- Verify: ~200ms
- Total: ~800ms-1s (excluding GPIO/ISP overhead)

## Limitations

Current implementation:

- Supports basic flash programming
- Does not yet support option bytes programming
- Does not yet support CRC verification
- Assumes contiguous flash segments

These features can be added as needed.

## License

This software is provided as-is for hardware development purposes.

## Support

For issues or questions:
1. Check troubleshooting section
2. Verify hardware connections
3. Check LPC1115 datasheet
4. Add debug output in the code
5. Capture UART traffic with oscilloscope/logic analyzer

---

**Last Updated**: May 2026
**Target Hardware**: Raspberry Pi Zero 2W + LPC1115
**Python Version**: 3.7+

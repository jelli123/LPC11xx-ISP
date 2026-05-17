# LPC11xx ISP Flasher for Raspberry Pi Zero 2W

A Python tool to program LPC11xx microcontrollers via UART ISP mode using a Raspberry Pi Zero 2W.

## Supported Chips

All LPC11xx family members are supported, including:

| Chip | Flash | RAM | Variants |
|------|-------|-----|----------|
| LPC1110 | 4 KB | 1 KB | /002 |
| LPC1111 | 8 KB | 2–4 KB | /002, /101–/103, /201–/203 |
| LPC1112 | 16 KB | 2–4 KB | /101–/103, /201–/203 |
| LPC1113 | 24 KB | 4–8 KB | /201–/203, /301–/303 |
| LPC1114 | 32 KB | 4–8 KB | /102, /201–/203, /301–/303, /323, /333 |
| LPC1115 | 64 KB | 8 KB | /303 |
| LPC11C12 | 16 KB | 8 KB | /301 (CAN) |
| LPC11C14 | 32 KB | 8 KB | /301 (CAN) |
| LPC11C22 | 16 KB | 8 KB | /301 (CAN) |
| LPC11C24 | 32 KB | 8 KB | /301 (CAN) |

Flash size and RAM size are auto-detected from the Part ID.

## Features

- **write** — Write Intel Hex file to flash (with optional verification)
- **read** — Read flash contents into Intel Hex file
- **verify** — Compare flash contents with Intel Hex file
- **erase** — Erase flash sectors (all or specific range)
- **blankcheck** — Check if flash sectors are blank
- **id** — Read Part ID (with name resolution), UID, boot code version
- Automatic chip detection and parameter configuration
- Configuration file support (`config.ini`)

## Hardware Setup

### Required Components

- Raspberry Pi Zero 2W
- LPC11xx microcontroller board
- Inverter circuit on RESET and ISP_Enable lines (see below)
- Jumper wires
- 3.3V power supply

### GPIO Inverter Circuit

**Why inverters are needed:** After a Raspberry Pi reset, all GPIOs default to input mode with pull-down resistors (LOW). Without inverters, this would drive /RESET LOW (holding the chip in reset) and PIO0_1 LOW (forcing ISP mode). The inverters ensure the LPC11xx is in a safe state (running, normal boot) when the Raspberry Pi is not actively driving the GPIOs.

```
Signal flow:

  RasPi GPIO → Inverter → LPC11xx pin

  GPIO LOW  (default after reset) → Inv → HIGH → safe state
  GPIO HIGH (active)              → Inv → LOW  → active function

  GPIO17 (ISP_EN):  HIGH → Inv → PIO0_1 LOW  = ISP mode requested
                    LOW  → Inv → PIO0_1 HIGH = normal boot

  GPIO18 (RESET):   HIGH → Inv → /RESET LOW  = chip in reset
                    LOW  → Inv → /RESET HIGH = chip running
```

A simple inverter can be built with an NPN transistor and two resistors per channel, or a 74HC04 hex inverter IC.

### Wiring Diagram

```
Raspberry Pi Zero 2W              Inverter        LPC11xx
─────────────────────              ────────        ───────

GPIO17 (Pin 11) ──────→ Inverter ──────→ PIO0_1 (ISP entry pin)
GPIO18 (Pin 12) ──────→ Inverter ──────→ /RESET
GPIO14 (Pin  8) ───────────────────────→ RXD (UART input)
GPIO15 (Pin 10) ←──────────────────────  TXD (UART output)
GND    (Pin  6) ───────────────────────→ GND
3.3V   (Pin 17) ───────────────────────→ VCC (if needed)
```

### Pinout Connections

**Raspberry Pi GPIO Pinout (BCM numbering):**

```
                    |--USB--|
         GND  ---1 [|]  2 --- 5V
         GPIO2 -3 [|]  4 --- 5V
         GPIO3 -5 [|]  6 --- GND
         GPIO4 -7 [|]  8 --- GPIO14 (UART TX) → LPC11xx RXD
         GND  ---9 [|] 10 --- GPIO15 (UART RX) ← LPC11xx TXD
        GPIO17-11 [|] 12 --- GPIO18 (Reset via Inv)
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

### Important Notes

1. **Logic Levels**: All signals are 3.3V. If your LPC11xx board uses 5V logic, add a level shifter.

2. **Power Supply**: LPC11xx can be powered from the Raspberry Pi 3.3V pin if current draw is low (< 100mA). For higher current, use a separate 3.3V supply.

3. **Decoupling**: Add 100nF capacitor between VCC and GND near the LPC11xx.

## Installation

### Using Setup Script

```bash
chmod +x setup.sh
sudo ./setup.sh
```

### Manual Installation

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-rpi.gpio

# Enable UART
sudo raspi-config
# Interface Options → Serial Port → Disable login shell, Enable hardware

pip3 install -r requirements.txt
```

## Usage

### Command Line Interface

```
sudo python3 lpc1115_flasher.py [options] <operation> [operation-args]
```

### Global Options

| Option | Description |
|--------|-------------|
| `-v`, `--verbose` | Verbose output |
| `-c FILE`, `--config FILE` | Configuration file (default: `config.ini` in script directory) |

### Operations

#### `write` — Write Intel Hex file to flash

```bash
sudo python3 lpc1115_flasher.py write firmware.hex
sudo python3 lpc1115_flasher.py write firmware.hex --no-verify
```

| Argument | Description |
|----------|-------------|
| `hex_file` | Intel Hex file to write |
| `--no-verify` | Skip verification after writing |

#### `read` — Read flash into Intel Hex file

```bash
sudo python3 lpc1115_flasher.py read readback.hex
sudo python3 lpc1115_flasher.py read readback.hex --start 0x1000 --length 4096
```

| Argument | Description |
|----------|-------------|
| `hex_file` | Output Intel Hex file |
| `--start ADDR` | Start address (hex or decimal, default: 0) |
| `--length N` | Bytes to read (default: full flash) |

#### `verify` — Compare flash with Intel Hex file

```bash
sudo python3 lpc1115_flasher.py verify firmware.hex
```

| Argument | Description |
|----------|-------------|
| `hex_file` | Intel Hex file to compare against |

#### `erase` — Erase flash sectors

```bash
sudo python3 lpc1115_flasher.py erase
sudo python3 lpc1115_flasher.py erase --start-sector 0 --end-sector 3
```

| Argument | Description |
|----------|-------------|
| `--start-sector N` | First sector to erase (default: 0) |
| `--end-sector N` | Last sector to erase (default: last sector) |

#### `blankcheck` — Check if flash is blank

```bash
sudo python3 lpc1115_flasher.py blankcheck
sudo python3 lpc1115_flasher.py blankcheck --start-sector 0 --end-sector 3
```

| Argument | Description |
|----------|-------------|
| `--start-sector N` | First sector to check (default: 0) |
| `--end-sector N` | Last sector to check (default: last sector) |

#### `id` — Read chip identification

```bash
sudo python3 lpc1115_flasher.py id
```

Displays Part ID with chip name, flash/RAM size, UID, and boot code version.

### Configuration File

If `config.ini` exists in the script directory, it is loaded automatically. Use `--config` to specify a different file.

```bash
cp config.example.ini config.ini
# Edit config.ini for your setup
sudo python3 lpc1115_flasher.py --config myconfig.ini write firmware.hex
```

**Configuration parameters:**

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `[hardware]` | `reset_pin` | `18` | GPIO pin for Reset (BCM) |
| `[hardware]` | `isp_enable_pin` | `17` | GPIO pin for ISP Enable (BCM) |
| `[hardware]` | `uart_port` | `/dev/ttyAMA0` | Serial port device |
| `[hardware]` | `uart_baudrate` | `115200` | UART baud rate |
| `[hardware]` | `crystal_freq_khz` | `12000` | Target crystal frequency in kHz |
| `[debug]` | `verbose` | `false` | Enable verbose output |

Flash size and RAM size are auto-detected from the chip Part ID and do not need to be configured.

### Example Session

```
$ sudo python3 lpc1115_flasher.py write blink.hex
==================================================
LPC11xx ISP Flasher
==================================================

Entering ISP mode...
  1. ISP_Enable HIGH → PIO0_1 LOW (ISP request)
  2. Reset HIGH → /RESET LOW (assert reset)
  3. Reset LOW → /RESET HIGH (release reset, enter ISP)
  ✓ ISP mode entered

Synchronizing with bootloader...
  ✓ Synchronized

Detecting chip...
  Part ID:  0x00040040
  Chip:     LPC1114.../303
  Flash:    32 KB (8 sectors)
  RAM:      8 KB

Loading hex file: blink.hex
  Address range: 0x00000000 - 0x000007FF
  Size: 2048 bytes

Unlocking flash (Command: U)...
Erasing sectors 0-0 (Commands: P + E)...
  ✓ Erased

Programming 1 segment(s)...
  0x00000000 - 0x000007FF (2048 bytes)
  ✓ Programming complete

Verifying (Command: M)...
  ✓ Verified

==================================================
✓ Write completed successfully!
==================================================

Resetting to normal operation...
  ✓ LPC11xx reset and running user code
```

## ISP Protocol

### Synchronization (UM10398, Section 26.4.1)

```
Host sends:      ?
Device responds: Synchronized\r\n
Host sends:      Synchronized\r\n
Device responds: OK\r\n
Host sends:      12000\r\n           (crystal freq in kHz)
Device responds: OK\r\n
```

### Command Format

ISP commands are **single ASCII letters** followed by decimal parameters:
```
<LETTER> [param1] [param2] [...]\r\n
```

### ISP Commands (UM10398, Chapter 26)

| Command | Letter | Parameters | Description |
|---------|--------|-----------|-------------|
| Unlock | `U` | `<code>` | Unlock flash (code=23130) |
| Set Baud Rate | `B` | `<baud> <stop>` | Change baud rate |
| Echo | `A` | `<0\|1>` | Disable/enable echo |
| Write to RAM | `W` | `<addr> <len>` | Write data to RAM (UU-encoded) |
| Read Memory | `R` | `<addr> <len>` | Read from memory (UU-encoded) |
| Prepare Sectors | `P` | `<start> <end>` | Prepare sectors for write/erase |
| Copy RAM to Flash | `C` | `<dst> <src> <len>` | Program flash from RAM |
| Go | `G` | `<addr> <mode>` | Execute code (mode: T=Thumb) |
| Erase | `E` | `<start> <end>` | Erase sector(s) |
| Blank Check | `I` | `<start> <end>` | Check if sectors are blank |
| Read Part ID | `J` | (none) | Read chip identification |
| Read Boot Version | `K` | (none) | Read boot code version |
| Compare | `M` | `<addr1> <addr2> <len>` | Compare memory regions |
| Read UID | `N` | (none) | Read unique serial number |

### ISP Mode Entry Sequence

The LPC11xx enters ISP mode when PIO0_1 is LOW at reset release. GPIO signals pass through inverters:

```
                     GPIO    Inverter   LPC11xx
                     ─────   ────────   ───────
ISP_Enable:          HIGH  →  LOW    → PIO0_1 LOW  (ISP mode)
Reset assert:        HIGH  →  LOW    → /RESET LOW  (in reset)
Reset release:       LOW   →  HIGH   → /RESET HIGH (running)
                     
Sequence:
  1. ISP_Enable = HIGH  → PIO0_1 = LOW (request ISP)
  2. Reset = HIGH        → /RESET = LOW (assert reset)
  3. Wait 100ms
  4. Reset = LOW         → /RESET = HIGH (release, boot into ISP)
```

## Troubleshooting

### Synchronization failed

1. Check UART wiring (GPIO14 TX → LPC RXD, GPIO15 RX ← LPC TXD)
2. Verify 3.3V logic levels
3. Confirm inverters are working (scope the /RESET and PIO0_1 signals)
4. Check crystal frequency setting matches target board
5. Expected bootloader response: `Synchronized` text string

### No response from LPC11xx

1. Verify LPC11xx has stable 3.3V power
2. Check inverters: GPIO HIGH must produce LPC pin LOW
3. Verify PIO0_1 is LOW when /RESET goes HIGH
4. Check UART signals with oscilloscope/logic analyzer

### "Device or resource busy"

```bash
sudo systemctl stop serial-getty@ttyAMA0.service
sudo systemctl disable serial-getty@ttyAMA0.service
```

### Permission denied

```bash
sudo usermod -a -G gpio,dialout $USER
# Log out and back in
```

## Diagnostic Tool

Test your hardware setup before flashing:

```bash
sudo python3 diagnostic.py
```

Tests Python version, dependencies, GPIO access, UART communication, ISP mode entry, and available hex files.

## References

- [LPC11xx User Manual (UM10398)](https://www.nxp.com/docs/en/user-manual/UM10398.pdf) — ISP protocol in Chapter 26
- [Raspberry Pi GPIO Documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)

## License

This software is provided as-is for hardware development purposes.

---

**Last Updated**: May 2026
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

GPIO17 (Pin 11) ───────────────→ ISP_Enable (active high → pulls PIO0_1 LOW)
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
  1. Activating ISP_Enable (GPIO17 HIGH)
  2. Asserting Reset (GPIO18 LOW)
  3. Releasing Reset (GPIO18 HIGH)
  ✓ ISP mode entered

Initializing ISP connection...
  Synchronizing with bootloader...
  ✓ Synchronization successful

Verifying chip...
  Part ID: 0x00040044
  ✓ Detected: LPC1115/302

Flashing program...
  Found 1 flash segment(s)
    Flashing 0x0000 - 0x0800 (2048 bytes)
      Data size: 2048 bytes
  ✓ Program flashed successfully

Verifying flash...
  ✓ Flash verification passed

Resetting LPC1115 to normal operation...
  1. Deactivating ISP_Enable (GPIO17 LOW)
  2. Asserting Reset (GPIO18 LOW)
  3. Releasing Reset (GPIO18 HIGH)
  ✓ LPC1115 reset and running user code

==================================================
✓ Flashing completed successfully!
==================================================
```

## ISP Protocol Implementation

### Synchronization Sequence (UM10398, Section 26.4.1)

The LPC1115 bootloader uses a text-based synchronization handshake:

1. Host sends `?` character (autobaud detection)
2. Bootloader responds: `Synchronized\r\n`
3. Host echoes: `Synchronized\r\n`
4. Bootloader responds: `Synchronized\r\nOK\r\n`
5. Host sends crystal frequency in kHz: `12000\r\n`
6. Bootloader responds: `12000\r\nOK\r\n`

### Command Format

ISP commands are **single ASCII letters** followed by decimal parameters, terminated with `\r\n`:
```
<LETTER> [param1] [param2] [...]\r\n
```

Responses consist of a numeric return code (0 = success) followed by optional data, all as ASCII text terminated with `\r\n`.

### ISP Commands (UM10398, Chapter 26)

| Command | Letter | Parameters | Description |
|---------|--------|-----------|-------------|
| Unlock | `U` | `<code>` | Unlock flash (code=23130) |
| Set Baud Rate | `B` | `<baud> <stop>` | Change baud rate |
| Echo | `A` | `<0\|1>` | Disable/enable echo |
| Write to RAM | `W` | `<addr> <len>` | Write data to RAM (UU-encoded) |
| Read Memory | `R` | `<addr> <len>` | Read from memory (UU-encoded) |
| Prepare Sectors | `P` | `<start> <end>` | Prepare sectors for write/erase |
| Copy RAM to Flash | `C` | `<dst> <src> <len>` | Program flash from RAM |
| Go | `G` | `<addr> <mode>` | Execute code (mode: T=Thumb) |
| Erase | `E` | `<start> <end>` | Erase sector(s) |
| Blank Check | `I` | `<start> <end>` | Check if sectors are blank |
| Read Part ID | `J` | (none) | Read chip identification |
| Read Boot Version | `K` | (none) | Read boot code version |
| Compare | `M` | `<addr1> <addr2> <len>` | Compare memory regions |
| Read UID | `N` | (none) | Read unique serial number |

### Example: Read Part ID

```
Host sends:    J\r\n
Device responds: 0\r\n       (return code: success)
                 625344048\r\n (part ID as decimal)
```

### Example: Erase Sector 0

```
Host sends:    U 23130\r\n   (unlock)
Device responds: 0\r\n       (success)
Host sends:    P 0 0\r\n     (prepare sector 0)
Device responds: 0\r\n       (success)
Host sends:    E 0 0\r\n     (erase sector 0)
Device responds: 0\r\n       (success)
```

### Data Transfer (UU-Encoding)

Write (W) and Read (R) commands use UU-encoding for data transfer:
- Data is sent in lines of up to 45 raw bytes (60 encoded characters)
- Every 20 lines, a checksum line (sum of raw bytes) is sent
- Receiver responds with "OK" or "RESEND"

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
4. **Check ISP mode**: Verify GPIO17 is HIGH during reset release (PIO0_1 LOW)
5. **Check crystal**: LPC1115 needs accurate clock for autobaud
6. **Expected response**: Bootloader should respond with "Synchronized" text

### No response from LPC1115

1. **Verify power**: Check LPC1115 is powered and has stable 3.3V
2. **Check reset sequence**: GPIO18 must go LOW→HIGH with ISP_Enable active
3. **Check ISP enable**: GPIO17 must be HIGH before reset release
4. **Oscilloscope**: Check UART signals on GPIO14/15
5. **Check PIO0_1**: Verify pin is pulled LOW at reset release

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

The ISP mode entry sequence follows the LPC11xx user manual:
PIO0_1 must be LOW when RESET is released to enter ISP mode.

Hardware assumption: GPIO17 HIGH = PIO0_1 pulled LOW (via inverter/transistor).

```
Initial State (Running Normal Code):
  ISP_Enable = 0 (LOW)  → PIO0_1 = HIGH (normal boot)
  Reset = 1 (HIGH)       → Chip running

Entry Sequence:
  1. Set ISP_Enable = 1 (HIGH)  ← PIO0_1 pulled LOW
  2. Set Reset = 0 (LOW)         ← Assert reset
  3. Wait 100ms                  ← Hold reset
  4. Set Reset = 1 (HIGH)        ← Release reset, PIO0_1 sampled LOW
                                    → Bootloader starts

Bootloader Running:
  Waits for '?' autobaud character on UART
  Then performs synchronization handshake
```

### ISP Exit and Normal Operation

```
Exit Sequence:
  1. Set ISP_Enable = 0 (LOW)  ← PIO0_1 = HIGH (normal boot)
  2. Set Reset = 0 (LOW)        ← Assert reset
  3. Wait 100ms                 ← Hold reset
  4. Set Reset = 1 (HIGH)       ← Release reset, run user code
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

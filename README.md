# LPC11xx ISP Flasher for Raspberry Pi Zero 2W

Programs LPC11xx microcontrollers via UART ISP mode using a Raspberry Pi.

## Supported Chips

LPC1110, LPC1111, LPC1112, LPC1113, LPC1114, **LPC1115**, LPC11C12, LPC11C14, LPC11C22, LPC11C24. Flash/RAM size auto-detected from Part ID.

## Hardware Wiring

```
Raspberry Pi              Inverter        LPC11xx
────────────              ────────        ───────
GPIO17 (Pin 11) ──→ Inverter ──→ PIO0_1 (ISP entry)
GPIO18 (Pin 12) ──→ Inverter ──→ /RESET
GPIO14 (Pin  8) ────────────────→ RXD (UART input)
GPIO15 (Pin 10) ←───────────────  TXD (UART output)
GND    (Pin  6) ────────────────→ GND
3.3V   (Pin 17) ────────────────→ VCC (optional)
```

**Inverters are required** because after a Raspberry Pi reset, GPIOs default to LOW (input with pull-down). Inverters convert this to HIGH on the LPC side — ensuring /RESET=HIGH (running) and PIO0_1=HIGH (normal boot) as safe default. A 74HC04 or NPN transistor per channel works.

If you connect directly without inverters, set `invert_reset = false` and `invert_isp_enable = false` in `config.ini`.

## Quick Start

```bash
# 1. Enable UART (one-time)
sudo raspi-config   # Interface → Serial → Disable console, Enable hardware

# 2. Setup
chmod +x setup.sh
sudo ./setup.sh

# 3. Allow GPIO/serial access without sudo (one-time, then re-login)
sudo usermod -a -G gpio,dialout $USER

# 4. Verify hardware
python3 diagnostic.py

# 5. Flash
python3 lpc1115_flasher.py write firmware.hex
```

> **Hinweis:** `sudo` ist nur nötig, wenn der Benutzer nicht in den Gruppen `gpio` und `dialout` ist. Nach `usermod` + Re-Login funktioniert alles ohne `sudo`.

## Usage

```bash
python3 lpc1115_flasher.py [options] <operation> [args]
```

### Options

| Option | Description |
|--------|-------------|
| `-v` | Verbose output (includes serial hex dump) |
| `-c FILE` | Configuration file (default: config.ini) |

### Operations

```bash
# Write hex file (with automatic verify)
python3 lpc1115_flasher.py write firmware.hex
python3 lpc1115_flasher.py write firmware.hex --no-verify

# Read flash
python3 lpc1115_flasher.py read readback.hex
python3 lpc1115_flasher.py read readback.hex --start 0x1000 --length 4096

# Verify flash against file
python3 lpc1115_flasher.py verify firmware.hex

# Erase flash
python3 lpc1115_flasher.py erase
python3 lpc1115_flasher.py erase --start-sector 0 --end-sector 3

# Blank check
python3 lpc1115_flasher.py blankcheck

# Chip info
python3 lpc1115_flasher.py id
```

## Configuration

Copy `config.example.ini` to `config.ini` and adjust:

```ini
[hardware]
reset_pin = 18
isp_enable_pin = 17
uart_port = /dev/ttyAMA0
uart_baudrate = 115200
crystal_freq_khz = 12000
invert_reset = true
invert_isp_enable = true
```

## Offline Deployment

The Raspberry Pi has no internet access. Build a self-contained package on a machine with internet:

```bash
chmod +x build_standalone.sh
./build_standalone.sh
```

Transfer `dist/lpc11xx-isp-flasher.tar.gz` to the Pi (USB stick, SCP), then:

```bash
tar -xzf lpc11xx-isp-flasher.tar.gz
cd lpc11xx-isp-flasher
./install.sh
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Port in use by knxd/getty | `sudo fuser /dev/ttyAMA0` → stop conflicting service |
| No response from LPC | Check TX/RX wiring, 3.3V power, crystal |
| Sync fails (garbled response) | Try `uart_baudrate = 57600` in config.ini |
| Permission denied | `sudo usermod -a -G gpio,dialout $USER` |
| Serial console active | `sudo raspi-config` → Serial → disable console |

## Files

| File | Description |
|------|-------------|
| `lpc1115_flasher.py` | Main flasher (CLI) |
| `lpc1115_isp_enhanced.py` | ISP protocol library |
| `diagnostic.py` | Hardware diagnostic tool |
| `config.example.ini` | Configuration template |
| `setup.sh` | Installation script |
| `build_standalone.sh` | Offline package builder |

## References

- [LPC11xx User Manual UM10398](https://www.nxp.com/docs/en/user-manual/UM10398.pdf) — ISP protocol in Chapter 26

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

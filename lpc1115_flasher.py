#!/usr/bin/env python3
"""
LPC11xx ISP Flasher for Raspberry Pi Zero 2W
Programs LPC11xx microcontrollers via UART ISP mode.

ISP Protocol based on LPC11xx User Manual (UM10398), Chapter 26.
Commands are single ASCII letters (J, P, E, C, W, R, G, U, N, etc.)
with text-based communication terminated by CR LF.

Supported operations:
  write      - Write Intel Hex file to flash
  read       - Read flash contents into Intel Hex file
  verify     - Compare flash contents with Intel Hex file
  erase      - Erase flash (all sectors or range)
  blankcheck - Check if flash sectors are blank
  id         - Read Part ID and UID

GPIO signals go through inverters before reaching the LPC11xx:
  GPIO HIGH → Inverter → LPC pin LOW
  GPIO LOW  → Inverter → LPC pin HIGH (pull-up)

This is required because the Raspberry Pi configures all GPIOs as
inputs with pull-down after reset, which would otherwise hold the
LPC11xx in reset (/RESET LOW) and ISP mode (PIO0_1 LOW).
"""

import sys
import time
import serial
import argparse
import configparser
import os
from pathlib import Path
from typing import Tuple, List, Optional

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("Error: RPi.GPIO not installed. Install with: sudo apt-get install python3-rpi.gpio")
    sys.exit(1)

try:
    from intelhex import IntelHex
except ImportError:
    print("Error: intelhex not installed. Install with: pip3 install intelhex")
    sys.exit(1)

from lpc1115_isp_enhanced import EnhancedISPProtocol, FlashMemoryManager, ISPReturnCodes


class LPC11xxFlasher:
    """Main LPC11xx Flasher class"""

    # Default GPIO pin assignments
    # Both signals go through an inverter on the PCB:
    #   RESET_PIN:      GPIO HIGH → Inverter → /RESET LOW  (chip in reset)
    #                   GPIO LOW  → Inverter → /RESET HIGH (chip running)
    #   ISP_ENABLE_PIN: GPIO HIGH → Inverter → PIO0_1 LOW  (ISP mode)
    #                   GPIO LOW  → Inverter → PIO0_1 HIGH (normal boot)
    #
    # After Raspberry Pi reset, GPIOs default to INPUT with pull-down (LOW),
    # so inverter outputs are HIGH → /RESET=HIGH, PIO0_1=HIGH → safe state.
    DEFAULT_RESET_PIN = 18
    DEFAULT_ISP_ENABLE_PIN = 17

    # Default UART settings
    DEFAULT_UART_PORT = '/dev/ttyAMA0'
    DEFAULT_UART_BAUDRATE = 115200

    # Default crystal frequency in kHz
    DEFAULT_CRYSTAL_FREQ_KHZ = 12000

    def __init__(self, verbose: bool = False, config_file: Optional[str] = None):
        """Initialize LPC11xx Flasher"""
        self.verbose = verbose
        self.serial_port = None
        self.isp = None
        self.flash_mgr = None
        self.detected_part_id = None
        self.flash_size = 0
        self.ram_size = 0
        self.num_sectors = 0

        # Load defaults, then override from config.ini if present
        self.reset_pin = self.DEFAULT_RESET_PIN
        self.isp_enable_pin = self.DEFAULT_ISP_ENABLE_PIN
        self.uart_port = self.DEFAULT_UART_PORT
        self.uart_baudrate = self.DEFAULT_UART_BAUDRATE
        self.crystal_freq_khz = self.DEFAULT_CRYSTAL_FREQ_KHZ

        # GPIO inversion flags (True = signal passes through inverter)
        self.invert_reset = True
        self.invert_isp_enable = True

        self._load_config(config_file)

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

    def _load_config(self, config_file: Optional[str] = None):
        """Load configuration from config.ini if it exists."""
        if config_file is None:
            # Look for config.ini in same directory as script
            script_dir = Path(__file__).parent
            config_file = str(script_dir / 'config.ini')

        if not os.path.exists(config_file):
            if self.verbose:
                print(f"  No config.ini found, using defaults")
            return

        print(f"  Loading configuration from {config_file}")
        config = configparser.ConfigParser()
        config.read(config_file)

        if config.has_section('hardware'):
            self.reset_pin = config.getint('hardware', 'reset_pin', fallback=self.reset_pin)
            self.isp_enable_pin = config.getint('hardware', 'isp_enable_pin', fallback=self.isp_enable_pin)
            self.uart_port = config.get('hardware', 'uart_port', fallback=self.uart_port)
            self.uart_baudrate = config.getint('hardware', 'uart_baudrate', fallback=self.uart_baudrate)
            self.invert_reset = config.getboolean('hardware', 'invert_reset', fallback=self.invert_reset)
            self.invert_isp_enable = config.getboolean('hardware', 'invert_isp_enable', fallback=self.invert_isp_enable)

        if config.has_section('timing'):
            self.crystal_freq_khz = config.getint('hardware', 'crystal_freq_khz',
                                                   fallback=self.crystal_freq_khz) if config.has_option('hardware', 'crystal_freq_khz') else self.crystal_freq_khz

        if config.has_section('debug'):
            if not self.verbose:
                self.verbose = config.getboolean('debug', 'verbose', fallback=False)

    def _reset_active(self) -> int:
        """GPIO level to assert /RESET (chip in reset)"""
        return GPIO.HIGH if self.invert_reset else GPIO.LOW

    def _reset_inactive(self) -> int:
        """GPIO level to release /RESET (chip running)"""
        return GPIO.LOW if self.invert_reset else GPIO.HIGH

    def _isp_active(self) -> int:
        """GPIO level to request ISP mode (PIO0_1 LOW on LPC)"""
        return GPIO.HIGH if self.invert_isp_enable else GPIO.LOW

    def _isp_inactive(self) -> int:
        """GPIO level for normal boot (PIO0_1 HIGH on LPC)"""
        return GPIO.LOW if self.invert_isp_enable else GPIO.HIGH

    def setup_gpio(self) -> bool:
        """Setup GPIO pins for ISP control.

        Initial state: /RESET released (chip running), PIO0_1 HIGH (normal boot).
        """
        if self.verbose:
            print("Setting up GPIO pins...")
        try:
            GPIO.setup(self.reset_pin, GPIO.OUT, initial=self._reset_inactive())
            GPIO.setup(self.isp_enable_pin, GPIO.OUT, initial=self._isp_inactive())
            if self.verbose:
                inv_str = "(inverted)" if self.invert_reset else "(direct)"
                isp_inv_str = "(inverted)" if self.invert_isp_enable else "(direct)"
                print(f"  ✓ GPIO pins configured")
                print(f"    Reset (GPIO{self.reset_pin}): /RESET HIGH - running {inv_str}")
                print(f"    ISP_Enable (GPIO{self.isp_enable_pin}): PIO0_1 HIGH - normal {isp_inv_str}")
            return True
        except Exception as e:
            print(f"  ✗ GPIO setup failed: {e}")
            return False

    def enter_isp_mode(self) -> bool:
        """
        Enter ISP mode on LPC11xx.

        The LPC11xx enters ISP mode when PIO0_1 is LOW at reset release.
        ISP_Enable remains active (PIO0_1 held LOW) throughout the entire
        ISP session to ensure stable operation. It is released only in
        exit_isp_mode().

        Sequence:
          1. ISP_Enable active  → PIO0_1 LOW (request ISP)
          2. Reset active       → /RESET LOW (assert reset)
          3. Reset inactive     → /RESET HIGH (release reset)
             Chip samples PIO0_1=LOW → boots into ISP bootloader
          4. Wait for bootloader init (~500ms)
        """
        print("\nEntering ISP mode...")

        try:
            # Step 1: Request ISP mode (PIO0_1 LOW on LPC)
            print("  1. ISP_Enable → PIO0_1 LOW (ISP request)")
            GPIO.output(self.isp_enable_pin, self._isp_active())
            time.sleep(0.01)

            # Step 2: Assert reset (/RESET LOW on LPC)
            print("  2. Reset → /RESET LOW (assert reset)")
            GPIO.output(self.reset_pin, self._reset_active())
            time.sleep(0.1)

            # Step 3: Release reset (/RESET HIGH on LPC)
            #         Chip samples PIO0_1=LOW → enters ISP bootloader
            print("  3. Reset → /RESET HIGH (release reset, enter ISP)")
            GPIO.output(self.reset_pin, self._reset_inactive())

            # Step 4: Wait for bootloader to initialize UART
            print("  4. Waiting for bootloader init...")
            time.sleep(0.5)

            print("  ✓ ISP mode entered (ISP_Enable held active)")
            return True

        except Exception as e:
            print(f"  ✗ Failed to enter ISP mode: {e}")
            return False

    def reset_target(self) -> bool:
        """
        Reset LPC11xx (assert and release /RESET).
        Used to restart the ISP handshake or boot user code.

        After reset, PIO0_1 state determines boot mode:
          PIO0_1 LOW  at reset release → ISP bootloader
          PIO0_1 HIGH at reset release → user code
        """
        try:
            GPIO.output(self.reset_pin, self._reset_active())
            time.sleep(0.1)
            GPIO.output(self.reset_pin, self._reset_inactive())
            time.sleep(0.2)
            return True
        except Exception as e:
            print(f"  ✗ Reset failed: {e}")
            return False

    def exit_isp_mode(self) -> bool:
        """
        Exit ISP mode and reset LPC11xx into normal operation.

        Sequence:
          1. ISP_Enable inactive → PIO0_1 HIGH (normal boot)
          2. Assert reset
          3. Release reset → boots user code
        """
        print("\nResetting to normal operation...")

        try:
            # Step 1: Ensure ISP disabled (PIO0_1 HIGH on LPC)
            GPIO.output(self.isp_enable_pin, self._isp_inactive())
            time.sleep(0.01)

            # Step 2+3: Reset cycle
            self.reset_target()

            print("  ✓ LPC11xx reset and running user code")
            return True

        except Exception as e:
            print(f"  ✗ Reset failed: {e}")
            return False

    def open_serial(self) -> bool:
        """Open serial port for ISP communication.

        Opens WITHOUT XON/XOFF initially — the sync handshake must complete
        without flow control. XON/XOFF is enabled after synchronization
        for the data transfer phase (UU-encoding).
        """
        if self.verbose:
            print(f"\nOpening serial port {self.uart_port} @ {self.uart_baudrate}...")
        try:
            self.serial_port = serial.Serial(
                port=self.uart_port,
                baudrate=self.uart_baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            time.sleep(0.1)
            if self.verbose:
                print(f"  ✓ Serial port opened")
            return True
        except Exception as e:
            print(f"  ✗ Failed to open serial port: {e}")
            return False

    def close_serial(self):
        """Close serial port"""
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None

    def _re_enter_isp(self):
        """Re-enter ISP mode silently (for sync retries).
        Asserts ISP_Enable, resets, releases. ISP_Enable stays active.
        """
        GPIO.output(self.isp_enable_pin, self._isp_active())
        time.sleep(0.01)
        GPIO.output(self.reset_pin, self._reset_active())
        time.sleep(0.1)
        GPIO.output(self.reset_pin, self._reset_inactive())
        time.sleep(0.5)

    def synchronize(self) -> bool:
        """Perform ISP synchronization handshake."""
        print("\nSynchronizing with bootloader...")

        self.isp = EnhancedISPProtocol(self.serial_port, self.crystal_freq_khz, verbose=self.verbose)

        for attempt in range(3):
            if attempt > 0:
                print(f"  Retry {attempt + 1}/3...")
                # Re-enter ISP mode fully (ISP_Enable + reset cycle)
                self._re_enter_isp()
                time.sleep(0.1)
                # Clear serial buffers after reset
                self.serial_port.reset_input_buffer()
                self.serial_port.reset_output_buffer()

            if self.isp.synchronize():
                # Enable XON/XOFF for data transfer phase after successful sync
                self.serial_port.xonxoff = True
                print("  ✓ Synchronized")
                return True

        print("  ✗ Synchronization failed")
        print("    No response from bootloader. Check:")
        print(f"    - Is {self.uart_port} the correct port? (Pi Zero 2W: try /dev/ttyS0)")
        print("    - Are UART TX/RX connected correctly? (TX→RX, RX→TX)")
        print("    - Is LPC11xx powered and has a working crystal?")
        print("    - Run 'sudo python3 diagnostic.py' for detailed checks")
        return False

    def detect_chip(self) -> bool:
        """Detect chip by reading Part ID (Command: J)."""
        print("\nDetecting chip...")

        part_id = self.isp.read_part_id()
        if part_id is None:
            print("  ✗ Failed to read Part ID")
            return False

        self.detected_part_id = part_id
        info = EnhancedISPProtocol.lookup_part(part_id)

        if info:
            name, flash_kb, ram_kb = info
            self.flash_size = flash_kb * 1024
            self.ram_size = ram_kb * 1024
            self.num_sectors = self.flash_size // EnhancedISPProtocol.FLASH_SECTOR_SIZE
            print(f"  Part ID:  0x{part_id:08X}")
            print(f"  Chip:     {name}")
            print(f"  Flash:    {flash_kb} KB ({self.num_sectors} sectors)")
            print(f"  RAM:      {ram_kb} KB")
        else:
            # Use defaults for unknown chip
            self.flash_size, self.ram_size, self.num_sectors = \
                EnhancedISPProtocol.get_chip_params(part_id)
            print(f"  Part ID:  0x{part_id:08X}")
            print(f"  ⚠ Unknown chip, using defaults ({self.flash_size // 1024}KB Flash)")

        return True

    def _init_connection(self) -> bool:
        """Common initialization: GPIO, serial, sync, chip detect."""
        if not self.setup_gpio():
            return False
        if not self.enter_isp_mode():
            return False
        if not self.open_serial():
            return False
        # Clear any garbage received during reset/boot sequence
        self.serial_port.reset_input_buffer()
        self.serial_port.reset_output_buffer()
        if not self.synchronize():
            self.close_serial()
            return False
        if not self.detect_chip():
            self.close_serial()
            return False
        return True

    def _cleanup(self, reset: bool = True):
        """Close serial, reset chip, cleanup GPIO.

        Always performs a reset to ensure the ISP handshake can restart
        on next invocation. The 'reset' parameter controls whether to
        boot into user code (True) or re-enter ISP (False, still resets).
        """
        self.close_serial()
        if reset:
            self.exit_isp_mode()
        else:
            # Even without full exit, always reset the target so the
            # bootloader is in a clean state for the next handshake.
            self.reset_target()
        try:
            GPIO.cleanup()
        except Exception:
            pass

    # ── Operation: Read Chip ID and UID ──────────────────────────────

    def cmd_id(self) -> bool:
        """Read and display Part ID, UID, and boot code version."""
        try:
            if not self._init_connection():
                return False

            # Part ID was already read during detect_chip

            # Read UID
            print("\nReading UID (Command: N)...")
            uid = self.isp.read_uid()
            if uid:
                print(f"  UID: {uid[0]:08X}-{uid[1]:08X}-{uid[2]:08X}-{uid[3]:08X}")
            else:
                print("  ⚠ Could not read UID")

            # Read boot code version
            print("\nReading Boot Code Version (Command: K)...")
            version = self.isp.read_boot_code_version()
            if version:
                print(f"  Boot Code: {version[0]}.{version[1]}")
            else:
                print("  ⚠ Could not read boot code version")

            print("\n✓ Done")
            return True

        finally:
            self._cleanup(reset=False)

    # ── Operation: Write HEX file to flash ───────────────────────────

    def cmd_write(self, hex_file: str, no_verify: bool = False) -> bool:
        """Write Intel Hex file to flash."""
        try:
            if not self._init_connection():
                return False

            # Load hex file
            print(f"\nLoading hex file: {hex_file}")
            hex_data = IntelHex(hex_file)
            min_addr = hex_data.minaddr()
            max_addr = hex_data.maxaddr()
            size = max_addr - min_addr + 1
            print(f"  Address range: 0x{min_addr:08X} - 0x{max_addr:08X}")
            print(f"  Size: {size} bytes")

            if max_addr >= self.flash_size:
                print(f"  ✗ Data exceeds flash size ({self.flash_size // 1024} KB)")
                return False

            flash_mgr = FlashMemoryManager(self.isp,
                                           flash_size=self.flash_size,
                                           ram_size=self.ram_size)

            # Determine sectors
            start_sector = min_addr // EnhancedISPProtocol.FLASH_SECTOR_SIZE
            end_sector = max_addr // EnhancedISPProtocol.FLASH_SECTOR_SIZE

            # Unlock
            print("\nUnlocking flash (Command: U)...")
            if not self.isp.unlock():
                print("  ✗ Failed to unlock")
                return False

            # Erase
            print(f"Erasing sectors {start_sector}-{end_sector} (Commands: P + E)...")
            if not flash_mgr.erase_sectors(start_sector, end_sector):
                print("  ✗ Erase failed")
                return False
            print("  ✓ Erased")

            # Program
            segments = hex_data.segments()
            print(f"\nProgramming {len(segments)} segment(s)...")
            for seg_start, seg_end in segments:
                data = bytes(hex_data[seg_start:seg_end])
                print(f"  0x{seg_start:08X} - 0x{seg_end:08X} ({len(data)} bytes)")
                if not flash_mgr.write_flash_data(seg_start, data):
                    print(f"  ✗ Programming failed at 0x{seg_start:08X}")
                    return False
            print("  ✓ Programming complete")

            # Verify
            if not no_verify:
                print("\nVerifying (Command: M)...")
                for seg_start, seg_end in segments:
                    data = bytes(hex_data[seg_start:seg_end])
                    if not flash_mgr.verify_flash_data(seg_start, data):
                        print(f"  ✗ Verification failed")
                        return False
                print("  ✓ Verified")

            print("\n" + "=" * 50)
            print("✓ Write completed successfully!")
            print("=" * 50)
            return True

        except Exception as e:
            print(f"\n✗ Write failed: {e}")
            return False
        finally:
            self._cleanup()

    # ── Operation: Read flash into HEX file ──────────────────────────

    def cmd_read(self, hex_file: str, start: int = 0, length: Optional[int] = None) -> bool:
        """Read flash contents and save as Intel Hex file."""
        try:
            if not self._init_connection():
                return False

            if length is None:
                length = self.flash_size - start

            print(f"\nReading flash: 0x{start:08X} - 0x{start + length - 1:08X} ({length} bytes)")

            # Read in chunks (max ~256 bytes per read due to UU-encoding overhead)
            chunk_size = 256
            hex_data = IntelHex()
            bytes_read = 0

            for offset in range(0, length, chunk_size):
                addr = start + offset
                remaining = min(chunk_size, length - offset)
                # Align to 4 bytes
                read_len = ((remaining + 3) // 4) * 4

                data = self.isp.read_memory(addr, read_len)
                if data is None:
                    print(f"  ✗ Read failed at 0x{addr:08X}")
                    return False

                for i in range(remaining):
                    hex_data[addr + i] = data[i]

                bytes_read += remaining
                if self.verbose:
                    print(f"  Read 0x{addr:08X} ({remaining} bytes)")

            # Save to file
            print(f"\nSaving to {hex_file}...")
            hex_data.write_hex_file(hex_file)

            print(f"\n✓ Read {bytes_read} bytes to {hex_file}")
            return True

        except Exception as e:
            print(f"\n✗ Read failed: {e}")
            return False
        finally:
            self._cleanup(reset=False)

    # ── Operation: Verify flash against HEX file ─────────────────────

    def cmd_verify(self, hex_file: str) -> bool:
        """Compare flash contents with Intel Hex file."""
        try:
            if not self._init_connection():
                return False

            print(f"\nLoading hex file: {hex_file}")
            hex_data = IntelHex(hex_file)

            flash_mgr = FlashMemoryManager(self.isp,
                                           flash_size=self.flash_size,
                                           ram_size=self.ram_size)

            segments = hex_data.segments()
            print(f"Verifying {len(segments)} segment(s)...")

            for seg_start, seg_end in segments:
                data = bytes(hex_data[seg_start:seg_end])
                if not flash_mgr.verify_flash_data(seg_start, data):
                    print(f"\n✗ Verification FAILED")
                    return False

            print(f"\n✓ Flash matches hex file")
            return True

        except Exception as e:
            print(f"\n✗ Verify failed: {e}")
            return False
        finally:
            self._cleanup(reset=False)

    # ── Operation: Erase flash ───────────────────────────────────────

    def cmd_erase(self, start_sector: int = 0, end_sector: Optional[int] = None) -> bool:
        """Erase flash sectors."""
        try:
            if not self._init_connection():
                return False

            if end_sector is None:
                end_sector = self.num_sectors - 1

            flash_mgr = FlashMemoryManager(self.isp,
                                           flash_size=self.flash_size,
                                           ram_size=self.ram_size)

            print(f"\nErasing sectors {start_sector} to {end_sector}...")
            if not flash_mgr.erase_sectors(start_sector, end_sector):
                print("  ✗ Erase failed")
                return False

            print(f"\n✓ Sectors {start_sector}-{end_sector} erased")
            return True

        except Exception as e:
            print(f"\n✗ Erase failed: {e}")
            return False
        finally:
            self._cleanup(reset=False)

    # ── Operation: Blank check ───────────────────────────────────────

    def cmd_blankcheck(self, start_sector: int = 0, end_sector: Optional[int] = None) -> bool:
        """Check if flash sectors are blank."""
        try:
            if not self._init_connection():
                return False

            if end_sector is None:
                end_sector = self.num_sectors - 1

            print(f"\nBlank checking sectors {start_sector} to {end_sector} (Command: I)...")
            is_blank, offset = self.isp.blank_check_sectors(start_sector, end_sector)

            if is_blank:
                print(f"\n✓ Sectors {start_sector}-{end_sector} are blank")
            else:
                print(f"\n✗ Not blank — first non-blank offset: {offset}")

            return is_blank

        except Exception as e:
            print(f"\n✗ Blank check failed: {e}")
            return False
        finally:
            self._cleanup(reset=False)

    def __del__(self):
        try:
            GPIO.cleanup()
        except Exception:
            pass


def main():
    """Main entry point with subcommands"""
    parser = argparse.ArgumentParser(
        description='LPC11xx ISP Flasher for Raspberry Pi Zero 2W',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
operations:
  write       Write Intel Hex file to flash
  read        Read flash contents into Intel Hex file
  verify      Compare flash contents with Intel Hex file
  erase       Erase flash sectors
  blankcheck  Check if flash sectors are blank
  id          Read Part ID, UID, and boot code version

examples:
  %(prog)s write firmware.hex
  %(prog)s write firmware.hex --no-verify
  %(prog)s read readback.hex
  %(prog)s read readback.hex --start 0x0000 --length 4096
  %(prog)s verify firmware.hex
  %(prog)s erase
  %(prog)s erase --start-sector 0 --end-sector 3
  %(prog)s blankcheck
  %(prog)s id
  %(prog)s --config myconfig.ini write firmware.hex
"""
    )

    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')
    parser.add_argument('-c', '--config', metavar='FILE',
                        help='Configuration file (default: config.ini)')

    subparsers = parser.add_subparsers(dest='operation', help='Operation to perform')

    # write
    p_write = subparsers.add_parser('write', help='Write Intel Hex file to flash')
    p_write.add_argument('hex_file', help='Intel Hex file to write')
    p_write.add_argument('--no-verify', action='store_true',
                         help='Skip verification after writing')

    # read
    p_read = subparsers.add_parser('read', help='Read flash into Intel Hex file')
    p_read.add_argument('hex_file', help='Output Intel Hex file')
    p_read.add_argument('--start', type=lambda x: int(x, 0), default=0,
                        help='Start address (default: 0x0000)')
    p_read.add_argument('--length', type=lambda x: int(x, 0), default=None,
                        help='Number of bytes to read (default: full flash)')

    # verify
    p_verify = subparsers.add_parser('verify', help='Compare flash with Intel Hex file')
    p_verify.add_argument('hex_file', help='Intel Hex file to compare')

    # erase
    p_erase = subparsers.add_parser('erase', help='Erase flash sectors')
    p_erase.add_argument('--start-sector', type=int, default=0,
                         help='First sector to erase (default: 0)')
    p_erase.add_argument('--end-sector', type=int, default=None,
                         help='Last sector to erase (default: last sector)')

    # blankcheck
    p_blank = subparsers.add_parser('blankcheck', help='Check if flash is blank')
    p_blank.add_argument('--start-sector', type=int, default=0,
                         help='First sector to check (default: 0)')
    p_blank.add_argument('--end-sector', type=int, default=None,
                         help='Last sector to check (default: last sector)')

    # id
    subparsers.add_parser('id', help='Read Part ID, UID, boot code version')

    args = parser.parse_args()

    if not args.operation:
        parser.print_help()
        sys.exit(1)

    print("=" * 50)
    print("LPC11xx ISP Flasher")
    print("=" * 50)

    flasher = LPC11xxFlasher(verbose=args.verbose, config_file=args.config)

    if args.operation == 'write':
        if not os.path.exists(args.hex_file):
            print(f"Error: File not found: {args.hex_file}")
            sys.exit(1)
        success = flasher.cmd_write(args.hex_file, no_verify=args.no_verify)

    elif args.operation == 'read':
        success = flasher.cmd_read(args.hex_file, start=args.start, length=args.length)

    elif args.operation == 'verify':
        if not os.path.exists(args.hex_file):
            print(f"Error: File not found: {args.hex_file}")
            sys.exit(1)
        success = flasher.cmd_verify(args.hex_file)

    elif args.operation == 'erase':
        success = flasher.cmd_erase(start_sector=args.start_sector,
                                    end_sector=args.end_sector)

    elif args.operation == 'blankcheck':
        success = flasher.cmd_blankcheck(start_sector=args.start_sector,
                                         end_sector=args.end_sector)

    elif args.operation == 'id':
        success = flasher.cmd_id()

    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

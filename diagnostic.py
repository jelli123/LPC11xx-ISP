#!/usr/bin/env python3
"""
LPC11xx ISP Diagnostic Tool
Tests hardware connections and ISP communication without flashing.

Supports both inverted (through hardware inverter) and direct GPIO connections.
Configure via config.ini (see config.example.ini).
"""

import sys
import time
import serial
import argparse
import configparser
import os
from pathlib import Path

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("Error: RPi.GPIO not installed")
    sys.exit(1)


class DiagnosticTool:
    """Diagnostic tool for LPC11xx flashing setup"""

    RESET_PIN = 18
    ISP_ENABLE_PIN = 17

    UART_PORT = '/dev/ttyAMA0'
    UART_BAUDRATE = 115200

    def __init__(self):
        self.ser = None
        self.errors = 0
        self.warnings = 0

        # GPIO inversion flags (default: inverted)
        self.invert_reset = True
        self.invert_isp_enable = True

        self._load_config()

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

    def _load_config(self):
        """Load configuration from config.ini if present."""
        script_dir = Path(__file__).parent
        config_file = script_dir / 'config.ini'
        if not config_file.exists():
            return

        config = configparser.ConfigParser()
        config.read(str(config_file))

        if config.has_section('hardware'):
            self.RESET_PIN = config.getint('hardware', 'reset_pin', fallback=self.RESET_PIN)
            self.ISP_ENABLE_PIN = config.getint('hardware', 'isp_enable_pin', fallback=self.ISP_ENABLE_PIN)
            self.UART_PORT = config.get('hardware', 'uart_port', fallback=self.UART_PORT)
            self.UART_BAUDRATE = config.getint('hardware', 'uart_baudrate', fallback=self.UART_BAUDRATE)
            self.invert_reset = config.getboolean('hardware', 'invert_reset', fallback=self.invert_reset)
            self.invert_isp_enable = config.getboolean('hardware', 'invert_isp_enable', fallback=self.invert_isp_enable)

    def _reset_active(self) -> int:
        return GPIO.HIGH if self.invert_reset else GPIO.LOW

    def _reset_inactive(self) -> int:
        return GPIO.LOW if self.invert_reset else GPIO.HIGH

    def _isp_active(self) -> int:
        return GPIO.HIGH if self.invert_isp_enable else GPIO.LOW

    def _isp_inactive(self) -> int:
        return GPIO.LOW if self.invert_isp_enable else GPIO.HIGH
    
    def log_info(self, msg: str):
        print(f"ℹ  {msg}")
    
    def log_ok(self, msg: str):
        print(f"✓  {msg}")
    
    def log_warn(self, msg: str):
        print(f"⚠  {msg}")
        self.warnings += 1
    
    def log_error(self, msg: str):
        print(f"✗  {msg}")
        self.errors += 1
    
    def test_python_version(self):
        """Test Python version"""
        print("\n[1] Python Version")
        print("-" * 50)
        
        version = sys.version_info
        if version.major >= 3 and version.minor >= 7:
            self.log_ok(f"Python {version.major}.{version.minor}.{version.micro}")
        else:
            self.log_error(f"Python 3.7+ required, got {version.major}.{version.minor}")
    
    def test_dependencies(self):
        """Test required Python packages"""
        print("\n[2] Python Dependencies")
        print("-" * 50)
        
        packages = {
            'serial': 'pyserial',
            'intelhex': 'intelhex',
            'RPi.GPIO': 'RPi.GPIO',
        }
        
        for module, package in packages.items():
            try:
                __import__(module)
                self.log_ok(f"{package} installed")
            except ImportError:
                self.log_error(f"{package} not installed")
                self.log_info(f"Install with: pip3 install {package}")
    
    def test_gpio(self):
        """Test GPIO pins"""
        print("\n[3] GPIO Pin Access")
        print("-" * 50)
        if self.invert_reset or self.invert_isp_enable:
            self.log_info("GPIO signals go through inverters to LPC11xx")
            self.log_info("GPIO HIGH → Inv → LPC pin LOW")
        else:
            self.log_info("GPIO signals connected directly to LPC11xx")

        try:
            # Test Reset pin
            GPIO.setup(self.RESET_PIN, GPIO.OUT)
            GPIO.output(self.RESET_PIN, self._reset_active())
            state = GPIO.input(self.RESET_PIN)
            expected = self._reset_active()
            if state == expected:
                inv_str = " → Inv → /RESET LOW" if self.invert_reset else " → /RESET LOW"
                self.log_ok(f"GPIO{self.RESET_PIN} (Reset) working{inv_str}")
            else:
                self.log_warn(f"GPIO{self.RESET_PIN} may have issues (reads: {state})")

            # Test ISP_Enable pin
            GPIO.setup(self.ISP_ENABLE_PIN, GPIO.OUT)
            GPIO.output(self.ISP_ENABLE_PIN, self._isp_active())
            state = GPIO.input(self.ISP_ENABLE_PIN)
            expected = self._isp_active()
            if state == expected:
                inv_str = " → Inv → PIO0_1 LOW" if self.invert_isp_enable else " → PIO0_1 LOW"
                self.log_ok(f"GPIO{self.ISP_ENABLE_PIN} (ISP_Enable) working{inv_str}")
            else:
                self.log_warn(f"GPIO{self.ISP_ENABLE_PIN} may have issues (reads: {state})")

            # Reset to safe state (chip running, normal boot)
            GPIO.output(self.RESET_PIN, self._reset_inactive())
            GPIO.output(self.ISP_ENABLE_PIN, self._isp_inactive())

        except Exception as e:
            self.log_error(f"GPIO test failed: {e}")
            self.log_info("Make sure you're running with 'sudo'")
    
    def test_uart(self):
        """Test UART connection"""
        print("\n[4] UART/Serial Port")
        print("-" * 50)
        
        # Check if port exists
        port_path = Path(self.UART_PORT)
        if port_path.exists():
            self.log_ok(f"Port {self.UART_PORT} exists")
        else:
            self.log_error(f"Port {self.UART_PORT} not found")
            self.log_info("Check with: ls -la /dev/tty*")
            return
        
        # Try to open port
        try:
            self.ser = serial.Serial(
                port=self.UART_PORT,
                baudrate=self.UART_BAUDRATE,
                timeout=1.0,
                xonxoff=True,   # XON/XOFF flow control (DC1/DC3)
                rtscts=False,
                dsrdtr=False
            )
            self.log_ok(f"Serial port opened at {self.UART_BAUDRATE} baud")
            
            # Test communication (if we're already in ISP mode)
            self.log_info("Attempting ISP autobaud synchronization...")
            
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            # Send autobaud character '?' — bootloader responds with "Synchronized\r\n"
            self.ser.write(b'?')
            self.ser.flush()
            
            time.sleep(0.3)
            response = self.ser.readline().decode('ascii', errors='ignore').strip()
            
            if response == "Synchronized":
                self.log_ok("ISP bootloader responded — LPC11xx is in ISP mode!")
            elif response:
                self.log_warn(f"Got response '{response}' (expected 'Synchronized')")
                self.log_info("LPC11xx may not be in ISP mode")
            else:
                self.log_warn("No response from bootloader")
                self.log_info("LPC11xx may not be in ISP mode yet")
                self.log_info("Try: sudo python3 lpc1115_flasher.py <hex_file>")
            
            self.ser.close()
            
        except serial.SerialException as e:
            self.log_error(f"Failed to open serial port: {e}")
            self.log_info("Check permissions: ls -la /dev/ttyAMA0")
            self.log_info("Add user to group: sudo usermod -a -G dialout $USER")
        except Exception as e:
            self.log_error(f"Serial test failed: {e}")
    
    def test_isp_mode_sequence(self):
        """Test ISP mode entry sequence"""
        print("\n[5] ISP Mode Sequence")
        print("-" * 50)

        try:
            self.log_info("Testing ISP mode entry sequence...")
            self.log_info("(No actual flashing will occur)")
            if self.invert_reset:
                self.log_info("Reset: inverted (GPIO HIGH → /RESET LOW)")
            else:
                self.log_info("Reset: direct (GPIO LOW → /RESET LOW)")
            if self.invert_isp_enable:
                self.log_info("ISP_Enable: inverted (GPIO HIGH → PIO0_1 LOW)")
            else:
                self.log_info("ISP_Enable: direct (GPIO LOW → PIO0_1 LOW)")

            # Step 1: ISP_Enable active → PIO0_1 LOW
            print("  Step 1: ISP_Enable → PIO0_1 LOW (request ISP)")
            GPIO.output(self.ISP_ENABLE_PIN, self._isp_active())
            time.sleep(0.05)
            if GPIO.input(self.ISP_ENABLE_PIN) == self._isp_active():
                print("    ✓ ISP_Enable active")
            else:
                print("    ✗ ISP_Enable not at expected level")

            # Step 2: Reset active → /RESET LOW
            print("  Step 2: Reset → /RESET LOW (assert reset)")
            GPIO.output(self.RESET_PIN, self._reset_active())
            time.sleep(0.1)
            if GPIO.input(self.RESET_PIN) == self._reset_active():
                print("    ✓ Reset asserted")
            else:
                print("    ✗ Reset not at expected level")

            # Step 3: Reset inactive → /RESET HIGH (enter ISP)
            print("  Step 3: Reset → /RESET HIGH (release, enter ISP)")
            GPIO.output(self.RESET_PIN, self._reset_inactive())
            time.sleep(0.5)
            if GPIO.input(self.RESET_PIN) == self._reset_inactive():
                print("    ✓ Reset released (bootloader starting)")
            else:
                print("    ✗ Reset not at expected level")

            self.log_ok("ISP mode sequence completed (ISP_Enable held active)")

            # Check UART after entering ISP mode
            print("\n  Checking UART communication after ISP entry...")
            try:
                ser = serial.Serial(
                    self.UART_PORT,
                    self.UART_BAUDRATE,
                    timeout=3.0
                )

                time.sleep(0.1)
                ser.reset_input_buffer()
                ser.reset_output_buffer()

                # ISP synchronization: send '?' and expect "Synchronized"
                ser.write(b'?')
                ser.flush()

                response = ser.readline().decode('ascii', errors='ignore').strip()
                if response == "Synchronized":
                    self.log_ok("ISP synchronization successful!")
                    self.log_ok("Bootloader responded with 'Synchronized'")
                    self.log_info("Full sync requires: echo 'Synchronized', then crystal freq")
                elif response:
                    self.log_warn(f"Unexpected response: '{response}'")
                    self.log_info("Expected 'Synchronized' from bootloader")
                else:
                    self.log_warn("No response on UART after '?' autobaud character")
                    self.log_info("Check:")
                    self.log_info("  - UART TX/RX connections")
                    self.log_info("  - LPC1115 power supply")
                    self.log_info("  - Logic levels (3.3V)")

                ser.close()

            except Exception as e:
                self.log_warn(f"Could not test UART: {e}")

        except Exception as e:
            self.log_error(f"ISP sequence test failed: {e}")
        finally:
            # Reset to safe state: normal boot
            try:
                GPIO.output(self.ISP_ENABLE_PIN, self._isp_inactive())
                GPIO.output(self.RESET_PIN, self._reset_active())
                time.sleep(0.1)
                GPIO.output(self.RESET_PIN, self._reset_inactive())
            except:
                pass
    
    def test_hex_files(self):
        """Check for hex files in current directory"""
        print("\n[6] Available Hex Files")
        print("-" * 50)
        
        hex_files = list(Path('.').glob('*.hex'))
        
        if hex_files:
            self.log_ok(f"Found {len(hex_files)} hex file(s)")
            for hex_file in hex_files:
                try:
                    from intelhex import IntelHex
                    hex_data = IntelHex(str(hex_file))
                    print(f"  - {hex_file.name} ({len(hex_data)} bytes)")
                except Exception as e:
                    print(f"  - {hex_file.name} (ERROR: {e})")
        else:
            self.log_warn("No hex files found in current directory")
            self.log_info("Place your Intel Hex file here to flash")
    
    def summary(self):
        """Print summary"""
        print("\n" + "=" * 50)
        print("Summary")
        print("=" * 50)
        
        if self.errors == 0 and self.warnings == 0:
            self.log_ok("All tests passed! Ready to flash.")
            print("\nTo flash:")
            print("  sudo python3 lpc1115_flasher.py your_program.hex")
        elif self.errors == 0:
            self.log_ok(f"Setup mostly working ({self.warnings} warning(s))")
            print("\nFlashing may still work, but check the warnings above.")
        else:
            self.log_error(f"Setup has issues ({self.errors} error(s))")
            print("\nFix the errors above before attempting to flash.")
    
    def run(self):
        """Run all tests"""
        print("=" * 50)
        print("LPC11xx ISP Diagnostic Tool")
        print("=" * 50)
        
        self.test_python_version()
        self.test_dependencies()
        self.test_gpio()
        self.test_uart()
        self.test_isp_mode_sequence()
        self.test_hex_files()
        self.summary()
        
        # Cleanup
        try:
            GPIO.cleanup()
        except:
            pass
        
        return 0 if self.errors == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description='LPC11xx ISP Diagnostic Tool'
    )
    
    args = parser.parse_args()
    
    tool = DiagnosticTool()
    return tool.run()


if __name__ == '__main__':
    sys.exit(main())

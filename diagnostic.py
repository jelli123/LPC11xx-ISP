#!/usr/bin/env python3
"""
LPC1115 ISP Diagnostic Tool
Tests hardware connections and ISP communication without flashing
"""

import sys
import time
import serial
import argparse
from pathlib import Path

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("Error: RPi.GPIO not installed")
    sys.exit(1)


class DiagnosticTool:
    """Diagnostic tool for LPC1115 flashing setup"""
    
    RESET_PIN = 18
    ISP_ENABLE_PIN = 17
    
    UART_PORT = '/dev/ttyAMA0'
    UART_BAUDRATE = 115200
    
    def __init__(self):
        self.ser = None
        self.errors = 0
        self.warnings = 0
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
    
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
        
        try:
            # Test Reset pin
            GPIO.setup(self.RESET_PIN, GPIO.OUT)
            GPIO.output(self.RESET_PIN, GPIO.LOW)
            state = GPIO.input(self.RESET_PIN)
            if state == GPIO.LOW:
                self.log_ok(f"GPIO18 (Reset) working")
            else:
                self.log_warn(f"GPIO18 may have issues (reads: {state})")
            
            # Test ISP_Enable pin
            GPIO.setup(self.ISP_ENABLE_PIN, GPIO.OUT)
            GPIO.output(self.ISP_ENABLE_PIN, GPIO.HIGH)
            state = GPIO.input(self.ISP_ENABLE_PIN)
            if state == GPIO.HIGH:
                self.log_ok(f"GPIO17 (ISP_Enable) working")
            else:
                self.log_warn(f"GPIO17 may have issues (reads: {state})")
            
            # Reset to safe state
            GPIO.output(self.RESET_PIN, GPIO.HIGH)
            GPIO.output(self.ISP_ENABLE_PIN, GPIO.LOW)
            
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
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            self.log_ok(f"Serial port opened at {self.UART_BAUDRATE} baud")
            
            # Test communication (if we're already in ISP mode)
            self.log_info("Attempting autobaud...")
            
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            # Send autobaud character
            self.ser.write(b'?')
            self.ser.flush()
            
            time.sleep(0.2)
            response = self.ser.read(1)
            
            if response == b'?':
                self.log_ok("Autobaud successful - LPC1115 is in ISP mode!")
            else:
                self.log_warn("No autobaud response")
                self.log_info("LPC1115 may not be in ISP mode yet")
                self.log_info("Try: python3 lpc1115_flasher.py <hex_file>")
            
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
            
            # Test sequence
            print("  Step 1: Set ISP_Enable (GPIO17) HIGH")
            GPIO.output(self.ISP_ENABLE_PIN, GPIO.HIGH)
            time.sleep(0.05)
            if GPIO.input(self.ISP_ENABLE_PIN) == GPIO.HIGH:
                print("    ✓ GPIO17 set to HIGH")
            else:
                print("    ✗ GPIO17 read as LOW (unexpected)")
            
            print("  Step 2: Set Reset (GPIO18) HIGH")
            GPIO.output(self.RESET_PIN, GPIO.HIGH)
            time.sleep(0.05)
            if GPIO.input(self.RESET_PIN) == GPIO.HIGH:
                print("    ✓ GPIO18 set to HIGH")
            else:
                print("    ✗ GPIO18 read as LOW (unexpected)")
            
            print("  Step 3: Set Reset (GPIO18) LOW")
            GPIO.output(self.RESET_PIN, GPIO.LOW)
            time.sleep(0.1)
            if GPIO.input(self.RESET_PIN) == GPIO.LOW:
                print("    ✓ GPIO18 set to LOW")
            else:
                print("    ✗ GPIO18 read as HIGH (unexpected)")
            
            print("  Step 4: Set ISP_Enable (GPIO17) LOW")
            GPIO.output(self.ISP_ENABLE_PIN, GPIO.LOW)
            time.sleep(0.1)
            if GPIO.input(self.ISP_ENABLE_PIN) == GPIO.LOW:
                print("    ✓ GPIO17 set to LOW")
            else:
                print("    ✗ GPIO17 read as HIGH (unexpected)")
            
            print("  Step 5: Set Reset (GPIO18) HIGH")
            GPIO.output(self.RESET_PIN, GPIO.HIGH)
            time.sleep(0.2)
            if GPIO.input(self.RESET_PIN) == GPIO.HIGH:
                print("    ✓ GPIO18 set to HIGH")
            else:
                print("    ✗ GPIO18 read as LOW (unexpected)")
            
            self.log_ok("ISP mode sequence completed")
            
            # Check UART after entering ISP mode
            print("\n  Checking UART communication after ISP entry...")
            try:
                ser = serial.Serial(
                    self.UART_PORT,
                    self.UART_BAUDRATE,
                    timeout=1.0
                )
                
                time.sleep(0.2)
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send autobaud
                ser.write(b'?')
                ser.flush()
                time.sleep(0.2)
                
                response = ser.read(1)
                if response == b'?':
                    self.log_ok("UART communication successful!")
                    self.log_ok("Hardware appears to be working correctly")
                else:
                    self.log_warn("No response on UART (expected '?', got nothing)")
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
            # Reset to safe state
            try:
                GPIO.output(self.RESET_PIN, GPIO.HIGH)
                GPIO.output(self.ISP_ENABLE_PIN, GPIO.LOW)
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
        print("LPC1115 ISP Diagnostic Tool")
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
        description='LPC1115 ISP Diagnostic Tool'
    )
    
    args = parser.parse_args()
    
    tool = DiagnosticTool()
    return tool.run()


if __name__ == '__main__':
    sys.exit(main())

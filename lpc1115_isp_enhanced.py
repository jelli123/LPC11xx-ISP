#!/usr/bin/env python3
"""
Enhanced LPC1115 ISP Protocol Handler
More complete ISP protocol implementation with flash programming and verification
"""

import sys
import time
import struct
from typing import Optional, Tuple, List


class EnhancedISPProtocol:
    """
    Enhanced ISP Protocol implementation for LPC1115
    Based on LPC1100 User Manual (UM10398)
    """
    
    # Flash parameters for LPC1115
    FLASH_SECTOR_SIZE = 4096      # 4KB
    FLASH_TOTAL_SIZE = 0x8000     # 32KB
    FLASH_START = 0x00000000
    
    # RAM parameters
    RAM_START = 0x10000000
    RAM_SIZE = 0x2000             # 8KB
    
    # Typical ISP boot codes
    CRYSTALFREQ = 12000000        # 12MHz typical
    
    # Part IDs for LPC1115
    VALID_PART_IDS = [
        0x25001110,  # LPC1115
        0x25001113,  # LPC1115 variant
    ]
    
    def __init__(self, serial_port):
        """Initialize with serial port object"""
        self.port = serial_port
        
    def send_cmd(self, cmd: str) -> bool:
        """Send ISP command string and return success"""
        try:
            # Convert command string to bytes with proper termination
            if isinstance(cmd, str):
                cmd = cmd.encode() if isinstance(cmd, str) else cmd
            
            if not cmd.endswith(b'\x0D'):
                cmd += b'\x0D'
            
            self.port.write(cmd)
            self.port.flush()
            return True
        except Exception as e:
            print(f"    Error sending command: {e}")
            return False
    
    def read_response(self, length: int = 1) -> bytes:
        """Read response from bootloader"""
        try:
            data = self.port.read(length)
            return data
        except Exception:
            return b''
    
    def read_line(self) -> bytes:
        """Read a line from bootloader (until CR+LF)"""
        data = b''
        timeout_count = 0
        while timeout_count < 50:  # ~5 second timeout
            char = self.port.read(1)
            if not char:
                timeout_count += 1
                time.sleep(0.1)
                continue
            
            if char == b'\x0D' or char == b'\x0A':
                if data:
                    return data
            else:
                data += char
        
        return data
    
    def call_isp_command(self, cmd_str: str, response_len: int = 0) -> Optional[bytes]:
        """
        Send ISP command and read response
        
        Args:
            cmd_str: Command string (e.g., "54")
            response_len: Expected response length (0 = no response)
        
        Returns:
            Response bytes or None if failed
        """
        
        # Add terminator if not present
        if not cmd_str.endswith('\x0D'):
            cmd_str = cmd_str + '\x0D'
        
        # Send command
        if not self.send_cmd(cmd_str):
            return None
        
        time.sleep(0.05)
        
        # Read response if expected
        if response_len > 0:
            response = self.read_response(response_len)
            return response if len(response) == response_len else None
        
        return b''
    
    def read_part_id_ex(self) -> Optional[int]:
        """
        Read Part ID (extended version)
        Returns part ID as integer
        """
        # Command: "54" = Read Part Identification Number
        response = self.call_isp_command("54", response_len=4)
        
        if response and len(response) == 4:
            part_id = struct.unpack('<I', response)[0]
            return part_id
        
        return None
    
    def unlock_flash(self) -> bool:
        """
        Unlock flash for programming
        Uses default security key for LPC1115
        """
        # Unlock command: "5A 02 <key1> <key2> <key3> <key4>"
        # Default key: 0x12345678
        cmd = "5A 02 78563412"  # Little-endian representation
        
        response = self.call_isp_command(cmd, response_len=1)
        return response == b'\x00'
    
    def erase_sector(self, start_sector: int, end_sector: int) -> bool:
        """
        Erase flash sectors
        
        Args:
            start_sector: First sector to erase (0-7 for 32KB)
            end_sector: Last sector to erase
        
        Returns:
            True if successful
        """
        # Erase command: "52 <start> <end>"
        cmd = f"52 {start_sector:02X} {end_sector:02X}"
        
        response = self.call_isp_command(cmd, response_len=1)
        return response == b'\x00'
    
    def write_to_ram(self, address: int, data: bytes, crc: Optional[int] = None) -> bool:
        """
        Write data to RAM
        
        Args:
            address: RAM address (0x10000000+)
            data: Data to write
            crc: Optional CRC checksum
        
        Returns:
            True if successful
        """
        length = len(data)
        
        # Write to RAM command: "57 <addr> <len> [crc]"
        if crc is not None:
            cmd = f"57 {address:08X} {length:08X} {crc:08X}"
        else:
            cmd = f"57 {address:08X} {length:08X}"
        
        if not self.send_cmd(cmd):
            return False
        
        time.sleep(0.05)
        
        # Send data
        self.port.write(data)
        self.port.flush()
        
        time.sleep(0.1)
        
        # Read response
        response = self.read_response(1)
        return response == b'\x00'
    
    def copy_ram_to_flash(self, dest_addr: int, src_addr: int, 
                         length: int, crc: Optional[int] = None) -> bool:
        """
        Copy RAM to Flash (program flash)
        
        Args:
            dest_addr: Destination address in flash
            src_addr: Source address in RAM
            length: Number of bytes to copy (must be multiple of 256)
            crc: Optional CRC32
        
        Returns:
            True if successful
        """
        # Copy command: "50 <dest> <src> <len> [crc]"
        if crc is not None:
            cmd = f"50 {dest_addr:08X} {src_addr:08X} {length:08X} {crc:08X}"
        else:
            cmd = f"50 {dest_addr:08X} {src_addr:08X} {length:08X}"
        
        response = self.call_isp_command(cmd, response_len=1)
        return response == b'\x00'
    
    def read_from_ram(self, address: int, length: int) -> Optional[bytes]:
        """
        Read data from RAM
        
        Args:
            address: Address to read from
            length: Number of bytes to read
        
        Returns:
            Data read or None if failed
        """
        # Read command: "56 <addr> <len>"
        cmd = f"56 {address:08X} {length:08X}"
        
        response = self.call_isp_command(cmd, response_len=length)
        return response if len(response) == length else None
    
    def read_from_flash(self, address: int, length: int) -> Optional[bytes]:
        """
        Read data from Flash
        
        Args:
            address: Address to read from
            length: Number of bytes to read
        
        Returns:
            Data read or None if failed
        """
        # Can use standard ISP read command or read directly
        # For now, use same as RAM read
        return self.read_from_ram(address, length)
    
    def prepare_sectors(self, start_sector: int, end_sector: int) -> bool:
        """
        Prepare sectors for write (required before Copy RAM to Flash)
        
        Args:
            start_sector: First sector
            end_sector: Last sector
        
        Returns:
            True if successful
        """
        # Prepare command: "50 <start> <end>"
        cmd = f"50 {start_sector:02X} {end_sector:02X}"
        
        response = self.call_isp_command(cmd, response_len=1)
        return response == b'\x00'
    
    def go(self, address: int = 0x00000000, mode: int = 0) -> bool:
        """
        Start user code at address
        
        Args:
            address: Address to execute from
            mode: Mode (0=ARM, 1=Thumb)
        
        Returns:
            True if successful
        """
        # Go command: "47 <addr> <mode>"
        cmd = f"47 {address:08X} {mode:02X}"
        
        response = self.call_isp_command(cmd, response_len=1)
        return response == b'\x00'
    
    def echo(self) -> bool:
        """Test communication with echo"""
        if not self.send_cmd("?"):
            return False
        
        time.sleep(0.1)
        response = self.read_response(1)
        return response == b'?'
    
    def get_uid(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Read Unique ID (4x 32-bit words)
        
        Returns:
            Tuple of (UID0, UID1, UID2, UID3) or None
        """
        cmd = "5A 01 00 00"
        
        response = self.call_isp_command(cmd, response_len=16)
        
        if response and len(response) == 16:
            uids = struct.unpack('<IIII', response)
            return uids
        
        return None
    
    def calculate_crc(self, data: bytes) -> int:
        """
        Calculate CRC32 checksum for ISP commands
        
        Args:
            data: Data to checksum
        
        Returns:
            CRC32 value
        """
        # Simplified CRC32 (actual implementation may vary)
        import zlib
        return zlib.crc32(data) & 0xFFFFFFFF


class FlashMemoryManager:
    """Manages flash memory operations for LPC1115"""
    
    def __init__(self, isp_protocol: EnhancedISPProtocol):
        self.isp = isp_protocol
        self.sector_size = 4096
        self.flash_start = 0x00000000
        self.flash_end = 0x00007FFF
        self.ram_addr = 0x10000000
        self.buffer_size = 256  # 256 byte buffer for writes
    
    def get_sectors_for_range(self, start: int, end: int) -> Tuple[int, int]:
        """Get sector range for address range"""
        start_sector = start // self.sector_size
        end_sector = end // self.sector_size
        return start_sector, end_sector
    
    def write_flash_data(self, flash_addr: int, data: bytes) -> bool:
        """
        Write data to flash
        
        Args:
            flash_addr: Flash address
            data: Data to write
        
        Returns:
            True if successful
        """
        
        print(f"    Writing {len(data)} bytes to 0x{flash_addr:04X}")
        
        # Write in 256-byte chunks
        for offset in range(0, len(data), self.buffer_size):
            chunk = data[offset:offset + self.buffer_size]
            chunk_flash_addr = flash_addr + offset
            
            # Write to RAM first
            if not self.isp.write_to_ram(self.ram_addr, chunk):
                print(f"      ✗ Failed to write to RAM at 0x{self.ram_addr:08X}")
                return False
            
            # Get sectors for this address
            sector_start, sector_end = self.get_sectors_for_range(
                chunk_flash_addr, 
                chunk_flash_addr + len(chunk) - 1
            )
            
            # Prepare sectors
            if not self.isp.prepare_sectors(sector_start, sector_end):
                print(f"      ✗ Failed to prepare sectors {sector_start}-{sector_end}")
                return False
            
            # Copy to flash
            if not self.isp.copy_ram_to_flash(chunk_flash_addr, self.ram_addr, len(chunk)):
                print(f"      ✗ Failed to copy to flash")
                return False
            
            print(f"      ✓ Programmed 0x{chunk_flash_addr:04X} ({len(chunk)} bytes)")
        
        return True
    
    def verify_flash_data(self, flash_addr: int, expected_data: bytes) -> bool:
        """
        Verify flash data
        
        Args:
            flash_addr: Flash address to verify
            expected_data: Expected data
        
        Returns:
            True if verified
        """
        
        print(f"    Verifying {len(expected_data)} bytes at 0x{flash_addr:04X}")
        
        # Read back data
        read_data = self.isp.read_from_flash(flash_addr, len(expected_data))
        
        if not read_data:
            print(f"      ✗ Failed to read flash")
            return False
        
        # Compare
        if read_data == expected_data:
            print(f"      ✓ Verified ({len(read_data)} bytes match)")
            return True
        else:
            print(f"      ✗ Verification failed")
            # Show first difference
            for i, (expected, actual) in enumerate(zip(expected_data, read_data)):
                if expected != actual:
                    print(f"        First difference at offset {i}: "
                          f"expected 0x{expected:02X}, got 0x{actual:02X}")
                    break
            return False


def example_usage():
    """
    Example of using the enhanced ISP protocol
    """
    
    print("Enhanced ISP Protocol Example")
    print("=" * 50)
    
    # Note: This is example code showing how to use the classes
    # In practice, you would:
    # 1. Initialize serial port
    # 2. Create ISPProtocol instance
    # 3. Use FlashMemoryManager for operations
    
    print("""
    # Usage example:
    
    import serial
    from lpc1115_isp_enhanced import EnhancedISPProtocol, FlashMemoryManager
    
    # Open serial port
    ser = serial.Serial('/dev/ttyAMA0', 115200, timeout=1.0)
    
    # Create protocol handler
    isp = EnhancedISPProtocol(ser)
    
    # Verify communication
    if isp.echo():
        print("✓ Communication established")
    
    # Read chip ID
    part_id = isp.read_part_id_ex()
    print(f"Part ID: 0x{part_id:08X}")
    
    # Create flash manager
    flash_mgr = FlashMemoryManager(isp)
    
    # Write flash
    data = bytes([0x00, 0x10, 0x20, ...])
    flash_mgr.write_flash_data(0x0000, data)
    
    # Verify
    flash_mgr.verify_flash_data(0x0000, data)
    
    # Run user code
    isp.go(0x0000)
    
    ser.close()
    """)


if __name__ == '__main__':
    example_usage()

#!/usr/bin/env python3
"""
LPC11xx ISP Protocol Handler
Complete ISP protocol implementation based on LPC11xx User Manual (UM10398)

The LPC11xx ISP uses ASCII text commands over UART.
Commands are single letters followed by parameters, terminated with \\r\\n.

Supports the full LPC11xx family: LPC1110, LPC1111, LPC1112, LPC1113,
LPC1114, LPC1115, LPC11C12, LPC11C14, LPC11C22, LPC11C24.
"""

import sys
import time
import struct
import binascii
import serial
from typing import Optional, Tuple, List


class ISPReturnCodes:
    """ISP command return codes (UM10398 Table 333)"""
    CMD_SUCCESS = 0
    INVALID_COMMAND = 1
    SRC_ADDR_ERROR = 2
    DST_ADDR_ERROR = 3
    SRC_ADDR_NOT_MAPPED = 4
    DST_ADDR_NOT_MAPPED = 5
    COUNT_ERROR = 6
    INVALID_SECTOR = 7
    SECTOR_NOT_BLANK = 8
    SECTOR_NOT_PREPARED = 9
    COMPARE_ERROR = 10
    BUSY = 11
    PARAM_ERROR = 12
    ADDR_ERROR = 13
    ADDR_NOT_MAPPED = 14
    CMD_LOCKED = 15
    INVALID_CODE = 16
    INVALID_BAUD_RATE = 17
    INVALID_STOP_BIT = 18
    CODE_READ_PROTECTION_ENABLED = 19

    MESSAGES = {
        0: "CMD_SUCCESS",
        1: "INVALID_COMMAND",
        2: "SRC_ADDR_ERROR",
        3: "DST_ADDR_ERROR",
        4: "SRC_ADDR_NOT_MAPPED",
        5: "DST_ADDR_NOT_MAPPED",
        6: "COUNT_ERROR",
        7: "INVALID_SECTOR",
        8: "SECTOR_NOT_BLANK",
        9: "SECTOR_NOT_PREPARED",
        10: "COMPARE_ERROR",
        11: "BUSY",
        12: "PARAM_ERROR",
        13: "ADDR_ERROR",
        14: "ADDR_NOT_MAPPED",
        15: "CMD_LOCKED",
        16: "INVALID_CODE",
        17: "INVALID_BAUD_RATE",
        18: "INVALID_STOP_BIT",
        19: "CODE_READ_PROTECTION_ENABLED",
    }


class EnhancedISPProtocol:
    """
    ISP Protocol implementation for LPC11xx family
    Based on LPC11xx User Manual (UM10398), Chapter 26

    ISP commands are ASCII text, single-letter commands:
      U  - Unlock
      B  - Set Baud Rate
      A  - Echo (enable/disable)
      W  - Write to RAM
      R  - Read Memory
      P  - Prepare Sectors for Write
      C  - Copy RAM to Flash
      G  - Go (execute code)
      E  - Erase Sectors
      I  - Blank Check Sectors
      J  - Read Part ID
      K  - Read Boot Code Version
      M  - Compare
      N  - Read UID
    """

    # Flash parameters (defaults for LPC1114/LPC1115, overridden per chip)
    FLASH_SECTOR_SIZE = 4096      # 4KB per sector
    FLASH_START = 0x00000000

    # RAM parameters
    RAM_START = 0x10000000

    # Valid copy sizes for Copy RAM to Flash
    VALID_COPY_SIZES = [256, 512, 1024, 4096]

    # Part IDs for all LPC11xx variants: {part_id: ("name", flash_kb, ram_kb)}
    PART_IDS = {
        # LPC1110
        0x0A07102B: ("LPC1110.../002",    4,  1),
        0x1A07102B: ("LPC1110.../002",    4,  1),
        # LPC1111
        0x0A16D02B: ("LPC1111.../002",    8,  2),
        0x1A16D02B: ("LPC1111.../002",    8,  2),
        0x041E502B: ("LPC1111.../101",    8,  2),
        0x2516D02B: ("LPC1111.../102",    8,  2),
        0x00010013: ("LPC1111.../103",    8,  2),
        0x0416502B: ("LPC1111.../201",    8,  4),
        0x2516902B: ("LPC1111.../202",    8,  4),
        0x00010012: ("LPC1111.../203",    8,  4),
        # LPC1112
        0x042D502B: ("LPC1112.../101",   16,  2),
        0x2524D02B: ("LPC1112.../102",   16,  2),
        0x0A24902B: ("LPC1112.../102",   16,  4),
        0x1A24902B: ("LPC1112.../102",   16,  4),
        0x00020023: ("LPC1112.../103",   16,  2),
        0x0425502B: ("LPC1112.../201",   16,  4),
        0x2524902B: ("LPC1112.../202",   16,  4),
        0x00020022: ("LPC1112.../203",   16,  4),
        # LPC1113
        0x0434502B: ("LPC1113.../201",   24,  4),
        0x2532902B: ("LPC1113.../202",   24,  4),
        0x00030032: ("LPC1113.../203",   24,  4),
        0x0434102B: ("LPC1113.../301",   24,  8),
        0x2532102B: ("LPC1113.../302",   24,  8),
        0x00030030: ("LPC1113.../303",   24,  8),
        # LPC1114
        0x0A40902B: ("LPC1114.../102",   32,  4),
        0x1A40902B: ("LPC1114.../102",   32,  4),
        0x0444502B: ("LPC1114.../201",   32,  4),
        0x2540902B: ("LPC1114.../202",   32,  4),
        0x00040042: ("LPC1114.../203",   32,  8),
        0x0444102B: ("LPC1114.../301",   32,  8),
        0x2540102B: ("LPC1114.../302",   32,  8),
        0x00040040: ("LPC1114.../303",   32,  8),
        0x00040060: ("LPC1114.../323",   32,  8),
        0x00040070: ("LPC1114.../333",   32,  8),
        # LPC1115
        0x00050080: ("LPC1115.../303",   64,  8),
        # LPC1102
        0x2500102B: ("LPC1102",           32,  8),
        # LPC11C1x / LPC11C2x (CAN variants)
        0x1421102B: ("LPC11C12.../301",  16,  8),
        0x1440102B: ("LPC11C14.../301",  32,  8),
        0x1431102B: ("LPC11C22.../301",  16,  8),
        0x1430102B: ("LPC11C24.../301",  32,  8),
    }

    # Unlock code
    UNLOCK_CODE = 23130

    @classmethod
    def lookup_part(cls, part_id: int) -> Optional[Tuple[str, int, int]]:
        """Look up part name, flash_kb, ram_kb for a given part ID."""
        return cls.PART_IDS.get(part_id)

    @classmethod
    def get_chip_params(cls, part_id: int) -> Tuple[int, int, int]:
        """Return (flash_size_bytes, ram_size_bytes, num_sectors) for part ID.
        Falls back to LPC1114/303 defaults if unknown."""
        info = cls.PART_IDS.get(part_id)
        if info:
            flash_kb = info[1]
            ram_kb = info[2]
        else:
            flash_kb = 32
            ram_kb = 8
        flash_bytes = flash_kb * 1024
        ram_bytes = ram_kb * 1024
        num_sectors = flash_bytes // cls.FLASH_SECTOR_SIZE
        return flash_bytes, ram_bytes, num_sectors

    def __init__(self, serial_port, crystal_freq_khz: int = 12000, verbose: bool = False):
        """
        Initialize with serial port object

        Args:
            serial_port: Opened serial.Serial instance
            crystal_freq_khz: Crystal frequency in kHz (default 12000 = 12MHz)
            verbose: Enable hex/ASCII debug output of serial traffic
        """
        self.port = serial_port
        self.crystal_freq_khz = crystal_freq_khz
        self.echo_enabled = True  # Bootloader echoes by default until 'A 0' is sent
        self.synchronized = False
        self.verbose = verbose

    def _log_tx(self, data: bytes):
        """Log transmitted bytes in hex and ASCII if verbose."""
        if not self.verbose:
            return
        hex_str = ' '.join(f'{b:02X}' for b in data)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        print(f"    TX [{len(data):3d}]: {hex_str}  |{ascii_str}|")

    def _log_rx(self, data: bytes):
        """Log received bytes in hex and ASCII if verbose."""
        if not self.verbose:
            return
        if not data:
            print(f"    RX [  0]: (empty)")
            return
        hex_str = ' '.join(f'{b:02X}' for b in data)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        print(f"    RX [{len(data):3d}]: {hex_str}  |{ascii_str}|")

    def send_command(self, cmd: str) -> bool:
        """
        Send ISP command string terminated with CR LF

        Args:
            cmd: Command string (e.g. "J" or "P 0 7")

        Returns:
            True if send succeeded
        """
        try:
            line = cmd + "\r\n"
            encoded = line.encode('ascii')
            self._log_tx(encoded)
            self.port.write(encoded)
            self.port.flush()
            return True
        except Exception as e:
            print(f"    Error sending command: {e}")
            return False

    def read_line(self, timeout: float = 2.0) -> Optional[str]:
        """
        Read a line from bootloader (until CR LF)

        Returns:
            Decoded string without line termination, or None on timeout
        """
        old_timeout = self.port.timeout
        self.port.timeout = timeout
        try:
            line = self.port.readline()
            if line:
                self._log_rx(line)
                return line.decode('ascii', errors='ignore').strip()
            self._log_rx(b'')
            return None
        except Exception:
            return None
        finally:
            self.port.timeout = old_timeout

    def _read_sync_response(self, timeout: float = 3.0) -> Optional[str]:
        """
        Read the synchronization response reliably.

        Uses inter_byte_timeout to let the kernel UART driver collect all bytes
        of a burst before returning. This avoids the race condition where reading
        byte-by-byte in Python can miss bytes that arrive between read() calls.

        Strategy:
          - Set a long timeout for the FIRST byte (wait for bootloader)
          - Set a short inter_byte_timeout so read() returns when a gap is detected
          - Read a large buffer in ONE call — the kernel collects all bytes

        Returns:
            "Synchronized" if found in received data, or whatever was received, or None
        """
        old_timeout = self.port.timeout
        old_inter_byte_timeout = self.port.inter_byte_timeout
        try:
            # inter_byte_timeout: if no new byte arrives within this time,
            # read() returns what it has. At 115200 baud, one byte takes ~87µs,
            # so 50ms is very generous for inter-byte gaps.
            self.port.timeout = timeout
            self.port.inter_byte_timeout = 0.05

            # Read up to 100 bytes — will return when:
            #   - 100 bytes received, OR
            #   - 50ms gap between bytes (message complete), OR
            #   - timeout seconds elapsed (no response at all)
            data = self.port.read(100)

            if data:
                self._log_rx(data)
                decoded = data.decode('ascii', errors='ignore').strip()
                if "Synchronized" in decoded:
                    return "Synchronized"
                return decoded if decoded else None
            return None
        finally:
            self.port.timeout = old_timeout
            self.port.inter_byte_timeout = old_inter_byte_timeout

    def _consume_echo(self, sent_cmd: str) -> None:
        """Consume the echo of the sent command if echo is enabled"""
        if self.echo_enabled:
            self.read_line(timeout=0.5)

    def _read_return_code(self) -> Optional[int]:
        """
        Read the return code from a command response

        Returns:
            Integer return code or None on error
        """
        line = self.read_line(timeout=2.0)
        if line is not None:
            try:
                return int(line.strip())
            except ValueError:
                return None
        return None

    def synchronize(self) -> bool:
        """
        Perform ISP synchronization handshake (UM10398, Section 26.4.1)

        Sequence:
          1. Host sends '?' (possibly multiple times for reliable autobaud)
          2. Device responds 'Synchronized\\r\\n'
          3. Host sends 'Synchronized\\r\\n'
          4. Device responds 'Synchronized\\r\\nOK\\r\\n'
          5. Host sends '<crystal_freq_khz>\\r\\n'
          6. Device responds '<crystal_freq_khz>\\r\\nOK\\r\\n'

        Returns:
            True if synchronization succeeded
        """
        # Clear buffers
        self.port.reset_input_buffer()
        self.port.reset_output_buffer()

        # Step 1: Send a single '?' for autobaud detection.
        # The LPC bootloader uses the '?' (0x3F) character to calibrate its
        # baud rate. Per UM10398: the auto-baud routine measures the bit time
        # from the start bit to determine the baud rate. Only ONE '?' should
        # be sent per attempt — multiple '?' can confuse the auto-baud if they
        # arrive while it's still measuring.
        self._log_tx(b'?')
        self.port.write(b'?')
        self.port.flush()

        # Wait for "Synchronized" response (bootloader needs time to init)
        response = self._read_sync_response(timeout=3.0)

        # Step 2: Check response
        if response != "Synchronized":
            print(f"    Expected 'Synchronized', got: '{response}'")
            return False

        # Step 3: Send "Synchronized"
        self.send_command("Synchronized")

        # Step 4: Read echo + "OK"
        resp1 = self.read_line(timeout=2.0)  # Echo: "Synchronized"
        if resp1 == "Synchronized":
            resp2 = self.read_line(timeout=2.0)  # "OK"
            if resp2 != "OK":
                print(f"    Expected 'OK', got: '{resp2}'")
                return False
        elif resp1 == "OK":
            pass  # Echo might be off
        else:
            print(f"    Unexpected response: '{resp1}'")
            return False

        # Step 5: Send crystal frequency in kHz
        freq_str = str(self.crystal_freq_khz)
        self.send_command(freq_str)

        # Step 6: Read echo + "OK"
        resp1 = self.read_line(timeout=2.0)  # Echo: frequency
        if resp1 == freq_str:
            resp2 = self.read_line(timeout=2.0)  # "OK"
            if resp2 != "OK":
                print(f"    Expected 'OK' after freq, got: '{resp2}'")
                return False
        elif resp1 == "OK":
            pass
        else:
            print(f"    Unexpected response after freq: '{resp1}'")
            return False

        self.synchronized = True

        # Disable echo — the bootloader echoes every sent character by default.
        # Disabling it simplifies all subsequent command/response handling.
        self.set_echo(False)

        return True

    def set_echo(self, enable: bool) -> bool:
        """
        Enable or disable command echo (Command: A)

        Args:
            enable: True to enable echo, False to disable

        Returns:
            True if successful
        """
        setting = 1 if enable else 0
        cmd = f"A {setting}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        if rc == ISPReturnCodes.CMD_SUCCESS:
            self.echo_enabled = enable
            return True
        return False

    def unlock(self) -> bool:
        """
        Unlock flash for write/erase operations (Command: U)

        Must be called before P, E, or C commands.

        Returns:
            True if successful
        """
        cmd = f"U {self.UNLOCK_CODE}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        return rc == ISPReturnCodes.CMD_SUCCESS

    def set_baud_rate(self, baudrate: int, stop_bits: int = 1) -> bool:
        """
        Set ISP baud rate (Command: B)

        Args:
            baudrate: New baud rate
            stop_bits: Stop bits (1 or 2)

        Returns:
            True if successful
        """
        cmd = f"B {baudrate} {stop_bits}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        return rc == ISPReturnCodes.CMD_SUCCESS

    def read_part_id(self) -> Optional[int]:
        """
        Read Part Identification Number (Command: J)

        Returns:
            Part ID as integer, or None on failure
        """
        cmd = "J"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        if rc != ISPReturnCodes.CMD_SUCCESS:
            return None

        # Read part ID value (decimal string)
        line = self.read_line(timeout=2.0)
        if line:
            try:
                return int(line.strip())
            except ValueError:
                return None
        return None

    def read_uid(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Read Unique ID (Command: N)
        Returns 4x 32-bit words.

        Returns:
            Tuple of (UID0, UID1, UID2, UID3) or None
        """
        cmd = "N"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        if rc != ISPReturnCodes.CMD_SUCCESS:
            return None

        # Read 4 lines, each containing a 32-bit word (decimal)
        uids = []
        for _ in range(4):
            line = self.read_line(timeout=2.0)
            if line:
                try:
                    uids.append(int(line.strip()))
                except ValueError:
                    return None
            else:
                return None

        return tuple(uids)

    def read_boot_code_version(self) -> Optional[Tuple[int, int]]:
        """
        Read Boot Code Version (Command: K)

        Returns:
            Tuple of (major, minor) or None
        """
        cmd = "K"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        if rc != ISPReturnCodes.CMD_SUCCESS:
            return None

        major_line = self.read_line(timeout=2.0)
        minor_line = self.read_line(timeout=2.0)
        if major_line and minor_line:
            try:
                return (int(major_line.strip()), int(minor_line.strip()))
            except ValueError:
                return None
        return None

    def prepare_sectors(self, start_sector: int, end_sector: int) -> bool:
        """
        Prepare sectors for write/erase (Command: P)
        Must be called before E (erase) or C (copy RAM to flash).

        Args:
            start_sector: First sector (0-based)
            end_sector: Last sector (0-based, inclusive)

        Returns:
            True if successful
        """
        cmd = f"P {start_sector} {end_sector}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        return rc == ISPReturnCodes.CMD_SUCCESS

    def erase_sectors(self, start_sector: int, end_sector: int) -> bool:
        """
        Erase flash sectors (Command: E)
        Sectors must be prepared first with prepare_sectors().

        Args:
            start_sector: First sector (0-based)
            end_sector: Last sector (0-based, inclusive)

        Returns:
            True if successful
        """
        cmd = f"E {start_sector} {end_sector}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        return rc == ISPReturnCodes.CMD_SUCCESS

    def blank_check_sectors(self, start_sector: int, end_sector: int) -> Tuple[bool, Optional[int]]:
        """
        Blank check sectors (Command: I)

        Args:
            start_sector: First sector
            end_sector: Last sector

        Returns:
            Tuple of (is_blank, first_non_blank_offset)
        """
        cmd = f"I {start_sector} {end_sector}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        if rc == ISPReturnCodes.CMD_SUCCESS:
            return (True, None)
        elif rc == ISPReturnCodes.SECTOR_NOT_BLANK:
            # Read offset and contents
            offset_line = self.read_line(timeout=1.0)
            content_line = self.read_line(timeout=1.0)
            offset = None
            if offset_line:
                try:
                    offset = int(offset_line.strip())
                except ValueError:
                    pass
            return (False, offset)
        return (False, None)

    def write_to_ram(self, address: int, data: bytes) -> bool:
        """
        Write data to RAM (Command: W)

        Args:
            address: RAM start address (word-aligned)
            data: Data to write (length must be multiple of 4)

        Returns:
            True if successful
        """
        length = len(data)
        cmd = f"W {address} {length}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        if rc != ISPReturnCodes.CMD_SUCCESS:
            return False

        # Send data using UU-encoding
        return self._send_uuencoded_data(data)

    def _send_uuencoded_data(self, data: bytes, max_retries: int = 3) -> bool:
        """
        Send data using UU-encoding as required by LPC ISP protocol.
        Data is sent in lines of up to 45 bytes (60 encoded chars).
        Every 20 lines (or at end of data), a checksum line is sent.
        The bootloader responds with "OK" or "RESEND".
        On "RESEND", the last block of lines is retransmitted.

        Flow control per UM10398, Section 26.4.

        Args:
            data: Raw data to send
            max_retries: Maximum retries per block on RESEND

        Returns:
            True if successful
        """
        offset = 0

        while offset < len(data):
            # Determine block: up to 20 lines × 45 bytes = 900 bytes
            block_start = offset
            block_end = min(offset + 20 * 45, len(data))

            for attempt in range(max_retries):
                lines_sent = 0
                checksum = 0
                pos = block_start

                # Send UU-encoded lines for this block
                while pos < block_end:
                    chunk = data[pos:pos + 45]
                    encoded = binascii.b2a_uu(chunk)
                    self._log_tx(encoded)
                    self.port.write(encoded)
                    self.port.flush()

                    checksum += sum(chunk)
                    lines_sent += 1
                    pos += len(chunk)

                # Send checksum for this block
                checksum_line = f"{checksum}\r\n"
                self.port.write(checksum_line.encode('ascii'))
                self.port.flush()

                # Wait for acknowledgement
                resp = self.read_line(timeout=2.0)
                if resp == "OK":
                    break  # Block accepted, move to next
                elif resp == "RESEND":
                    if attempt + 1 < max_retries:
                        continue  # Retry this block
                    else:
                        print(f"    Data transfer failed after {max_retries} retries")
                        return False
                else:
                    print(f"    Data transfer error: '{resp}'")
                    return False

            offset = block_end

        return True

    def _read_line_raw(self, timeout: float = 2.0) -> Optional[bytes]:
        """Read a raw line from port with explicit timeout and logging."""
        old_timeout = self.port.timeout
        self.port.timeout = timeout
        try:
            line = self.port.readline()
            if line:
                self._log_rx(line)
                return line
            return None
        except serial.SerialException as e:
            if self.verbose:
                print(f"    Serial error: {e}")
            return None
        finally:
            self.port.timeout = old_timeout

    def _receive_uuencoded_data(self, length: int, max_retries: int = 3) -> Optional[bytes]:
        """
        Receive UU-encoded data from bootloader.

        The bootloader sends up to 20 UU-encoded lines, then a checksum.
        Host responds with "OK" or "RESEND".
        On "RESEND", the bootloader retransmits the last block.

        Flow control per UM10398, Section 26.4.

        Args:
            length: Expected number of bytes
            max_retries: Maximum retries per block on checksum mismatch

        Returns:
            Decoded data or None on error
        """
        data = b''

        while len(data) < length:
            # Receive one block (up to 20 lines + checksum)
            block_data = b''
            block_checksum = 0
            lines_received = 0
            block_ok = False

            for attempt in range(max_retries):
                if attempt > 0:
                    # Re-receiving after RESEND
                    block_data = b''
                    block_checksum = 0
                    lines_received = 0

                while lines_received < 20:
                    line = self._read_line_raw(timeout=2.0)
                    if not line:
                        if self.verbose:
                            print(f"    UU receive: timeout after {lines_received} lines, {len(data)+len(block_data)}/{length} bytes")
                        return None

                    line_stripped = line.strip()

                    # Try to decode as UU-encoded data
                    try:
                        decoded = binascii.a2b_uu(line)
                        block_data += decoded
                        block_checksum += sum(decoded)
                        lines_received += 1
                    except binascii.Error:
                        # Not UU data — must be the checksum line
                        try:
                            received_checksum = int(line_stripped.decode('ascii'))
                            if received_checksum == block_checksum:
                                self.send_command("OK")
                                block_ok = True
                            else:
                                if self.verbose:
                                    print(f"    UU checksum mismatch: got {received_checksum}, expected {block_checksum}")
                                self.send_command("RESEND")
                            break
                        except ValueError:
                            if self.verbose:
                                print(f"    UU unexpected line: {line_stripped}")
                            return None

                    # Check if we have all data
                    if len(data) + len(block_data) >= length:
                        # Remaining data complete, next line is checksum
                        cs_line = self._read_line_raw(timeout=2.0)
                        if not cs_line:
                            return None
                        try:
                            received_checksum = int(cs_line.strip().decode('ascii'))
                            if received_checksum == block_checksum:
                                self.send_command("OK")
                                block_ok = True
                            else:
                                if self.verbose:
                                    print(f"    UU checksum mismatch: got {received_checksum}, expected {block_checksum}")
                                self.send_command("RESEND")
                        except ValueError:
                            return None
                        break

                if not block_ok and lines_received == 20:
                    # Read checksum after 20 lines
                    cs_line = self._read_line_raw(timeout=2.0)
                    if not cs_line:
                        return None
                    try:
                        received_checksum = int(cs_line.strip().decode('ascii'))
                        if received_checksum == block_checksum:
                            self.send_command("OK")
                            block_ok = True
                        else:
                            if self.verbose:
                                print(f"    UU checksum mismatch: got {received_checksum}, expected {block_checksum}")
                            self.send_command("RESEND")
                    except ValueError:
                        return None

                if block_ok:
                    break

            if not block_ok:
                print(f"    Receive failed after {max_retries} retries")
                return None

            data += block_data

        return data[:length]

    def read_memory(self, address: int, length: int) -> Optional[bytes]:
        """
        Read memory (Command: R)
        Can read from both RAM and Flash.

        Args:
            address: Start address (word-aligned)
            length: Number of bytes to read (multiple of 4)

        Returns:
            Data bytes or None on failure
        """
        cmd = f"R {address} {length}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        if rc != ISPReturnCodes.CMD_SUCCESS:
            return None

        # Receive UU-encoded data
        return self._receive_uuencoded_data(length)

    def copy_ram_to_flash(self, flash_addr: int, ram_addr: int, length: int) -> bool:
        """
        Copy RAM to Flash (Command: C)
        Programs flash from RAM buffer. Sectors must be prepared first.

        Args:
            flash_addr: Destination flash address (256-byte aligned)
            ram_addr: Source RAM address (word-aligned)
            length: Number of bytes (must be 256, 512, 1024, or 4096)

        Returns:
            True if successful
        """
        if length not in self.VALID_COPY_SIZES:
            print(f"    Error: Copy size must be one of {self.VALID_COPY_SIZES}")
            return False

        cmd = f"C {flash_addr} {ram_addr} {length}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        return rc == ISPReturnCodes.CMD_SUCCESS

    def compare(self, addr1: int, addr2: int, length: int) -> Tuple[bool, Optional[int]]:
        """
        Compare memory regions (Command: M)

        Args:
            addr1: First address
            addr2: Second address
            length: Number of bytes to compare

        Returns:
            Tuple of (match, first_mismatch_offset)
        """
        cmd = f"M {addr1} {addr2} {length}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        if rc == ISPReturnCodes.CMD_SUCCESS:
            return (True, None)
        elif rc == ISPReturnCodes.COMPARE_ERROR:
            line = self.read_line(timeout=1.0)
            offset = None
            if line:
                try:
                    offset = int(line.strip())
                except ValueError:
                    pass
            return (False, offset)
        return (False, None)

    def go(self, address: int, mode: str = 'T') -> bool:
        """
        Execute code at address (Command: G)

        Args:
            address: Start address (must have Thumb bit set for Cortex-M0)
            mode: 'T' for Thumb mode (required for Cortex-M0)

        Returns:
            True if successful
        """
        cmd = f"G {address} {mode}"
        self.send_command(cmd)
        self._consume_echo(cmd)

        rc = self._read_return_code()
        return rc == ISPReturnCodes.CMD_SUCCESS


class FlashMemoryManager:
    """Manages flash memory operations for LPC11xx family"""

    def __init__(self, isp_protocol: EnhancedISPProtocol,
                 flash_size: int = 32 * 1024, ram_size: int = 8 * 1024):
        self.isp = isp_protocol
        self.sector_size = EnhancedISPProtocol.FLASH_SECTOR_SIZE
        self.flash_start = EnhancedISPProtocol.FLASH_START
        self.flash_size = flash_size
        self.ram_size = ram_size
        self.num_sectors = flash_size // self.sector_size
        # Place RAM buffer after first 0x300 bytes (reserved by bootloader)
        self.ram_buffer_addr = 0x10000300
        self.write_size = 256  # Minimum write size

    def get_sector_for_address(self, address: int) -> int:
        """Get sector number for a flash address"""
        return address // self.sector_size

    def get_sectors_for_range(self, start: int, end: int) -> Tuple[int, int]:
        """Get sector range for address range"""
        start_sector = start // self.sector_size
        end_sector = end // self.sector_size
        return start_sector, end_sector

    def erase_sectors(self, start_sector: int, end_sector: int) -> bool:
        """
        Erase flash sectors (unlock + prepare + erase)

        Args:
            start_sector: First sector
            end_sector: Last sector (inclusive)

        Returns:
            True if successful
        """
        # Unlock first
        if not self.isp.unlock():
            print("    Error: Failed to unlock flash")
            return False

        # Prepare sectors
        if not self.isp.prepare_sectors(start_sector, end_sector):
            print(f"    Error: Failed to prepare sectors {start_sector}-{end_sector}")
            return False

        # Erase
        if not self.isp.erase_sectors(start_sector, end_sector):
            print(f"    Error: Failed to erase sectors {start_sector}-{end_sector}")
            return False

        return True

    def write_flash_data(self, flash_addr: int, data: bytes) -> bool:
        """
        Write data to flash memory.
        Handles unlocking, preparation, RAM writing, and copying to flash.

        Args:
            flash_addr: Flash destination address (256-byte aligned)
            data: Data to write

        Returns:
            True if successful
        """
        print(f"    Writing {len(data)} bytes to 0x{flash_addr:08X}")

        # Pad data to minimum write size
        if len(data) % self.write_size != 0:
            pad_len = self.write_size - (len(data) % self.write_size)
            data = data + b'\xFF' * pad_len

        # Determine best copy size
        copy_size = self.write_size
        for size in EnhancedISPProtocol.VALID_COPY_SIZES:
            if size <= len(data) and len(data) % size == 0:
                copy_size = size

        # Write in chunks
        for offset in range(0, len(data), copy_size):
            chunk = data[offset:offset + copy_size]
            chunk_flash_addr = flash_addr + offset

            # Get sectors for this chunk
            start_sector, end_sector = self.get_sectors_for_range(
                chunk_flash_addr,
                chunk_flash_addr + len(chunk) - 1
            )

            # Write chunk to RAM
            if not self.isp.write_to_ram(self.ram_buffer_addr, chunk):
                print(f"      Error: Failed to write to RAM")
                return False

            # Unlock
            if not self.isp.unlock():
                print(f"      Error: Failed to unlock")
                return False

            # Prepare sectors
            if not self.isp.prepare_sectors(start_sector, end_sector):
                print(f"      Error: Failed to prepare sectors {start_sector}-{end_sector}")
                return False

            # Copy RAM to Flash
            if not self.isp.copy_ram_to_flash(chunk_flash_addr, self.ram_buffer_addr, len(chunk)):
                print(f"      Error: Failed to copy to flash at 0x{chunk_flash_addr:08X}")
                return False

            print(f"      Programmed 0x{chunk_flash_addr:08X} ({len(chunk)} bytes)")

        return True

    def verify_flash_data(self, flash_addr: int, expected_data: bytes) -> bool:
        """
        Verify flash data using the Compare command.

        Args:
            flash_addr: Flash address to verify
            expected_data: Expected data

        Returns:
            True if verified
        """
        print(f"    Verifying {len(expected_data)} bytes at 0x{flash_addr:08X}")

        # Pad to word alignment
        verify_len = len(expected_data)
        if verify_len % 4 != 0:
            verify_len = ((verify_len + 3) // 4) * 4

        # Write expected data to RAM for comparison
        padded = expected_data + b'\xFF' * (verify_len - len(expected_data))
        if not self.isp.write_to_ram(self.ram_buffer_addr, padded):
            print(f"      Error: Failed to write verification data to RAM")
            return False

        # Use Compare command
        match, offset = self.isp.compare(flash_addr, self.ram_buffer_addr, verify_len)

        if match:
            print(f"      Verified OK ({len(expected_data)} bytes match)")
            return True
        else:
            print(f"      Verification failed at offset {offset}")
            return False

    def read_flash_data(self, flash_addr: int, length: int) -> Optional[bytes]:
        """
        Read data from flash memory.

        Args:
            flash_addr: Start address
            length: Number of bytes

        Returns:
            Data or None on failure
        """
        return self.isp.read_memory(flash_addr, length)


def example_usage():
    """Example of using the ISP protocol"""

    print("LPC11xx ISP Protocol Example")
    print("=" * 50)

    print("""
    # Usage example:

    import serial
    from lpc1115_isp_enhanced import EnhancedISPProtocol, FlashMemoryManager

    # Open serial port
    ser = serial.Serial('/dev/ttyAMA0', 115200, timeout=1.0)

    # Create protocol handler (12MHz crystal)
    isp = EnhancedISPProtocol(ser, crystal_freq_khz=12000)

    # Synchronize with bootloader
    if isp.synchronize():
        print("Synchronized with bootloader")

    # Read chip ID (Command: J)
    part_id = isp.read_part_id()
    info = EnhancedISPProtocol.lookup_part(part_id)
    if info:
        name, flash_kb, ram_kb = info
        print(f"Detected: {name} ({flash_kb}KB Flash, {ram_kb}KB RAM)")

    # Get chip-specific parameters
    flash_size, ram_size, num_sectors = EnhancedISPProtocol.get_chip_params(part_id)

    # Create flash manager with correct sizes
    flash_mgr = FlashMemoryManager(isp, flash_size=flash_size, ram_size=ram_size)

    # Unlock flash
    isp.unlock()

    # Erase sector 0
    flash_mgr.erase_sectors(0, 0)

    # Write data to flash
    data = bytes([0x00, 0x10, 0x00, 0x20, ...])
    flash_mgr.write_flash_data(0x0000, data)

    # Verify
    flash_mgr.verify_flash_data(0x0000, data)

    # Read flash back
    read_data = flash_mgr.read_flash_data(0x0000, 256)

    # Run user code (Thumb mode for Cortex-M0)
    isp.go(0x00000000, 'T')

    ser.close()
    """)


if __name__ == '__main__':
    example_usage()

import time
import threading
import serial
import re
import os
try:
    from utils.common import CommonUtils
except ModuleNotFoundError:
    from ..utils.common import CommonUtils


class Device:
    def __init__(
        self,
        name,
        port,
        baud_rate,
        stop_bits=serial.STOPBITS_ONE,
        parity=serial.PARITY_NONE,
        data_bits=serial.EIGHTBITS,
        flow_control=None,
        dtr=False,
        rts=False,
        line_ending="0d0a",  # Default CRLF in ASCII hex
        hex_mode=False  # If True, commands are sent as hex strings
    ):
        self.name = name
        self.port = port
        self.baud_rate = baud_rate
        # Parse line ending from ASCII hex string to bytes
        self.line_ending_bytes = self._parse_line_ending(line_ending)
        self.line_ending_str = line_ending  # Keep original for logging
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baud_rate
        self.ser.stopbits = stop_bits
        self.ser.parity = parity
        self.ser.bytesize = data_bits
        if flow_control is not None:
            self.ser.xonxoff = flow_control.get("xon_xoff", False)
            self.ser.rtscts = flow_control.get("rts_cts", False)
            self.ser.dsrdtr = flow_control.get("dsr_dtr", False)
        else:
            self.ser.xonxoff = False
            self.ser.rtscts = False
            self.ser.dsrdtr = False
            
        self.ser.dtr = dtr
        self.ser.rts = rts
        self.ser.open()

        self.lock = threading.Lock()
        self.log_file = None

    def _parse_line_ending(self, line_ending):
        """
        Parse line ending from ASCII hex string to bytes.
        Examples:
        - "0d0a" -> b'\r\n' (CRLF)
        - "0a" -> b'\n' (LF)
        - "0d" -> b'\r' (CR)
        - "00" -> b'\x00' (NULL)
        """
        try:
            # Handle empty string
            if not line_ending or not line_ending.strip():
                raise ValueError("Empty line ending string")
            
            # Remove any spaces or separators
            hex_str = line_ending.replace(" ", "").replace("-", "").replace(":", "")
            
            # Ensure even length (each byte needs 2 hex digits)
            if len(hex_str) % 2 != 0:
                raise ValueError(f"Invalid hex string length: {hex_str}")
            
            # Convert hex pairs to bytes
            result = bytearray()
            for i in range(0, len(hex_str), 2):
                hex_byte = hex_str[i:i+2]
                byte_val = int(hex_byte, 16)
                result.append(byte_val)
            
            return bytes(result)
        except ValueError as e:
            # Fallback to default CRLF if parsing fails
            print(f"Warning: Failed to parse line ending '{line_ending}': {e}. Using default CRLF.")
            return b'\r\n'

    def _parse_hex_command(self, hex_command):
        """
        Parse hex command string to bytes.
        Examples:
        - "48656c6c6f" -> b'Hello'
        - "48 65 6c 6c 6f" -> b'Hello'
        - "48-65-6C-6C-6F" -> b'Hello'
        """
        try:
            # Remove any spaces, dashes, or colons
            hex_str = hex_command.replace(" ", "").replace("-", "").replace(":", "")
            
            # Ensure even length (each byte needs 2 hex digits)
            if len(hex_str) % 2 != 0:
                raise ValueError(f"Invalid hex string length: {hex_str}")
            
            # Convert hex pairs to bytes
            result = bytearray()
            for i in range(0, len(hex_str), 2):
                hex_byte = hex_str[i:i+2]
                byte_val = int(hex_byte, 16)
                result.append(byte_val)
            
            return bytes(result)
        except ValueError as e:
            # If parsing fails, log error and return empty bytes
            CommonUtils.print_log_line(f"Error: Failed to parse hex command '{hex_command}': {e}")
            return b''

    def send_command(self, command, timeout, hex_mode=False, expected_responses=None):
        """
        Send command and read response with smart matching.
        
        Args:
            command: Command string to send
            timeout: Maximum wait time in seconds
            hex_mode: If True, parse command as hex string
            expected_responses: List of expected response strings to match (in order)
            
        Returns:
            dict with keys:
                - success: bool, True if all expected responses matched or no expectations
                - response: str, full response text (newline-separated)
                - matched: list of matched expected responses
                - elapsed_time: float, time taken to get response
        """
        start_time = time.time()
        
        # Send command
        with self.lock:
            if command:
                # Convert command to bytes based on hex_mode
                if hex_mode:
                    command_bytes = self._parse_hex_command(command) + self.line_ending_bytes
                else:
                    command_bytes = command.encode("utf-8") + self.line_ending_bytes
                
                self.ser.write(command_bytes)
                self.ser.flush()
                
                timestamp = self._get_timestamp()
                log_line = f"({timestamp})---> {command}"
                self.write_to_log(log_line)

        # Read response with expectation matching
        raw_response = []
        buffer = bytearray()
        matched_expectations = []
        expected_responses = expected_responses or []
        next_expected_idx = 0  # Track which expected response to match next
        
        # max_timeout = min(timeout, 300)  # Cap at 300 seconds
        max_timeout = timeout
        check_interval = 0.01  # 10ms check interval
        
        while (time.time() - start_time) < max_timeout:
            try:
                with self.lock:
                    if self.ser.in_waiting > 0:
                        chunk = self.ser.read(min(self.ser.in_waiting, 512))
                        buffer.extend(chunk)
                
                # Process complete lines from buffer
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    
                    if line.strip():
                        data = CommonUtils.force_decode(line.strip())
                        timestamp = self._get_timestamp()
                        log_line = f"[{timestamp}] {data}"
                        
                        # Write to log immediately
                        self.write_to_log(log_line)
                        raw_response.append(data)
                        
                        # Check if this line matches the next expected response
                        if next_expected_idx < len(expected_responses):
                            expected = expected_responses[next_expected_idx]
                            if expected in data:
                                matched_expectations.append(expected)
                                next_expected_idx += 1
                                
                                # If all expectations matched, wait a bit for trailing data then exit
                                if next_expected_idx >= len(expected_responses):
                                    time.sleep(0.05)  # Small delay to catch trailing data
                                    if self.ser.in_waiting > 0:
                                        with self.lock:
                                            chunk = self.ser.read(min(self.ser.in_waiting, 512))
                                            buffer.extend(chunk)
                                    break
                
                # Early exit if all expectations matched
                if expected_responses and next_expected_idx >= len(expected_responses):
                    break
                    
                time.sleep(check_interval)
                
            except serial.SerialException as e:
                CommonUtils.print_log_line(f"Serial error in send_command: {e}")
                break
            except Exception as e:
                CommonUtils.print_log_line(f"Unexpected error in send_command: {e}")
                break
        
        # Process any remaining data in buffer
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if line.strip():
                data = CommonUtils.force_decode(line.strip())
                timestamp = self._get_timestamp()
                log_line = f"[{timestamp}] {data}"
                self.write_to_log(log_line)
                raw_response.append(data)
        
        # Handle incomplete line in buffer
        if buffer.strip():
            data = CommonUtils.force_decode(buffer.strip())
            timestamp = self._get_timestamp()
            log_line = f"[{timestamp}] {data}"
            self.write_to_log(log_line)
            raw_response.append(data)
        
        elapsed_time = time.time() - start_time
        response_text = "\n".join(raw_response) if raw_response else ""
        
        # Determine success
        if expected_responses:
            success = (next_expected_idx >= len(expected_responses))
        else:
            success = bool(raw_response)  # Success if we got any response
        
        return {
            "success": success,
            "response": response_text,
            "matched": matched_expectations,
            "elapsed_time": elapsed_time
        }
    
    def _get_timestamp(self):
        """Generate formatted timestamp string"""
        return (
            time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
            + f":{int((time.time() % 1) * 1000):03d}"
        )

    def write_to_log(self, message):
        if self.log_file:
            lines = message.splitlines()
            for line in lines:
                self.log_file.write(line + "\n")
                self.log_file.flush()

    def close(self):
        if self.log_file:
            self.log_file.close()
        self.ser.close()

    def get_status(self):
        """Get device status for debugging"""
        try:
            return {
                "name": self.name,
                "port": self.port,
                "serial_open": self.ser.is_open if hasattr(self, 'ser') else False,
                "in_waiting": self.ser.in_waiting if hasattr(self, 'ser') and self.ser.is_open else 0,
                "log_file_open": self.log_file is not None and not self.log_file.closed if self.log_file else False,
                "lock_locked": self.lock.locked() if hasattr(self, 'lock') else False
            }
        except Exception as e:
            return {
                "name": self.name,
                "port": self.port,
                "error": str(e)
            }

    def _sanitize_filename(self, filename):
        """
        Sanitize filename to be safe for both Windows and Linux.
        Removes path separators and Windows reserved names.
        """
        # Windows reserved names
        windows_reserved = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
        
        # Remove or replace problematic characters
        # Replace path separators with underscores
        safe_name = filename.replace('/', '_').replace('\\', '_')
        
        # Replace other problematic characters
        safe_name = re.sub(r'[<>:"|?*]', '_', safe_name)
        
        # Remove control characters
        safe_name = re.sub(r'[\x00-\x1f\x7f-\x9f]', '_', safe_name)
        
        # Handle Windows reserved names
        name_upper = safe_name.upper()
        if name_upper in windows_reserved:
            safe_name = f"device_{safe_name}"
        
        # Remove leading/trailing dots and spaces
        safe_name = safe_name.strip('. ')
        
        # Ensure the name is not empty
        if not safe_name:
            safe_name = "device_unknown"
            
        return safe_name

    def setup_logging(self, log_dir):
        """Setup logging for this device with safe filename."""
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        safe_port_name = self._sanitize_filename(self.port)
        log_filename = f"{self.name}_{safe_port_name}.log"
        log_path = os.path.join(log_dir, log_filename)
        
        self.log_file = open(log_path, "w", encoding="utf-8")
        return log_path

from typing import List, Optional, Union
import time
import sys
import threading
import serial
import re
import os
from collections import deque
from utils.common import CommonUtils
from components.Logger import get_logger, AutoComLogger

logger: AutoComLogger = get_logger("AutoCom")


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
        hex_mode=False,  # If True, commands are sent as hex strings
    ):
        self.name = name
        self.port = port
        self.baud_rate = baud_rate
        # Parse line ending from ASCII hex string to bytes
        self.line_ending_bytes = self._parse_line_ending(line_ending)
        self.line_ending_str = line_ending  # Keep original for logging

        # Serial port setup
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

        # Threading and synchronization

        self.lock = threading.Lock()  # For serial port access
        self.logging_active = threading.Event()  # Control logging thread
        self.logging_active.set()  # Start with logging active
        self.command_in_progress = (
            threading.Event()
        )  # Signal when command is being sent
        self.log_thread = None
        self.shutdown_flag = False
        # Logging
        self.log_file = None

        self.response_buffer = deque()  # Buffer for command responses
        # (timestamp_str, data_bytes) — preserves real arrival time for chronological log replay
        self.pending_rx_buffer: deque[tuple[str, bytes]] = deque()
        self.pending_logged_lines = deque()  # Kept for compatibility (unused when buffer_background=True)
        self.buffer_background = True
        self._logging_chunk_buffer = bytearray()  # Accumulates partial lines between logging thread pauses
        self.last_iteration_success = None  # Track result of last iteration
        # Try to open the serial port and handle common failures (e.g. permission, not found)
        try:
            self.ser.open()
            self.open_failed = False

            # Start continuous logging thread
            self._start_logging_thread()
        except serial.SerialException as e:
            logger.log_session_start(
                f"<!> Failed to open serial port for device '{self.name}' (port: {self.port})"
            )
            # Mark that opening failed so callers can handle it gracefully
            self.open_failed = True
            raise RuntimeError(
                f"Failed to open serial port for device '{self.name}' (port: {self.port})"
            ) from e
        except Exception as e:
            logger.log_session_start(
                f"Unexpected error opening serial port for device '{self.name}' (port: {self.port}): {e}"
            )
            self.open_failed = True
            raise RuntimeError(
                f"Unexpected error opening serial port for device '{self.name}': {e}"
            ) from e

    def _start_logging_thread(self):
        """Start the continuous logging thread"""
        self.log_thread = threading.Thread(target=self._continuous_logging, daemon=True)
        self.log_thread.start()

    def _continuous_logging(self):
        """Continuous logging thread function

        Background reader that buffers serial output between steps.
        When send_command starts, logging_active is cleared and the thread
        flushes its in-flight chunk buffer into pending_rx_buffer before pausing.
        """
        while not self.shutdown_flag:
            try:
                # Check if logging should be paused (during command execution)
                if not self.logging_active.is_set():
                    self._flush_pending_chunk_buffer()
                    time.sleep(0.01)
                    continue

                # Only read from serial if no command is in progress
                if not self.command_in_progress.is_set():
                    with self.lock:
                        if self.ser.is_open and self.ser.in_waiting > 0:
                            chunk = self.ser.read(min(self.ser.in_waiting, 512))
                            self._logging_chunk_buffer.extend(chunk)

                # Process complete lines from the instance buffer
                while b"\n" in self._logging_chunk_buffer:
                    line, self._logging_chunk_buffer = \
                        self._logging_chunk_buffer.split(b"\n", 1)
                    if line.strip():
                        self._process_log_line(line.strip())

                # Flush oversized partial data to avoid memory growth
                if self._logging_chunk_buffer and len(self._logging_chunk_buffer) > 1024:
                    self._process_log_line(bytes(self._logging_chunk_buffer))
                    self._logging_chunk_buffer = bytearray()

                time.sleep(0.01)

            except Exception as e:
                logger.log_session_start(f"Logging thread error: {e}")
                time.sleep(0.1)

        # Process any remaining data before shutdown
        if buffer:
            self._process_log_line(bytes(buffer))

    def _process_log_line(self, data_bytes):
        """Process and log a line of data from the serial device.

        When buffer_background=True, data arriving between steps is stored
        in pending_rx_buffer as (timestamp, bytes) tuples so that the next
        send_command can replay it in chronological order with the correct
        original arrival timestamps.
        """
        try:
            if self.buffer_background:
                ts = self._get_timestamp()
                with self.lock:
                    self.pending_rx_buffer.append((ts, data_bytes.strip() + b"\n"))
                return

            data = CommonUtils.force_decode(data_bytes)
            timestamp = self._get_timestamp()
            log_line = f"[{timestamp}] {data}"

            # Write to log file
            if self.log_file and not self.log_file.closed:
                self.write_to_log(log_line)

            with self.lock:
                self.pending_logged_lines.append(data)

        except Exception as e:
            logger.log_session_start(f"Error processing log line: {e}")

    def _flush_pending_chunk_buffer(self):
        """Flush any data still sitting in the logging thread's chunk buffer
        into pending_rx_buffer before send_command takes over."""
        if self._logging_chunk_buffer:
            data = bytes(self._logging_chunk_buffer)
            if data.strip():
                ts = self._get_timestamp()
                with self.lock:
                    self.pending_rx_buffer.append((ts, data.strip() + b"\n"))
            self._logging_chunk_buffer = bytearray()

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
                hex_byte = hex_str[i : i + 2]
                byte_val = int(hex_byte, 16)
                result.append(byte_val)

            return bytes(result)
        except ValueError as e:
            # Fallback to default CRLF if parsing fails
            logger.log_step_error(
                f"Warning: Failed to parse line ending '{line_ending}': {e}. Using default CRLF."
            )
            return b"\r\n"

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
                hex_byte = hex_str[i : i + 2]
                byte_val = int(hex_byte, 16)
                result.append(byte_val)

            return bytes(result)
        except ValueError as e:
            # If parsing fails, log error and return empty bytes
            logger.log_step_error(
                f"Error: Failed to parse hex command '{hex_command}': {e}"
            )
            return b""

    def send_command(
        self,
        command: str,
        timeout: float,
        hex_mode: bool = False,
        expected_responses: List[str] = [],
    ) -> dict:
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

        # If the serial port failed to open at init, return a controlled failure
        if getattr(self, "open_failed", False) or not (
            hasattr(self, "ser") and getattr(self.ser, "is_open", False)
        ):
            logger.log_session_start(
                f"Serial port not open for device '{self.name}' (port: {self.port}), cannot send command: {command}"
            )
            return {
                "success": False,
                "response": "",
                "matched": [],
                "elapsed_time": 0.0,
            }

        try:
            # Step 1. Pause continuous logging thread and flush its chunk buffer
            self.logging_active.clear()
            time.sleep(0.05)  # Small delay to ensure logging thread pauses
            self._flush_pending_chunk_buffer()

            # Step 2. Clear response buffer and set command in progress flag
            self.response_buffer.clear()
            self.command_in_progress.set()

            # Step 3. Extract pending entries with timestamps and write to log
            #         in CHRONOLOGICAL order (original arrival timestamps) BEFORE
            #         writing the command marker. This ensures the device log
            #         correctly reflects real-world serial output order.
            raw_response: list[str] = []
            pending_bytes = bytearray()  # Raw bytes for matching
            with self.lock:
                while self.pending_rx_buffer:
                    ts, data = self.pending_rx_buffer.popleft()
                    decoded = CommonUtils.force_decode(data)
                    self.write_to_log(f"[{ts}] {decoded.strip()}")
                    pending_bytes.extend(data)

            # Parse pending data into decoded lines for matching
            while b"\n" in pending_bytes:
                line, pending_bytes = pending_bytes.split(b"\n", 1)
                if line.strip():
                    raw_response.append(CommonUtils.force_decode(line.strip()))

            # Step 3b. Send command (or log empty command marker)
            with self.lock:
                if command:
                    # Convert command to bytes based on hex_mode
                    if hex_mode:
                        command_bytes = (
                            self._parse_hex_command(command) + self.line_ending_bytes
                        )
                    else:
                        command_bytes = command.encode("utf-8") + self.line_ending_bytes

                    self.ser.write(command_bytes)
                    self.ser.flush()

                    timestamp = self._get_timestamp()
                    log_line = f"({timestamp})---> {command}"
                    self.write_to_log(log_line)
                else:
                    # If command is empty, just log that
                    timestamp = self._get_timestamp()
                    log_line = f"({timestamp})---> <EMPTY COMMAND>"
                    self.write_to_log(log_line)

            # Step 4. Initialize matching state
            buffer = bytearray()  # Only new data from serial goes here
            matched_all = False
            matched_expectations: list[str] = []
            expected_responses = expected_responses or []
            next_expected_idx = 0

            # Pre-check pending data against expected responses
            if raw_response and expected_responses:
                for data in raw_response:
                    if next_expected_idx < len(expected_responses):
                        expected = expected_responses[next_expected_idx]
                        if expected in data:
                            matched_expectations.append(expected)
                            next_expected_idx += 1
                if next_expected_idx >= len(expected_responses):
                    matched_all = True

            max_timeout = timeout
            check_interval = 0.01  # 10ms check interval

            while not matched_all and (time.time() - start_time) < max_timeout:
                try:
                    # Read from serial port directly (since logging thread is paused)
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

                                    # If all expectations matched, stop immediately and
                                    # leave remaining bytes for the next step.
                                    if next_expected_idx >= len(expected_responses):
                                        matched_all = True
                                        break

                    if matched_all:
                        break

                    # Handle data in buffer without newline: wait for timeout to confirm it's the last data
                    if buffer and b"\n" not in buffer:
                        # Wait 500ms to see if more data arrives
                        wait_start = time.time()
                        data_received_during_wait = False

                        while (
                            time.time() - wait_start
                        ) < 0.5:  # Wait 500ms for more data
                            with self.lock:
                                if self.ser.in_waiting > 0:
                                    chunk = self.ser.read(min(self.ser.in_waiting, 512))
                                    buffer.extend(chunk)
                                    data_received_during_wait = True
                                    break  # Exit wait loop and process new data

                            time.sleep(0.01)  # Check every 10ms

                        # If timeout occurred with no new data, this is the last incomplete line
                        if not data_received_during_wait and buffer:
                            buffer.extend(b"\n")  # Add newline character

                    # Early exit if all expectations matched
                    if expected_responses and next_expected_idx >= len(
                        expected_responses
                    ):
                        break

                    time.sleep(check_interval)

                except serial.SerialException as e:
                    logger.log_step_error(
                        f"Serial error on device '{self.name}' (port: {self.port}): {e}"
                    )
                    # Attempt to reopen the port 3 times
                    for attempt in range(3):
                        try:
                            if not self.ser.is_open:
                                self.ser.open()
                            break  # Successfully reopened
                        except Exception as reopen_exception:
                            logger.log_step_error(
                                f"Failed to reopen serial port '{self.port}' on attempt {attempt + 1}: {reopen_exception}"
                            )
                            time.sleep(5)  # Wait before retrying
                    sys.exit(1)
                except Exception as e:
                    logger.log_step_error(
                        f"Unexpected error on device '{self.name}' (port: {self.port}): {e}"
                    )
                    sys.exit(1)

            # Step 5. Handle any remaining data in buffer
            if not matched_all:
                # Still haven't matched — process remaining buffer as part of this step's response
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
            elif buffer:
                # matched_all=True — save leftover for the next step
                ts = self._get_timestamp()
                with self.lock:
                    self.pending_rx_buffer.appendleft((ts, bytes(buffer)))
                    # NOTE: appendleft puts it at the *front* of the pending queue
                    # so next step sees this data before anything the background
                    # thread may have read in the brief gap between steps.

            elapsed_time = time.time() - start_time
            response_text = "\n".join(raw_response) if raw_response else ""

            # Determine success
            if expected_responses:
                success = next_expected_idx >= len(expected_responses)
            else:
                success = bool(raw_response)  # Success if we got any response

            return {
                "success": success,
                "response": response_text,
                "matched": matched_expectations,
                "elapsed_time": elapsed_time,
            }

        finally:
            # Step 6. Cleanup - always executed
            # Clear command in progress flag
            self.command_in_progress.clear()
            # Clear command-local response buffer only; pending_rx_buffer is preserved
            # for the next step when we stopped immediately after matching.
            # Resume continuous logging thread
            self.logging_active.set()

    def _write_immediate_log(self, message):
        """Write log immediately (bypasses the logging thread)"""
        if self.log_file:
            self.log_file.write(message + "\n")
            self.log_file.flush()

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

    def mark_iteration(self, iteration_num, total_iterations=None):
        """Mark the end of previous iteration and beginning of a new iteration in the log file

        Args:
            iteration_num: Current iteration number (1-based)
            total_iterations: Total number of iterations (optional, for display as "X/Y")
        """
        separator = "=" * 80

        # Write separator
        self.write_to_log(separator)

        # If this is not the first iteration, print the result of the previous iteration
        if iteration_num > 1 and self.last_iteration_success is not None:
            previous_num = iteration_num - 1
            status = "Passed" if self.last_iteration_success else "Failed"
            if total_iterations:
                previous_marker = f"{'─' * 30} Iteration {previous_num}/{total_iterations} {status} {'─' * 30}"
            else:
                previous_marker = (
                    f"{'─' * 30} Iteration {previous_num} {status} {'─' * 30}"
                )
            self.write_to_log(previous_marker)

        # Print current iteration marker
        if total_iterations:
            current_marker = f"{'─' * 30} Iteration {iteration_num}/{total_iterations} Started {'─' * 30}"
        else:
            current_marker = f"{'─' * 30} Iteration {iteration_num} Started {'─' * 30}"
        self.write_to_log(current_marker)

        # Write separator
        self.write_to_log(separator)

    def set_iteration_result(self, success):
        """Set the result of the current iteration

        Args:
            success: Boolean indicating if the iteration was successful
        """
        self.last_iteration_success = success

    def close(self):
        """Close device and cleanup resources"""
        # Set shutdown flag to stop logging thread
        self.shutdown_flag = True

        # Disable logging to allow thread to exit
        self.logging_active.clear()

        # Wait for logging thread to finish
        if self.log_thread and self.log_thread.is_alive():
            self.log_thread.join(timeout=2)

        # Close log file
        if self.log_file and not self.log_file.closed:
            self.log_file.close()

        # Close serial port
        if self.ser and self.ser.is_open:
            self.ser.close()

    def get_status(self):
        """Get device status for debugging"""
        try:
            return {
                "name": self.name,
                "port": self.port,
                "serial_open": self.ser.is_open if hasattr(self, "ser") else False,
                "in_waiting": (
                    self.ser.in_waiting
                    if hasattr(self, "ser") and self.ser.is_open
                    else 0
                ),
                "log_file_open": (
                    self.log_file is not None and not self.log_file.closed
                    if self.log_file
                    else False
                ),
                "lock_locked": self.lock.locked() if hasattr(self, "lock") else False,
            }
        except Exception as e:
            return {"name": self.name, "port": self.port, "error": str(e)}

    def _sanitize_filename(self, filename):
        """
        Sanitize filename to be safe for both Windows and Linux.
        Removes path separators and Windows reserved names.
        """
        # Windows reserved names
        windows_reserved = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }

        # Remove or replace problematic characters
        # Replace path separators with underscores
        safe_name = filename.replace("/", "_").replace("\\", "_")

        # Replace other problematic characters
        safe_name = re.sub(r'[<>:"|?*]', "_", safe_name)

        # Remove control characters
        safe_name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "_", safe_name)

        # Handle Windows reserved names
        name_upper = safe_name.upper()
        if name_upper in windows_reserved:
            safe_name = f"device_{safe_name}"

        # Remove leading/trailing dots and spaces
        safe_name = safe_name.strip(". ")

        # Ensure the name is not empty
        if not safe_name:
            safe_name = "device_unknown"

        return safe_name

    def setup_logging(self, log_dir):
        """Setup logging for this device with safe filename."""
        from pathlib import Path

        log_path_obj = Path(log_dir)
        log_path_obj.mkdir(parents=True, exist_ok=True)

        safe_port_name = self._sanitize_filename(self.port)
        log_filename = f"{self.name}_{safe_port_name}.log"
        log_path = log_path_obj / log_filename

        self.log_file = open(log_path, "w", encoding="utf-8")
        return str(log_path)

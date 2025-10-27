import serial
try:
    from utils.common import CommonUtils
    from components.Device import Device
except ModuleNotFoundError:
    from ..utils.common import CommonUtils
    from .Device import Device
import os
import re
import time
import threading
import queue


class MonitorManager:
    """Simplified device monitoring manager"""
    def __init__(self, device, device_name, log_date_dir):
        self.device = device
        self.device_name = device_name
        self.running = False
        self.monitor_thread = None
        self.buffer = bytearray()
        
        # Device data sharing mechanism
        self.lock = threading.RLock()  # Use reentrant lock
        self.latest_data = []  # Store latest received data lines
        self.data_event = threading.Event()  # Event to notify new data
        
        # Data collection during command execution
        self.command_active = False
        self.command_response_data = []
        self.command_complete_event = threading.Event()
        
    def start_monitoring(self):
        """Start monitoring"""
        if self.running:
            return
            
        self.running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name=f"Monitor-{self.device_name}"
        )
        self.monitor_thread.start()
        CommonUtils.print_log_line(f"Monitoring started: {self.device_name}")
        
    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
        CommonUtils.print_log_line(f"Monitoring stopped: {self.device_name}")
        
    def begin_command_capture(self):
        """Begin command data capture"""
        with self.lock:
            self.command_active = True
            self.command_response_data.clear()
            self.command_complete_event.clear()
            
    def end_command_capture(self):
        """End command data capture"""
        with self.lock:
            self.command_active = False
            return list(self.command_response_data)
            
    def wait_for_command_response(self, timeout):
        """Wait for command response"""
        return self.command_complete_event.wait(timeout=timeout)
        
    def get_latest_data(self, clear=False):
        """Get latest data"""
        with self.lock:
            data = list(self.latest_data)
            if clear:
                self.latest_data.clear()
                self.data_event.clear()
            return data
            
    def _monitor_loop(self):
        """Monitor loop - simplified logic"""
        CommonUtils.print_log_line(f"Started monitoring device: {self.device_name}")
        
        while self.running:
            try:
                # Check if there is data to read
                if not self.device.ser.is_open:
                    break
                    
                if self.device.ser.in_waiting > 0:
                    # Read available data
                    data = self.device.ser.read(self.device.ser.in_waiting)
                    self.buffer.extend(data)
                    
                    # Process complete lines
                    while b'\n' in self.buffer:
                        line, self.buffer = self.buffer.split(b'\n', 1)
                        if line.strip():
                            decoded_line = CommonUtils.force_decode(line.strip())
                            self._process_line(decoded_line)
                else:
                    # Sleep briefly when no data
                    time.sleep(0.01)
                    
            except serial.SerialException as e:
                CommonUtils.print_log_line(f"Serial error {self.device_name}: {e}")
                break
            except Exception as e:
                CommonUtils.print_log_line(f"Monitor error {self.device_name}: {e}")
                time.sleep(0.1)
                
        CommonUtils.print_log_line(f"Monitor ended: {self.device_name}")
        
    def _process_line(self, line):
        """Process single line of data"""
        current_time = time.time()
        timestamp = (
            time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime(current_time))
            + f":{int((current_time % 1) * 1000):03d}"
        )
        
        # Write to log file
        log_line = f"[{timestamp}] {line}"
        if self.device.log_file and not self.device.log_file.closed:
            try:
                self.device.log_file.write(log_line + "\n")
                self.device.log_file.flush()
            except Exception as e:
                CommonUtils.print_log_line(f"Failed to write log {self.device_name}: {e}")
        
        # Update data cache
        with self.lock:
            # Keep latest 100 lines of data
            self.latest_data.append(line)
            if len(self.latest_data) > 100:
                self.latest_data.pop(0)
            self.data_event.set()
            
            # If executing command, collect response data
            if self.command_active:
                self.command_response_data.append(line)
                self.command_complete_event.set()


class CommandDeviceDict:
    def __init__(self, dict):
        self.dict = dict
        self.devices = {}
        self.log_date_dir = None
        
        # Simplified monitoring mechanism
        self.monitor_threads = {}  # Track monitor threads
        self.stop_monitoring = threading.Event()  # Global stop signal
        
        # Optimized data sharing mechanism
        self.device_monitors = {}  # device_name -> MonitorManager instance
        
        for device in dict["Devices"]:
            if device["status"] == "enabled":
                parity_map = {
                    "None": serial.PARITY_NONE,
                    "Even": serial.PARITY_EVEN,
                    "Odd": serial.PARITY_ODD,
                    "Mark": serial.PARITY_MARK,
                    "Space": serial.PARITY_SPACE,
                }

                parity_value = device.get("parity", "None")
                parity = parity_map.get(parity_value, serial.PARITY_NONE)

                device_name = device["name"]
                self.devices[device_name] = Device(
                    name=device_name,
                    port=device["port"],
                    baud_rate=device["baud_rate"],
                    stop_bits=device.get("stop_bits", serial.STOPBITS_ONE),
                    parity=parity,
                    data_bits=device.get("data_bits", serial.EIGHTBITS),
                    flow_control=device.get("flow_control"),
                    dtr=device.get("dtr", False),
                    rts=device.get("rts", False),
                    line_ending=device.get("line_ending", "0d0a"),  # Default CRLF in ASCII hex
                )
                
                # Setup logging - 使用环境变量中的日志目录（如果设置了）
                log_dir = os.environ.get('AUTOCOM_DEVICE_LOGS_DIR', 'device_logs')
                self.log_date_dir = os.path.join(log_dir, time.strftime("%Y-%m-%d_%H-%M-%S"))
                log_path = self.devices[device_name].setup_logging(self.log_date_dir)
                
                CommonUtils.set_log_file_path(self.log_date_dir)
                CommonUtils.print_log_line(
                    f"Device {device['name']} connected to port {device['port']}, baud rate {device['baud_rate']}",
                    top_border=True,
                    bottom_border=True,
                )
                
                # If monitoring is enabled
                if device.get("monitor") == True:
                    # Create monitor manager
                    monitor_manager = MonitorManager(
                        self.devices[device_name], 
                        device_name, 
                        self.log_date_dir
                    )
                    self.device_monitors[device_name] = monitor_manager
                    
                    # Replace device's send_command method with wrapper
                    original_send_command = self.devices[device_name].send_command
                    def wrapped_send_command(cmd, timeout, hex_mode=False, expected_responses=None):
                        # Monitor version uses simplified logic, wrap result in dict format
                        result_str = self.send_command_with_monitor(device_name, cmd, timeout, hex_mode, expected_responses, original_send_command)
                        # Wrap string result in dict format for compatibility
                        if isinstance(result_str, dict):
                            return result_str
                        return {
                            "success": bool(result_str and not result_str.startswith("ERROR")),
                            "response": result_str,
                            "matched": expected_responses if expected_responses and result_str else [],
                            "elapsed_time": timeout  # We don't track actual time in monitor version
                        }
                    self.devices[device_name].send_command = wrapped_send_command
                    
                    # Start monitoring
                    monitor_manager.start_monitoring()
                    self.monitor_threads[device_name] = monitor_manager.monitor_thread
                    
                    CommonUtils.print_log_line(
                        f"Device {device['name']} monitoring started",
                        bottom_border=True,
                    )

    def _sanitize_filename(self, filename):
        """
        Clean filename, remove or replace unsafe characters
        Compatible with cross-platform file systems
        """
        # Define unsafe characters (Windows + Unix)
        unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\0']
        
        # Replace unsafe characters with underscores
        sanitized = filename
        for char in unsafe_chars:
            sanitized = sanitized.replace(char, '_')
        
        # Remove control characters (ASCII 0-31)
        sanitized = ''.join(char for char in sanitized if ord(char) >= 32)
        
        # Remove extra underscores and spaces
        sanitized = re.sub(r'[_\s]+', '_', sanitized)
        
        # Remove leading and trailing underscores, dots and spaces
        sanitized = sanitized.strip('_. ')
        
        # Ensure filename is not empty
        if not sanitized:
            sanitized = "unnamed_device"
        
        # Limit filename length (avoid filesystem limitations)
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
        
        return sanitized

    def stop_all_monitoring(self):
        """
        Stop all device monitoring - simplified version
        """
        if self.stop_monitoring.is_set():
            CommonUtils.print_log_line("Monitoring already stopped")
            return
            
        CommonUtils.print_log_line("Stopping all device monitoring...")
        self.stop_monitoring.set()
        
        # Stop all monitors
        for device_name, monitor in self.device_monitors.items():
            monitor.stop_monitoring()
        
        # Wait for all monitor threads to finish
        for device_name, thread in self.monitor_threads.items():
            if thread and thread.is_alive():
                CommonUtils.print_log_line(f"Waiting for {device_name} monitor to stop...")
                thread.join(timeout=2)
                if thread.is_alive():
                    CommonUtils.print_log_line(f"Warning: {device_name} monitor thread did not stop gracefully")
                else:
                    CommonUtils.print_log_line(f"✓ {device_name} monitor stopped")
        
        CommonUtils.print_log_line("All device monitoring stopped")

    def get_monitoring_status(self):
        """Get monitoring status - simplified version"""
        status = {
            "stop_monitoring_set": self.stop_monitoring.is_set(),
            "active_monitors": {}
        }
        
        for device_name, monitor in self.device_monitors.items():
            status["active_monitors"][device_name] = {
                "running": monitor.running,
                "thread_alive": monitor.monitor_thread.is_alive() if monitor.monitor_thread else False,
                "latest_data_count": len(monitor.get_latest_data()),
                "command_active": monitor.command_active
            }
        
        return status

    def test_command_response(self, device_name, command="AT", timeout=5.0):
        """
        Test command response mechanism - simplified version
        """
        CommonUtils.print_log_line(f"Testing device {device_name} command response: {command}")
        
        if device_name not in self.devices:
            return f"ERROR: Device {device_name} not found"
        
        # Check if monitor exists
        if device_name in self.device_monitors:
            monitor = self.device_monitors[device_name]
            if not monitor.running:
                CommonUtils.print_log_line(f"Warning: Device {device_name} monitoring not running")
        
        # Execute command
        start_time = time.time()
        result = self.devices[device_name].send_command(command, timeout)
        end_time = time.time()
        
        CommonUtils.print_log_line(f"Command '{command}' completed in {end_time - start_time:.2f}s")
        CommonUtils.print_log_line(f"Response length: {len(result)} characters")
        CommonUtils.print_log_line(f"Response preview: {result[:100]}{'...' if len(result) > 100 else ''}")
        
        # Check result
        if "ERROR:" in result:
            CommonUtils.print_log_line("❌ Command execution error")
        elif len(result.strip()) == 0:
            CommonUtils.print_log_line("⚠️ Warning: Empty response received")
        else:
            CommonUtils.print_log_line("✅ Command executed successfully")
        
        return result

    def send_command_with_monitor(self, device_name, command, timeout, hex_mode, expected_responses, original_send_command):
        """
        Send command using monitor - simplified version
        Accepts new parameters for compatibility but uses simplified logic
        """
        if device_name not in self.device_monitors:
            # If no monitor, use original method
            return original_send_command(command, timeout, hex_mode, expected_responses)
            
        monitor = self.device_monitors[device_name]
        device = self.devices[device_name]
        
        try:
            # Start data capture
            monitor.begin_command_capture()
            
            # Send command
            with device.lock:
                if command:
                    # Clear old data in serial buffer
                    if device.ser.in_waiting > 0:
                        discarded = device.ser.read(device.ser.in_waiting)
                        CommonUtils.print_log_line(f"Cleared buffer: {len(discarded)} bytes")
                    
                    # Send command (handle hex_mode)
                    if hex_mode:
                        command_bytes = device._parse_hex_command(command) + device.line_ending_bytes
                    else:
                        command_bytes = command.encode("utf-8") + device.line_ending_bytes
                    device.ser.write(command_bytes)
                    device.ser.flush()
                    
                    # Log sent command
                    timestamp = (
                        time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
                        + f":{int((time.time() % 1) * 1000):03d}"
                    )
                    device.write_to_log(f"({timestamp})---> {command}")
            
            # Wait for response
            start_time = time.time()
            response_lines = []
            
            # Adaptive timeout strategy
            check_interval = 0.1  # Check every 100ms
            max_wait_without_data = min(timeout / 3, 2.0)  # Maximum idle time
            last_data_time = start_time
            
            while (time.time() - start_time) < timeout:
                # Wait for new data
                if monitor.wait_for_command_response(check_interval):
                    # Collect all response data
                    new_data = monitor.end_command_capture()
                    monitor.begin_command_capture()  # Restart capture
                    
                    if new_data:
                        response_lines.extend(new_data)
                        last_data_time = time.time()
                    
                # Check if should stop waiting
                time_without_data = time.time() - last_data_time
                if response_lines and time_without_data > max_wait_without_data:
                    CommonUtils.print_log_line(f"Response collection complete, wait time: {time_without_data:.2f}s")
                    break
            
            # Get final response data
            final_data = monitor.end_command_capture()
            response_lines.extend(final_data)
            
            if not response_lines:
                error_msg = f"ERROR: No response for command: {command} (timeout: {timeout}s)"
                CommonUtils.print_log_line(f"No response for command: {command}")
                timestamp = (
                    time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
                    + f":{int((time.time() % 1) * 1000):03d}"
                )
                return f"[{timestamp}] {error_msg}"
            
            # Format response and log
            response_with_timestamp = []
            for line in response_lines:
                timestamp = (
                    time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
                    + f":{int((time.time() % 1) * 1000):03d}"
                )
                response_with_timestamp.append(f"[{timestamp}] {line}")
            
            # Log response
            response_log = "\n".join(response_with_timestamp)
            device.write_to_log(response_log)
            
            # Return raw response (without timestamps)
            return "\n".join(response_lines)
            
        except Exception as e:
            CommonUtils.print_log_line(f"Error sending command: {e}")
            return f"ERROR: Command execution exception: {e}"

    def close_all_devices(self):
        """
        Close all devices and stop monitoring
        """
        self.stop_all_monitoring()
        
        for device_name, device in self.devices.items():
            try:
                device.close()
                CommonUtils.print_log_line(f"Device {device_name} closed")
            except Exception as e:
                CommonUtils.print_log_line(f"Error closing device {device_name}: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatic cleanup"""
        self.close_all_devices()
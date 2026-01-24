import json
import os
import queue
import threading
import time
import shutil
import glob
from threading import RLock
try:
    from utils.common import CommonUtils
except ModuleNotFoundError:
    from ..utils.common import CommonUtils

class DataStore:
    def __init__(self, filename=None, save_interval=5.0, session_id=None, auto_cleanup=True, cleanup_days=7):
        """
        Initialize DataStore with session-based file management
        
        Args:
            filename: Custom filename (optional). If not provided, will use session-based naming
            save_interval: Interval between automatic saves (seconds)
            session_id: Unique session identifier. If not provided, will generate one based on timestamp
            auto_cleanup: Whether to automatically clean up old data files
            cleanup_days: Number of days to keep old data files (default: 7)
        """
        self.data = {}
        self.lock = RLock()
        self.save_interval = save_interval
        self.last_save_time = time.time()
        self.auto_cleanup = auto_cleanup
        self.cleanup_days = cleanup_days
        
        # Generate session ID if not provided
        if session_id is None:
            self.session_id = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        else:
            self.session_id = session_id
        
        # Setup filename with session ID
        if filename is None:
            data_dir = "temps/data_store"
            os.makedirs(data_dir, exist_ok=True)
            self.filename = f"{data_dir}/session_{self.session_id}.json"
        else:
            self.filename = filename
        
        self.backup_filename = f"{self.filename}.backup"
        
        # Optimization: batch saving and incremental updates
        self.dirty_devices = set()
        
        # Queue and thread configuration
        self.save_queue = queue.Queue(maxsize=50)
        self._stop_event = threading.Event()
        self.save_thread = threading.Thread(
            target=self._save_worker,
            name=f"DataStoreSaveWorker_{self.session_id}",
            daemon=True
        )

        # Load data during initialization
        self._load_from_file()
        
        # Perform cleanup if enabled
        if self.auto_cleanup:
            self._cleanup_old_files()
        
        self.save_thread.start()
        
        CommonUtils.print_log_line(f"DataStore initialized for session: {self.session_id}")
        CommonUtils.print_log_line(f"Data file: {self.filename}")

    def _load_from_file(self):
        """Load data with error recovery mechanism"""
        for filepath in [self.filename, self.backup_filename]:
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r") as f:
                        self.data = json.load(f)
                    CommonUtils.print_log_line(f"Successfully loaded data file: {filepath}")
                    return
                except (json.JSONDecodeError, IOError) as e:
                    CommonUtils.print_log_line(f"File {filepath} corrupted: {e}")
                    continue
        
        CommonUtils.print_log_line("No valid data file found, using empty dataset")
        self.data = {}
    
    def get_constant(self, key, default=None):
        """Get a constant value by key"""
        return self.get_data("Constants", key) or default
        
    def _cleanup_old_files(self):
        """Clean up old data files based on cleanup_days setting"""
        try:
            from pathlib import Path
            data_dir = Path(self.filename).parent
            if not data_dir.exists():
                return
            
            current_time = time.time()
            cutoff_time = current_time - (self.cleanup_days * 24 * 3600)
            
            # Find all session data files
            files = list(data_dir.glob("session_*.json"))
            
            cleaned_count = 0
            for filepath in files:
                try:
                    file_time = filepath.stat().st_mtime
                    if file_time < cutoff_time:
                        filepath.unlink()
                        # Also remove backup file if exists
                        backup_file = filepath.with_suffix('.json.backup')
                        if backup_file.exists():
                            os.remove(backup_file)
                        cleaned_count += 1
                except Exception as e:
                    CommonUtils.print_log_line(f"Error cleaning up file {filepath}: {e}")
            
            if cleaned_count > 0:
                CommonUtils.print_log_line(f"Cleaned up {cleaned_count} old data files (older than {self.cleanup_days} days)")
        except Exception as e:
            CommonUtils.print_log_line(f"Error during cleanup: {e}")

    def store_data(self, device_name, variable, value):
        """Store data - optimized version"""
        with self.lock:
            if device_name not in self.data:
                self.data[device_name] = {}
            self.data[device_name][variable] = value
            self.dirty_devices.add(device_name)

        # Batch saving strategy
        current_time = time.time()
        if current_time - self.last_save_time > self.save_interval:
            self._trigger_save()

    def get_data(self, device_name, variable=None):
        """Get data from storage"""
        with self.lock:
            if device_name not in self.data:
                return None
            
            if variable is None:
                # Return all data for the device
                return self.data[device_name].copy()
            else:
                # Return specific variable data
                return self.data[device_name].get(variable, None)

    def get_all_data(self):
        """Get all stored data"""
        with self.lock:
            return {device: variables.copy() for device, variables in self.data.items()}

    def has_data(self, device_name, variable=None):
        """Check if data exists"""
        with self.lock:
            if device_name not in self.data:
                return False
            
            if variable is None:
                return len(self.data[device_name]) > 0
            else:
                return variable in self.data[device_name]

    def delete_data(self, device_name, variable=None):
        """Delete data from storage"""
        with self.lock:
            if device_name not in self.data:
                return False
            
            if variable is None:
                # Delete all data for the device
                del self.data[device_name]
                self.dirty_devices.add(device_name)
            else:
                # Delete specific variable data
                if variable in self.data[device_name]:
                    del self.data[device_name][variable]
                    self.dirty_devices.add(device_name)
                    return True
                return False
            return True

    def _trigger_save(self):
        """Trigger save operation"""
        try:
            dirty_data = self._get_dirty_snapshot()
            if dirty_data:
                save_task = {
                    "data": dirty_data,
                    "devices_to_clear": set(dirty_data.keys())
                }
                self.save_queue.put_nowait(save_task)
                # with self.lock:
                #     self.dirty_devices.clear()
                self.last_save_time = time.time()
        except queue.Full:
            CommonUtils.print_log_line("Save queue is full, skipping this save")

    def _get_dirty_snapshot(self):
        """Get snapshot of changed data"""
        with self.lock:
            return {device: self.data[device].copy() 
                    for device in self.dirty_devices 
                    if device in self.data}

    def _save_worker(self):
        """Background save worker thread - optimized version"""
        CommonUtils.print_log_line("DataStore save worker thread started")
        
        while True:
            try:
                # Check stop condition first
                if self._stop_event.is_set():
                    # Process remaining items in queue before stopping
                    remaining_items = []
                    while True:
                        try:
                            item = self.save_queue.get_nowait()
                            remaining_items.append(item)
                        except queue.Empty:
                            break
                    
                    # Process remaining items
                    for save_task in remaining_items:
                        try:
                            self._incremental_save(save_task["data"])
                            with self.lock:
                                for device in save_task["devices_to_clear"]:
                                    self.dirty_devices.discard(device)
                        except Exception as e:
                            CommonUtils.print_log_line(f"Error processing remaining save task: {e}")
                        finally:
                            self.save_queue.task_done()
                    
                    break
                
                # Get save task with timeout
                save_task = self.save_queue.get(timeout=1.0)
                
                try:
                    self._incremental_save(save_task["data"])
                    
                    with self.lock:
                        # Clear dirty devices after save
                        for device in save_task["devices_to_clear"]:
                            self.dirty_devices.discard(device)
                            
                except Exception as e:
                    CommonUtils.print_log_line(f"Error in incremental save: {e}")
                finally:
                    # Always call task_done to prevent deadlock
                    self.save_queue.task_done()
                    
            except queue.Empty:
                # No tasks to process, continue loop
                continue
            except Exception as e:
                CommonUtils.print_log_line(f"Save worker thread error: {e}")
                # Continue loop to prevent thread death
                continue
                
        CommonUtils.print_log_line("DataStore save worker thread stopped")

    def _incremental_save(self, dirty_data):
        """Incremental save to file"""
        temp_file = f"{self.filename}.tmp"
        
        try:
            # Read existing data
            existing_data = {}
            if os.path.exists(self.filename):
                try:
                    with open(self.filename, "r") as f:
                        existing_data = json.load(f)
                except json.JSONDecodeError:
                    # Try to recover from backup
                    if os.path.exists(self.backup_filename):
                        with open(self.backup_filename, "r") as f:
                            existing_data = json.load(f)

            # Merge dirty data
            for device, variables in dirty_data.items():
                if device in existing_data:
                    existing_data[device].update(variables)
                else:
                    existing_data[device] = variables

            # Atomic write
            with open(temp_file, "w") as f:
                json.dump(existing_data, f, indent=2)
            
            # Create backup and replace main file
            if os.path.exists(self.filename):
                shutil.copy2(self.filename, self.backup_filename)
            
            os.replace(temp_file, self.filename)
            
        except Exception as e:
            CommonUtils.print_log_line(f"Error saving data: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def force_save(self):
        """Force immediate save of all data"""
        # Create a snapshot of current dirty devices to avoid holding lock too long
        dirty_snapshot = None
        with self.lock:
            if self.dirty_devices:
                dirty_snapshot = set(self.dirty_devices)
        
        # Trigger save outside of lock
        if dirty_snapshot:
            try:
                dirty_data = {}
                with self.lock:
                    dirty_data = {device: self.data[device].copy() 
                                for device in dirty_snapshot 
                                if device in self.data}
                
                if dirty_data:
                    save_task = {
                        "data": dirty_data,
                        "devices_to_clear": dirty_snapshot
                    }
                    self.save_queue.put_nowait(save_task)
                    self.last_save_time = time.time()
                    
                    # Wait for save completion with timeout to prevent infinite blocking
                    start_time = time.time()
                    timeout = 10.0  # 10 second timeout
                    
                    while (time.time() - start_time) < timeout:
                        if self.save_queue.empty():
                            break
                        time.sleep(0.1)
                    
                    if not self.save_queue.empty():
                        CommonUtils.print_log_line("Warning: force_save timeout, some data may not be saved immediately")
                        
            except queue.Full:
                CommonUtils.print_log_line("Save queue is full during force_save")

    def get_stats(self):
        """Get storage status statistics"""
        with self.lock:
            return {
                "total_devices": len(self.data),
                "dirty_devices": len(self.dirty_devices),
                "dirty_device_names": list(self.dirty_devices),
                "queue_size": self.save_queue.qsize(),
                "last_save_time": self.last_save_time,
                "worker_thread_alive": self.save_thread.is_alive(),
                "stop_event_set": self._stop_event.is_set()
            }

    def diagnose_blocking(self):
        """Diagnose potential blocking issues"""
        stats = self.get_stats()
        issues = []
        
        if stats["queue_size"] > 40:
            issues.append(f"Queue nearly full: {stats['queue_size']}/50")
        
        if not stats["worker_thread_alive"]:
            issues.append("Worker thread is not alive")
        
        if stats["stop_event_set"]:
            issues.append("Stop event is set")
        
        if len(stats["dirty_devices"]) > 20:
            issues.append(f"Too many dirty devices: {len(stats['dirty_devices'])}")
        
        current_time = time.time()
        if current_time - stats["last_save_time"] > 30:
            issues.append(f"No save for {current_time - stats['last_save_time']:.1f} seconds")
        
        if issues:
            CommonUtils.print_log_line(f"DataStore issues detected: {', '.join(issues)}")
            CommonUtils.print_log_line(f"Stats: {stats}")
        
        return issues
    
    def get_session_id(self):
        """Get current session ID"""
        return self.session_id
    
    def get_filename(self):
        """Get current data filename"""
        return self.filename
    
    @staticmethod
    def list_sessions(data_dir="temps/data_store", days=7):
        """
        List all available sessions within specified days
        
        Args:
            data_dir: Directory containing session data files
            days: Number of days to look back (default: 7)
            
        Returns:
            List of tuples: (session_id, filepath, modified_time)
        """
        from pathlib import Path
        data_path = Path(data_dir)
        if not data_path.exists():
            return []
        
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 3600)
        
        files = list(data_path.glob("session_*.json"))
        
        sessions = []
        for filepath in files:
            try:
                file_time = os.path.getmtime(filepath)
                if file_time >= cutoff_time:
                    # Extract session ID from filename
                    filename = os.path.basename(filepath)
                    session_id = filename.replace("session_", "").replace(".json", "")
                    sessions.append((session_id, filepath, file_time))
            except Exception as e:
                CommonUtils.print_log_line(f"Error reading session file {filepath}: {e}")
        
        # Sort by modified time (newest first)
        sessions.sort(key=lambda x: x[2], reverse=True)
        return sessions
    
    @staticmethod
    def load_session_data(session_id=None, filepath=None, data_dir="temps/data_store"):
        """
        Load data from a specific session
        
        Args:
            session_id: Session ID to load (optional)
            filepath: Direct file path (optional, takes precedence over session_id)
            data_dir: Directory containing session data files
            
        Returns:
            Dictionary of loaded data, or empty dict if not found
        """
        try:
            from pathlib import Path
            if filepath:
                target_file = Path(filepath)
            elif session_id:
                target_file = Path(data_dir) / f"session_{session_id}.json"
            else:
                return {}
            
            if target_file.exists():
                return json.loads(target_file.read_text())
        except Exception as e:
            CommonUtils.print_log_line(f"Error loading session data: {e}")
        
        return {}
    
    @staticmethod
    def query_across_sessions(device_name, variable, data_dir="temps/data_store", days=7):
        """
        Query a variable across all recent sessions
        
        Args:
            device_name: Device name to query
            variable: Variable name to query
            data_dir: Directory containing session data files
            days: Number of days to look back
            
        Returns:
            List of tuples: (session_id, value, timestamp)
        """
        sessions = DataStore.list_sessions(data_dir, days)
        results = []
        
        for session_id, filepath, file_time in sessions:
            data = DataStore.load_session_data(filepath=filepath)
            if device_name in data and variable in data[device_name]:
                value = data[device_name][variable]
                results.append((session_id, value, file_time))
        
        return results

    def stop(self):
        """Stop storage service"""
        CommonUtils.print_log_line("Stopping DataStore service...")
        
        # Force save any pending data with timeout
        try:
            self.force_save()
        except Exception as e:
            CommonUtils.print_log_line(f"Error during final save: {e}")
        
        # Stop worker thread
        self._stop_event.set()
        
        # Wait for worker thread to finish with timeout
        if self.save_thread.is_alive():
            self.save_thread.join(timeout=5.0)
            if self.save_thread.is_alive():
                CommonUtils.print_log_line("Warning: Save worker thread did not stop gracefully")
            else:
                CommonUtils.print_log_line("Save worker thread stopped successfully")
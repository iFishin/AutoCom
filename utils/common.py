#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import List
import os
import re
import sys
import shutil


class CommonUtils:
    """Common utility functions class"""
    
    # Define global variables
    log_file_path = "EXECUTION_LOG.log"
    terminal_width = None  # Auto-detect terminal width
    
    @classmethod
    def set_log_file_path(cls, path: str):
        cls.log_file_path = os.path.join(path, "EXECUTION_LOG.log")
    
    @classmethod
    def get_terminal_width(cls) -> int:
        """Get terminal width, with fallback to 120 if unable to detect"""
        if cls.terminal_width is None:
            try:
                cls.terminal_width = shutil.get_terminal_size((120, 24)).columns
                # Ensure minimum width of 80 and maximum of 200
                cls.terminal_width = max(80, min(cls.terminal_width, 200))
            except Exception:
                cls.terminal_width = 120
        return cls.terminal_width
    
    @classmethod
    def reset_terminal_width(cls):
        """Reset terminal width cache to force re-detection"""
        cls.terminal_width = None
    
    def escape_control_characters(s: str, ignore_crlf: bool = True) -> str:
        r"""
        Escapes control characters and extended ASCII characters in the text to the format \\x{XX}.
        Args:
            s (str): Input string (characters must have Unicode code points in the range 0-255).
            ignore_crlf (bool): Whether to ignore escaping of \r and \n (default is True).
        Returns:
            str: The escaped string (e.g., \\x00, \\xFF).
        """
        return ''.join(
            f'\\x{ord(c):02X}' 
            if (ord(c) <= 0xFF and (ord(c) < 32 or ord(c) >= 127) and not (ignore_crlf and c in '\r\n')) 
            else c 
            for c in s
        )
        
    def remove_control_characters(s: str, ignore_crlf: bool = True) -> str:
        r"""
        Removes control characters and extended ASCII characters from the text.

        Args:
            s (str): Input string (characters must have Unicode code points in the range 0-255).
            ignore_crlf (bool): Whether to ignore the removal of \r and \n (default is False).

        Returns:
            str: The string with control characters removed.
        """
        return ''.join(
            c for c in s 
            if not (ord(c) <= 0xFF and (ord(c) < 32 or ord(c) >= 127) and not (ignore_crlf and c in '\r\n'))
        )
    
    @staticmethod
    def force_decode(bytes_data: bytes, replace_null: str = 'escape') -> str:
        r"""
        Force decode byte data into a string and handle null characters (\x00).

        Args:
        bytes_data (bytes): Byte data to decode.
        replace_null (str): Method to handle null characters, options are 'escape' (escape as \x00), 
                    'remove' (remove null characters), or 'ignore' (ignore null characters).

        Returns:
        str: Decoded string.
        """
        encoding_list = ["utf-8", "gbk", "big5", "latin1"]
        
        for encoding in encoding_list:
            try:
                decoded_str = bytes_data.decode(encoding)
                if replace_null == 'escape':
                    decoded_str = CommonUtils.escape_control_characters(decoded_str)
                elif replace_null == 'remove':
                    decoded_str = CommonUtils.remove_control_characters(decoded_str)
                elif replace_null == 'ignore':
                    pass
                return decoded_str
            except UnicodeDecodeError:
                continue

    @staticmethod
    def format_long_string(s: str, width: int) -> List[str]:
        """Split a long string into multiple lines based on specified width

        Args:
            s: String to be split
            width: Maximum width for each line

        Returns:
            List of split strings
        """
        if not s:
            return [""]
        if len(s) <= width:
            return [s]
        return [s[i : i + width] for i in range(0, len(s), width)]

    @staticmethod
    def get_string_display_width(s: str) -> int:
        """Get the display width of a string, counting emoji as 2 characters wide

        Args:
            s: Input string

        Returns:
            Display width of the string
        """
        # More comprehensive emoji pattern to catch most emoji
        emoji_pattern = re.compile(
            r'[\U0001F300-\U0001F9FF]'  # Emoji range
            r'|[\U0001F600-\U0001F64F]'  # Emoticons
            r'|[\U0001F900-\U0001F9FF]'  # Supplemental symbols
            r'|[\U0001FA00-\U0001FA6F]'  # Chess symbols
            r'|[✅❌📱💬🔄🧾💾]'  # Common single characters
        )
        width = 0
        if not isinstance(s, str):
            return width
        for char in s:
            if emoji_pattern.match(char):
                width += 2
            else:
                width += 1
        return width
    
    @staticmethod
    def _truncate_string(s: str, max_display_width: int) -> str:
        """Truncate a string to a maximum display width, accounting for emoji
        
        Args:
            s: String to truncate
            max_display_width: Maximum display width
            
        Returns:
            Truncated string
        """
        # Same comprehensive emoji pattern as get_string_display_width
        emoji_pattern = re.compile(
            r'[\U0001F300-\U0001F9FF]'
            r'|[\U0001F600-\U0001F64F]'
            r'|[\U0001F900-\U0001F9FF]'
            r'|[\U0001FA00-\U0001FA6F]'
            r'|[✅❌📱💬🔄🧾💾]'
        )
        current_width = 0
        
        for i, char in enumerate(s):
            char_width = 2 if emoji_pattern.match(char) else 1
            if current_width + char_width > max_display_width:
                return s[:i]
            current_width += char_width
        
        return s

    @classmethod
    def print_log_line(
        cls,
        line: str,
        top_border: bool = False,
        bottom_border: bool = False,
        side_border: bool = True,
        border_vertical_char: str = "-",
        border_side_char: str = "|",
        length: int = None,
        align: str = "^",
        log_file: str = None,
        is_print: bool = True,
    ) -> str:
        """Print and save formatted log line with borders
        
        Automatically adapts to terminal width if length is not specified.

        Args:
            line: Line to print
            top_border: Whether to print top border
            bottom_border: Whether to print bottom border
            side_border: Whether to print side border
            border_vertical_char: Character for top and bottom borders
            border_side_char: Side border character
            length: Total length of the line (auto-detect if None)
            align: Text alignment ('^' for center, '<' for left, '>' for right)
            log_file: Log file path (uses default if None)
            is_print: Whether to print to console

        Returns:
            Formatted log line string
        """
        if log_file is None:
            log_file = cls.log_file_path
        
        # Auto-detect terminal width if length not specified
        if length is None:
            length = cls.get_terminal_width()
        
        if top_border:
            border = border_vertical_char * length
            if is_print:
                print(border)
            FileHandler.write_file(log_file, border + "\n", "a")
        
        if side_border:
            content_length = length - len(border_side_char) * 2 - 2
            # Adjust line length for emoji characters
            display_width = cls.get_string_display_width(line)
            
            # If line is too long, truncate with ellipsis
            if display_width > content_length:
                # Truncate and add ellipsis
                truncated_line = cls._truncate_string(line, content_length - 3)
                display_width = cls.get_string_display_width(truncated_line) + 3
                formatted_line = truncated_line + "..."
            else:
                padding = content_length - display_width
                if padding > 0:
                    if align == '^':
                        left_pad = padding // 2
                        right_pad = padding - left_pad
                        formatted_line = ' ' * left_pad + line + ' ' * right_pad
                    elif align == '<':
                        formatted_line = line + ' ' * padding
                    else:  # align == '>'
                        formatted_line = ' ' * padding + line
                else:
                    formatted_line = line
            
            line = f"{border_side_char} {formatted_line} {border_side_char}"
        else:
            # Non-bordered line with width adaptation
            display_width = cls.get_string_display_width(line)
            if display_width > length:
                # Truncate if too long
                line = cls._truncate_string(line, length - 3) + "..."
            else:
                padding = length - display_width
                if padding > 0:
                    if align == '^':
                        left_pad = padding // 2
                        right_pad = padding - left_pad
                        line = ' ' * left_pad + line + ' ' * right_pad
                    elif align == '<':
                        line = line + ' ' * padding
                    else:  # align == '>'
                        line = ' ' * padding + line
        
        if is_print:
            try:
                print(line)
            except UnicodeEncodeError:
                # Handle unicode encoding errors for terminals with limited encoding support
                try:
                    print(line.encode('utf-8', 'replace').decode('utf-8', 'replace'))
                except UnicodeEncodeError:
                    # Last resort: remove problematic characters
                    print(line.encode('ascii', 'replace').decode('ascii'))
        FileHandler.write_file(log_file, line + "\n", "a")
        
        if bottom_border:
            border = border_vertical_char * length
            if is_print:
                print(border)
            FileHandler.write_file(log_file, border + "\n", "a")
        return line


    @staticmethod
    def print_formatted_log(
        time_str: str,
        result: str,
        device: str,
        command_str: str,
        response_str: str,
        first_line: bool = False,
        top_border: bool = False,
        bottom_border: bool = False
    ) -> str:
        """Print and save formatted log line with adaptive column widths

        Args:
            time_str: Time string
            result: Execution result
            device: Device name
            command_str: Command string
            response_str: Response string
            first_line: Whether this is the first line (not used)
            top_border: Whether to print top border
            bottom_border: Whether to print bottom border

        Returns:
            Formatted log line string
        """
        log_file = CommonUtils.log_file_path
        
        # Get terminal width
        width = CommonUtils.get_terminal_width()
        
        # Define column widths as percentages of available space
        # Reserve 13 chars for separators and borders: "| " + " | " (4x) + " |"
        content_width = width - 13
        
        # Proportional column width allocation
        # Time: 14%, Result: 10%, Device: 10%, Command: 32%, Response: 33%
        col_widths = {
            'time': max(13, int(content_width * 0.14)),
            'result': max(9, int(content_width * 0.10)),
            'device': max(10, int(content_width * 0.10)),
            'command': max(25, int(content_width * 0.32)),
            'response': max(25, int(content_width * 0.33))
        }
        
        # Handle empty line
        if not any([time_str, result, device, command_str, response_str]):
            sep = '-' * width
            try:
                print(sep)
            except UnicodeEncodeError:
                try:
                    print(sep.encode('utf-8', 'replace').decode('utf-8', 'replace'))
                except UnicodeEncodeError:
                    print(sep.encode('ascii', 'replace').decode('ascii'))
            FileHandler.write_file(log_file, sep + "\n", "a")
            return sep
        
        # Format each column
        def pad_col(text, col_width, align='left'):
            text = str(text) if text else ""
            # Normalize time format - ensure it's exactly 19 characters (YYYY-MM-DD_HH:MM:SS:mmm)
            if align == 'left' and col_width == col_widths.get('time', 0):
                # This is the time column
                if len(text) > 19:
                    text = text[:19]  # Truncate to standard time format length
                elif len(text) > 0 and len(text) < 19:
                    text = text.ljust(19)  # Pad if shorter
            
            # Get the display width accounting for emoji being 2 chars wide
            display_width = CommonUtils.get_string_display_width(text)
            
            # If text is too long for the column, truncate it
            if display_width > col_width:
                text = CommonUtils._truncate_string(text, col_width - 1)
                display_width = CommonUtils.get_string_display_width(text)
            
            # Calculate padding needed based on display width, not character count
            pad_needed = max(0, col_width - display_width)
            
            if align == 'center':
                left_pad = pad_needed // 2
                right_pad = pad_needed - left_pad
                return ' ' * left_pad + text + ' ' * right_pad
            elif align == 'right':
                return ' ' * pad_needed + text
            else:  # left
                return text + ' ' * pad_needed
        
        # Build row
        row = '| {} | {} | {} | {} | {} |'.format(
            pad_col(time_str or "", col_widths['time'], 'left'),
            pad_col(result or "", col_widths['result'], 'center'),
            pad_col(device or "", col_widths['device'], 'center'),
            pad_col(command_str or "", col_widths['command'], 'left'),
            pad_col(response_str or "", col_widths['response'], 'left')
        )
            
        try:
            if top_border:
                print('-' * len(row))
            print(row)
            if bottom_border:
                print('-' * len(row))
        except UnicodeEncodeError:
            try:
                print(row.encode('utf-8', 'replace').decode('utf-8', 'replace'))
            except UnicodeEncodeError:
                print(row.encode('ascii', 'replace').decode('ascii'))
        FileHandler.write_file(log_file, row + "\n", "a")
        return row

    @staticmethod
    def check_ordered_responses(response: str, expected_responses: List[str]) -> bool:
        """Check if expected responses appear in order within the response string

        Args:
            response: Complete response string
            expected_responses: List of expected response strings

        Returns:
            True if all expected responses appear in order, False otherwise
        """
        if not expected_responses:
            return True
        start = 0
        for expected in expected_responses:
            start = response.find(expected, start)
            if start == -1:
                return False
            start += len(expected)
        return True

    @staticmethod
    def parse_variables_from_str(s: str) -> List[str]:
        """Parse variables enclosed in curly braces from a string

        Args:
            s: Input string containing variables in {variable_name} format

        Returns:
            List of variable names found in the string
        """
        pattern = re.compile(r'\{(\w+|_)\}')
        found_variables = re.findall(pattern, s)
        return found_variables
    
    @staticmethod
    def process_variables(param_value: str, data_store: object = None, device_name: str = None) -> str:
        """Process variables in a string and handle interactive input for empty values
        
        Args:
            param_value: String that may contain variables like ${VAR}
            data_store: DataStore instance to get/store variable values
            device_name: Optional device name for retrieving device-specific variables
            
        Returns:
            String with all variables replaced with their values
        """
        if not isinstance(param_value, str):
            return param_value
            
        vars = CommonUtils.parse_variables_from_str(param_value)
        if not vars:
            return param_value
            
        var_values = {}
        for var in vars:
            # 优先从 Constants 获取值
            if data_store:
                var_value = data_store.get_constant(var)
                if var_value is not None:
                    if var_value != "":
                        var_values[var] = var_value
                        continue
                    else:  # 空值，需要用户输入
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                value = input(f"Please enter value for {var}: ").strip()
                                
                                if not value:  # 如果输入为空
                                    if attempt < max_retries - 1:
                                        CommonUtils.print_log_line(f"Value cannot be empty. Please try again ({attempt + 1}/{max_retries})")
                                        continue
                                    else:
                                        CommonUtils.print_log_line(f"❌ No valid value provided for {var} after {max_retries} attempts")
                                        sys.exit(1)
                                
                                # 保存输入的值到 Constants
                                data_store.store_data("Constants", var, value)
                                var_values[var] = value
                                CommonUtils.print_log_line(f"✓ Stored {var} = {value}")
                                break
                                
                            except KeyboardInterrupt:
                                CommonUtils.print_log_line("\n❌ Input cancelled by user")
                                sys.exit(1)
                            except Exception as e:
                                if attempt < max_retries - 1:
                                    CommonUtils.print_log_line(f"Error: {e}. Please try again ({attempt + 1}/{max_retries})")
                                    continue
                                else:
                                    CommonUtils.print_log_line(f"❌ Failed to get value for {var} after {max_retries} attempts: {e}")
                                    sys.exit(1)
                        continue
                        
                # 尝试从设备变量获取值
                if device_name:
                    var_value = data_store.get_data(device_name, var)
                    if var_value is not None:
                        var_values[var] = var_value
                        continue
                    
            # 如果找不到变量
            CommonUtils.print_log_line(f"❌ Variable '{var}' not found in Constants")
            CommonUtils.print_log_line("   Note: Variables must be defined in Constants block")
            sys.exit(1)
            
        return CommonUtils.replace_variables_from_str(param_value, vars, **var_values)
        
    @staticmethod
    def replace_variables_from_str(s: str, found_variables: List[str], **kwargs) -> str:
        """Replace variables in a string with provided values

        Args:
            s: Input string containing variables in {variable_name} format
            found_variables: List of variable names to be replaced
            **kwargs: Key-value pairs where key is variable name and value is replacement

        Returns:
            String with variables replaced by their values, or original {variable_name} if value is None
        """
        for variable_name in found_variables:
            placeholder = f'{{{variable_name}}}'
            if variable_name in kwargs and kwargs[variable_name] is not None:
                replacement = str(kwargs[variable_name])
                s = s.replace(placeholder, replacement)
        return s

class FileHandler:
    """File operation utility class"""

    @staticmethod
    def read_file(file_path: str, encoding: str = "utf-8") -> str:
        """Read file content

        Args:
            file_path: Path to the file
            encoding: File encoding, defaults to utf-8

        Returns:
            File content string, returns None if error occurs
        """
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, file_path)

            if not os.path.exists(full_path):
                print(f"File not found: {full_path}")
                return None

            try:
                with open(full_path, "r", encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                print(
                    f"Encoding error when reading file. Trying with different encoding..."
                )
                with open(full_path, "r", encoding="latin-1") as f:
                    return f.read()
        except Exception as e:
            print(f"Error reading file {full_path}: {str(e)}")
            return None

    @staticmethod
    def write_file(
        file_path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> bool:
        """Write content to file

        Args:
            file_path: Path to the file
            content: Content to write
            mode: Write mode, defaults to 'w' for overwrite
            encoding: File encoding, defaults to utf-8

        Returns:
            True if write successful, False if failed
        """
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, file_path)

            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            try:
                with open(full_path, mode, encoding=encoding) as f:
                    f.write(content)
                return True
            except UnicodeEncodeError:
                print(
                    f"Encoding error when writing file. Trying with different encoding..."
                )
                with open(full_path, mode, encoding="latin-1") as f:
                    f.write(content)
                return True
        except Exception as e:
            print(f"Error writing to file {full_path}: {str(e)}")
            return False

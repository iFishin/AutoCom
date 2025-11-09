#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import List
import os
import re
import sys


class CommonUtils:
    """Common utility functions class"""
    
    # Define global variables
    log_file_path = "EXECUTION_LOG.log"
    
    @classmethod
    def set_log_file_path(cls, path: str):
        cls.log_file_path = os.path.join(path, "EXECUTION_LOG.log")
    
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
        emoji_pattern = re.compile(r'[\U00010000-\U0010FFFF]|[✅❌]')
        width = 0
        if not isinstance(s, str):
            return width
        for char in s:
            if emoji_pattern.match(char):
                width += 2
            else:
                width += 1
        return width

    @classmethod
    def print_log_line(
        cls,
        line: str,
        top_border: bool = False,
        bottom_border: bool = False,
        side_border: bool = True,
        border_vertical_char: str = "-",
        border_side_char: str = "|",
        length: int = 120,
        align: str = "^",
        log_file: str = None,
        is_print: bool = True,
    ) -> str:
        """Print and save formatted log line with borders

        Args:
            line: Line to print
            top_border: Whether to print top border
            bottom_border: Whether to print bottom border
            side_border: Whether to print side border
            border_vertical_char: Character for top and bottom borders
            border_side_char: Side border character
            length: Total length of the line
            align: Text alignment ('^' for center, '<' for left, '>' for right)

        Returns:
            Formatted log line string
        """
        if log_file is None:
            log_file = cls.log_file_path

        if top_border:
            border = border_vertical_char * length
            print(border)
            FileHandler.write_file(log_file, border + "\n", "a")
        
        if side_border:
            content_length = length - len(border_side_char) * 2 - 2
            # Adjust line length for emoji characters
            display_width = cls.get_string_display_width(line)
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
            # Similar adjustment for non-bordered lines
            display_width = cls.get_string_display_width(line)
            padding = length - display_width
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
            line = formatted_line
        
        if is_print:
            print(line)
        FileHandler.write_file(log_file, line + "\n", "a")
        
        if bottom_border:
            border = border_vertical_char * length
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
    ) -> str:
        """Print and save formatted log line

        Args:
            time_str: Time string
            result: Execution result
            device: Device name
            command_str: Command string
            response_str: Response string
            first_line: Whether this is the first line

        Returns:
            Formatted log line string
        """
        # Define field widths
        fields = [
            (time_str, 25),
            (result, 10),
            (device, 10),
            (command_str, 25),
            (response_str, 30)
        ]
        if not first_line:
            # For continuation lines, replace time and result with spaces
            fields[0] = (" " * 25, 25)
            fields[1] = (" " * 10, 10)
            # Replace empty device with space
            if not device.strip():
                fields[2] = (" " * 10, 10)

        # Format each field with center alignment
        formatted_fields = []
        for content, width in fields:
            display_width = CommonUtils.get_string_display_width(content)
            padding = max(0, width - display_width)
            left_pad = padding // 2
            right_pad = padding - left_pad
            formatted_fields.append(f"{' ' * left_pad}{content}{' ' * right_pad}")
        # Join fields with separators
        log_content = " | ".join(formatted_fields)
        
        return CommonUtils.print_log_line(log_content, side_border=True)

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

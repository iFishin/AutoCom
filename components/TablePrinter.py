import shutil
import re
from typing import List, Optional, Any, Dict, Union
from pathlib import Path
from wcwidth import wcswidth, wcwidth

class TablePrinter:
    """统一的表格打印器"""
    log_file_path = None
    
    def __init__(self, 
                 headers: List[str],
                 max_width: int = 200,
                 min_width: int = 80,
                 auto_terminal: bool = True):
        """
        初始化表格打印器
        
        Args:
            headers: 表头列表
            max_width: 最大宽度
            min_width: 最小宽度
            auto_terminal: 是否自动使用终端宽度
        """
        self.headers = headers
        self.max_width = max_width
        self.min_width = min_width
        self.auto_terminal = auto_terminal
        self.widths = self.calculate_column_widths()
        self.data = []
        self.terminal_width = None
        
        if auto_terminal:
            self.terminal_width = self._terminal_width()

    def _terminal_width(self) -> int:
        """统一获取终端宽度（实例方法，考虑 min/max）"""
        try:
            w = shutil.get_terminal_size((self.min_width, 24)).columns
            return max(self.min_width, min(w, self.max_width))
        except Exception:
            return self.min_width

    def _display_width(self, text: str) -> int:
        """返回字符串的显示宽度，失败时回退到字符长度"""
        try:
            w = wcswidth(text)
            return w if w >= 0 else len(text)
        except Exception:
            return len(text)

    def _truncate_text_to_width(self, text: str, width: int, ellipsis: str = '..') -> str:
        """按显示宽度截断文本，保留尾部省略符号"""
        if width <= 0:
            return ''
        ell_w = self._display_width(ellipsis)
        target = max(0, width - ell_w)
        cur = 0
        cut_index = 0
        for j, ch in enumerate(text):
            w = wcwidth(ch)
            if w < 0:
                w = 1
            if cur + w > target:
                cut_index = j
                break
            cur += w
        else:
            cut_index = len(text)
        if cut_index >= len(text):
            return text
        return text[:cut_index] + ellipsis
    
    def get_available_width(self) -> int:
        """获取可用宽度（考虑边框）"""
        if self.auto_terminal:
            width = self._terminal_width()
        else:
            width = self.max_width
        
        # 减去边框和分隔符占用的宽度
        # 格式: "| " + " | ".join(cells) + " |"
        border_overhead = len(self.headers) * 2 + 3  # 每个单元格左右空格 + 边框字符
        return width - border_overhead
    
    def calculate_column_widths(self, 
                                  mode: str = "proportional",
                                  custom_ratios: Optional[List[float]] = None,
                                  fixed_widths: Optional[List[int]] = None) -> List[int]:
        """
        计算列宽
        
        Args:
            mode: 计算模式
                - "equal": 等宽分配
                - "proportional": 按比例分配（需要 custom_ratios）
                - "content": 基于内容自适应
                - "fixed": 固定宽度（需要 fixed_widths）
            custom_ratios: 自定义比例列表，和为1
            fixed_widths: 固定宽度列表
        
        Returns:
            列宽列表
        """
        total_width = self.get_available_width()
        
        if mode == "fixed" and fixed_widths:
            return fixed_widths
        
        if mode == "proportional" and custom_ratios:
            widths = [int(total_width * ratio) for ratio in custom_ratios]
            # 调整舍入误差
            diff = total_width - sum(widths)
            if diff != 0:
                widths[-1] += diff
            return widths
        
        if mode == "equal":
            col_width = total_width // len(self.headers)
            return [col_width] * len(self.headers)
        
        if mode == "content":
            # 基于内容自适应
            return self._calculate_content_based_widths(total_width)
        
        # 默认使用比例分配（基于表头长度）
        return self._calculate_header_based_widths(total_width)
    
    def _calculate_header_based_widths(self, total_width: int) -> List[int]:
        """基于表头长度计算宽度"""
        # 获取每个表头的显示宽度
        header_widths = [ self._display_width(str(h)) for h in self.headers ]
        total_header_width = sum(header_widths)
        
        if total_header_width >= total_width:
            # 等分
            return [total_width // len(self.headers)] * len(self.headers)
        
        # 按比例分配
        widths = [int(total_width * (w / total_header_width)) for w in header_widths]
        diff = total_width - sum(widths)
        if diff != 0:
            widths[-1] += diff
        return widths
    
    def _calculate_content_based_widths(self, total_width: int) -> List[int]:
        """基于所有内容计算最优宽度"""
        all_rows = [self.headers] + self.data
        
        # 使用文件内 CommonUtils
        max_widths = []
        
        for col_idx in range(len(self.headers)):
            max_len = 0
            for row in all_rows:
                if col_idx < len(row):
                    cell_text = str(row[col_idx])
                    cell_width = self._display_width(cell_text)
                    max_len = max(max_len, cell_width)
            max_widths.append(min(max_len, total_width // 2))  # 限制最大宽度
        
        # 如果总宽度超出，按比例压缩
        total_max = sum(max_widths)
        if total_max > total_width:
            widths = [int(total_width * (w / total_max)) for w in max_widths]
            diff = total_width - sum(widths)
            if diff != 0:
                widths[-1] += diff
            return widths
        
        return max_widths
    
    def add_row(self, row: List[Any]) -> None:
        """添加一行数据"""
        self.data.append(row)
    
    def add_banner(self, banner: str) -> None:
        """添加一个横幅（占满整行）"""
        self.data.append([banner] + [''] * (len(self.headers) - 1))
    
    def print_table(self, 
                    log_file: Optional[str] = None,
                    top_border: bool = True,
                    bottom_border: bool = True,
                    is_print: bool = True) -> str:
        """
        打印整个表格
        
        Returns:
            完整的表格字符串
        """
        if not self.headers:
            return ""
        
        # 计算列宽
        widths = self.calculate_column_widths()
        
        # 构建表格
        lines = []
        
        # 上边框
        if top_border:
            top_line = self._build_border_line(widths, 'top')
            lines.append(top_line)
        
        # 表头
        header_line = self._build_data_line(self.headers, widths, is_header=True)
        lines.append(header_line)
        
        # 分隔线
        sep_line = self._build_border_line(widths, 'middle')
        lines.append(sep_line)
        
        # 数据行（支持 banner：第一列有内容且其余列为空）
        for row in self.data:
            # 规范化行长度
            row = list(row) + [''] * max(0, len(self.headers) - len(row))

            is_banner = False
            if len(row) >= 1 and str(row[0]).strip() != '':
                # 若第一列非空且其余列均为空，则视为 banner
                rest_empty = all((not str(c).strip()) for c in row[1:len(self.headers)])
                is_banner = rest_empty

            if is_banner:
                # 合并单元格宽度（内部，不含左右竖线）
                merged_inner = sum(widths) + max(0, len(widths) - 1)
                sep_line = '├' + '─' * merged_inner + '┤'

                content_text = str(row[0])
                if self._display_width(content_text) > merged_inner:
                    content_text = self._truncate_text_to_width(content_text, merged_inner)

                disp_w = self._display_width(content_text)
                left_pad = (merged_inner - disp_w) // 2
                right_pad = merged_inner - disp_w - left_pad
                content_line = '│' + ' ' * left_pad + content_text + ' ' * right_pad + '│'

                lines.append(sep_line)
                lines.append(content_line)
                lines.append(sep_line)
            else:
                data_line = self._build_data_line(row, widths)
                lines.append(data_line)
                # 每个数据行下方追加中间分隔线，保证每行上下都有边框
                row_sep = self._build_border_line(widths, 'middle')
                lines.append(row_sep)
        
        # 下边框
        if bottom_border:
            bottom_line = self._build_border_line(widths, 'bottom')
            lines.append(bottom_line)
        
        # 输出
        output = '\n'.join(lines)
        
        if is_print:
            print(output)
        
        if log_file:
            self._write_to_file(log_file, output)
        
        return output
    
    def print_realtime_header(self, log_file: Optional[str] = None, is_print: bool = True):
        """实时打印表头（适用于循环执行时第一次打印）"""
        if hasattr(self, '_header_printed'):
            return  # 已经打印过表头了
        
        self._print_header(log_file, is_print)
    
        self._header_printed = True
    def print_realtime_row(self, 
                           row: List[Any],
                           log_file: Optional[str] = None,
                           is_print: bool = True) -> str:
        """
        实时追加打印一行（不刷新整个表格）
        
        Args:
            row: 数据行
            log_file: 日志文件路径
            is_print: 是否打印到控制台
        
        Returns:
            打印的行字符串
        """
        # 第一次调用时初始化宽度并打印表头
        if not hasattr(self, '_header_printed'):
            self._print_header(log_file, is_print)
            self._header_printed = True
        
        # 打印数据行
        line = self._build_data_line(row, self.widths)
        sep_line = self._build_border_line(self.widths, 'middle')

        if is_print:
            print(line)
            print(sep_line)

        if log_file:
            self._write_to_file(log_file, line)
            self._write_to_file(log_file, sep_line)

        return line

    def print_realtime_banner(self, banner: str, log_file: Optional[str] = None, is_print: bool = True):
        """在表格宽度内打印合并单元格风格的横幅（中间分割风格）"""
        
        # 计算合并单元格的内部宽度（不包含左右竖线）
        merged_inner = sum(self.widths) + max(0, len(self.widths) - 1)

        # 中间分割线，使用 '├' 和 '┤' 包裹，内部为实线
        sep_line = '├' + '─' * merged_inner + '┤'

        # 内容行，居中显示并两侧用竖线包裹
        content_text = banner if banner is not None else ''
        # 截断或保留以适配宽度
        if self._display_width(content_text) > merged_inner:
            content_text = self._truncate_text_to_width(content_text, merged_inner)

        disp_w = self._display_width(content_text)
        left_pad = (merged_inner - disp_w) // 2
        right_pad = merged_inner - disp_w - left_pad
        content_line = '│' + ' ' * left_pad + content_text + ' ' * right_pad + '│'

        if is_print:
            print(content_line)
            print(sep_line)

        if log_file:
            self._write_to_file(log_file, content_line)
            self._write_to_file(log_file, sep_line)
    
    def print_realtime_footer(self, log_file: Optional[str] = None, is_print: bool = True):
        """打印表格底部边框（适用于实时打印结束时）"""
        if not hasattr(self, '_header_printed'):
            return  # 如果表头都没打印过，就不打印底部
        
        bottom_line = self._build_border_line(self.widths, 'bottom')
        
        if is_print:
            print(bottom_line)
        
        if log_file:
            self._write_to_file(log_file, bottom_line)

    def _print_header(self, log_file: Optional[str], is_print: bool):
        """打印表头"""
        lines = []
        
        # 上边框
        top_line = self._build_border_line(self.widths, 'top')
        lines.append(top_line)
        
        # 表头
        header_line = self._build_data_line(self.headers, self.widths, is_header=True)
        lines.append(header_line)
        
        # 分隔线
        sep_line = self._build_border_line(self.widths, 'middle')
        lines.append(sep_line)
        
        output = '\n'.join(lines)
        
        if is_print:
            print(output)
        
        if log_file:
            self._write_to_file(log_file, output)
    
    def _build_border_line(self, widths: List[int], position: str) -> str:
        """构建边框线"""
        # 使用圆角风格边框
        if position == 'top':
            start, middle, end = '╭', '┬', '╮'
        elif position == 'bottom':
            start, middle, end = '╰', '┴', '╯'
        else:  # middle
            start, middle, end = '├', '┼', '┤'
        
        segments = [start]
        for i, w in enumerate(widths):
            segments.append('─' * w)
            if i < len(widths) - 1:
                segments.append(middle)
        segments.append(end)
        
        return ''.join(segments)
    
    def _build_data_line(self, row: List[Any], widths: List[int], is_header: bool = False) -> str:
        """构建数据行"""
        
        cells = []
        for i, cell in enumerate(row):
            if i >= len(widths):
                break
            
            cell_str = str(cell) if cell is not None else ""
            
            # 获取显示宽度并截断（使用统一工具）
            display_width = self._display_width(cell_str)
            if display_width > widths[i]:
                cell_str = self._truncate_text_to_width(cell_str, widths[i])
            
            # 填充到指定宽度
            current_width = self._display_width(cell_str)
            padding = widths[i] - current_width
            
            if is_header:
                # 表头居中
                left_pad = padding // 2
                right_pad = padding - left_pad
                cell_str = ' ' * left_pad + cell_str + ' ' * right_pad
            else:
                # 数据左对齐
                cell_str = cell_str + ' ' * padding
            
            cells.append(cell_str)
        
        return '│' + '│'.join(cells) + '│'
    
    def _write_to_file(self, filepath: str, content: str):
        """写入文件"""
        from pathlib import Path
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content + '\n')

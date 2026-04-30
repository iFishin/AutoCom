# Changelog

## [1.1.1] — 2026-04-30

### 修复
- 修复 MANIFEST.in 中引用不存在的根目录文件（About.md、AutoCom字典使用示例.md），改为正确的 docs/ 路径
- 修复 pyproject.toml 依赖列表缺少 requests 和 pywifi（仅存在于 requirements.txt 中）

### 杂务
- 补充 CHANGELOG.md 文档
- 补充 CONTRIBUTING.md 贡献指南

## [1.1.0] — 2026-04-04

### 新增
- 新增 TablePrinter 组件，优化终端表格打印效果
- 重构 Logger 日志系统，支持分级日志和更好的输出格式
- 新增 CLI 单元测试（test_autocom_cli.py、test_table_printer.py）
- 新增 GitHub Actions 工作流：自动更新文档、构建发布、PyPI 发布

### 修复
- 修复 Logger 和 TablePrinter 的若干错误
- 修复 CLI 中的语法错误
- 修复日志打印中执行时间单位（改为 ms）
- 修复执行 `autocom` 命令时误创建目录的问题
- 修复 `success_response_actions` 未正确处理的问题
- 修复 ActionHandler 中 `execute_command_by_order` 的错误处理
- 修复并行命令执行时延迟响应动作被打断的问题
- 修复 Constants 引用判断

### 变更
- 更新文档，添加全局常量使用方法，完善指令配置项说明
- 删除过时的 setup.py 相关描述和脚本文件
- 重命名 "设备使用指南" 为 Started.md
- 新增 update_actions_doc.py 脚本用于自动同步 Action 文档

## [1.0.0] — 2026-03

### 新增
- 核心串口自动化执行框架
- 支持多设备、多指令的串行和并行执行
- ActionHandler 扩展系统，支持自定义操作项
- 持续串口监听功能，避免日志挤压
- Constants 常量属性块，支持用户输入
- ConfigForDevices / ConfigForCommands 全局配置覆盖机制
- 文件夹遍历模式（-f）和监控模式（-m）
- 自定义 ActionHandler 注入支持

### 修复
- Device 插入执行切片点，记录执行轮数
- 修正执行 `autocom` 时当前目录下创建模板文件的问题
- 重构列宽分配比例以优化显示效果

---

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)
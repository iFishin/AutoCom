# 开发工具脚本

## dev.py - 统一开发工具

一个集成了所有开发任务的命令行工具。

### 快速使用

```bash
# 查看帮助
python scripts/dev.py help

# 开发模式安装
python scripts/dev.py install

# 运行测试
python scripts/dev.py test

# 查看版本
python scripts/dev.py version

# 更新版本
python scripts/dev.py version 1.1.0

# 清理构建
python scripts/dev.py clean

# 构建分发包
python scripts/dev.py build

# 发布到 PyPI
python scripts/dev.py publish
```

### 功能说明

- **clean**: 清理所有构建产物 (build/, dist/, *.egg-info, __pycache__)
- **test**: 运行所有测试,验证模块导入和 CLI 命令
- **build**: 构建 wheel 和 tar.gz 分发包
- **install**: 以开发模式安装项目 (pip install -e .)
- **version**: 查看或更新版本号
- **publish**: 发布到 PyPI (需要 twine 和正确的凭证)

---

## update_actions_doc.py - Action 文档自动生成脚本

这个脚本能够自动从 `utils/ActionHandler.py` 中提取所有 action 操作项的定义，并生成或更新 `docs/Actions.md` 文档。

### 功能特性

✨ **自动提取**: 自动发现 ActionHandler 中所有 `handle_*` 方法
📋 **生成文档**: 创建快速参考表和详细说明部分
🔄 **增量更新**: 支持添加新的 action 后自动同步文档
📝 **格式保留**: 保留原始 docstring 中的所有信息

### 使用方法

#### 基本用法

```bash
python scripts/update_actions_doc.py
```

#### 工作流程

1. **添加新的 Action**
   - 在 `utils/ActionHandler.py` 中添加新的 `handle_xxx` 方法
   - 编写包含说明和用法的 docstring（参考现有的 action 格式）

2. **更新文档**
   - 运行脚本自动提取新的 action
   - 脚本会更新 `docs/Actions.md`

3. **验证结果**
   - 查看生成的 `docs/Actions.md` 文件
   - 检查快速参考表和详细说明是否正确

### Docstring 格式规范

为了让脚本能正确提取 action 信息，请遵循以下 docstring 格式：

```python
def handle_your_action(self, config, command, response, context):
    """
    操作项简要说明
    
    用法:
    {
        "your_action": {
            "parameter1": "value",
            "parameter2": "value"
        }
    }
    
    参数:
    - parameter1: 参数说明
    - parameter2: 参数说明
    
    说明: 详细的功能说明和使用场景
    """
    # 实现代码...
    pass
```

### Docstring 的关键部分

| 部分 | 说明 | 必需 |
| --- | --- | --- |
| 第一行 | 操作项简要说明 | ✅ |
| `用法:` 部分 | 完整的 JSON 格式示例 | ✅ |
| `参数:` 部分 | 参数列表及说明 | ⭐ 推荐 |
| `说明:` 部分 | 详细功能说明 | ⭐ 推荐 |

### 脚本输出

脚本执行成功后会：

1. 列出找到的所有 action 操作项
2. 输出处理过程信息
3. 显示最终生成的文件位置
4. 报告同步的操作项总数

示例输出：
```
正在提取 ActionHandler 中的操作项...
找到 18 个 action 操作项:
  - test
  - save
  - save_conditional
  - ...

正在更新 Actions.md...
✅ 成功更新: D:\#GIT\AutoCom\docs\Actions.md
共 18 个操作项已同步
```

### 自动化集成

建议在以下场景中自动运行此脚本：

- ✅ Git hooks（pre-commit）：确保文档与代码保持同步
- ✅ CI/CD 流程：在构建前验证文档
- ✅ 发布前检查：确保所有新增 action 已文档化

### 常见问题

**Q: 脚本找不到 ActionHandler.py**
A: 确保从项目根目录运行脚本，或检查路径是否正确

**Q: 生成的文档格式不对**
A: 检查 docstring 是否遵循规范格式，特别是 `用法:` 部分的 JSON 格式

**Q: 某个 action 没有被提取**
A: 确认方法名以 `handle_` 开头，且包含有效的 docstring

### 维护建议

- 每次添加新 action 后立即运行脚本
- 定期检查文档的准确性
- 保持 docstring 与实现代码的一致性
- 在 Git 提交前确保文档已更新

---

### 详细文档

查看 [docs/开发指南.md](../docs/开发指南.md) 获取完整的开发指南。

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

### 详细文档

查看 [docs/开发指南.md](../docs/开发指南.md) 获取完整的开发指南。

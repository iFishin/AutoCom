# AutoCom 开发快速指南

## 🚀 快速开始

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/iFishin/AutoCom.git
cd AutoCom

# 开发模式安装
python scripts/dev.py install

# 验证安装
autocom -v
```

## 📦 使用开发工具 (scripts/dev.py)

### 查看帮助

```bash
python scripts/dev.py help
```

### 常用命令

#### 1. 开发模式安装

```bash
python scripts/dev.py install
```
将项目以可编辑模式安装,修改代码后无需重新安装。

#### 2. 运行测试

```bash
python scripts/dev.py test
```
测试所有模块是否正常工作。

#### 3. 清理构建产物

```bash
python scripts/dev.py clean
```
清理 `build/`, `dist/`, `*.egg-info` 等目录。

#### 4. 构建分发包

```bash
python scripts/dev.py build
```
生成 wheel 和 tar.gz 包到 `dist/` 目录。

#### 5. 版本管理

```bash
# 查看当前版本
python scripts/dev.py version

# 更新版本
python scripts/dev.py version 1.1.0
```

#### 6. 发布到 PyPI

```bash
python scripts/dev.py publish
```

## 🔄 完整的发布流程

### 发布新版本的步骤:

```bash
# 1. 确保代码是最新的
git pull

# 2. 运行测试确保一切正常
python scripts/dev.py test

# 3. 更新版本号
python scripts/dev.py version 1.1.0

# 4. 提交版本更改
git add version.py
git commit -m "Bump version to v1.1.0"

# 5. 创建 Git 标签
git tag v1.1.0

# 6. 推送到 GitHub
git push
git push origin v1.1.0

# 7. 构建分发包
python scripts/dev.py build

# 8. 发布到 PyPI (可选)
python scripts/dev.py publish

# 9. 验证从 GitHub 安装
pip install git+https://github.com/iFishin/AutoCom.git
```

## 🧪 本地测试

### 测试开发版本

```bash
python scripts/dev.py install
python scripts/dev.py test
autocom -v
```

### 测试构建的包

```bash
python scripts/dev.py build
pip install --force-reinstall dist/autocom-1.0.0-py3-none-any.whl
autocom -v
```

### 测试从 GitHub 安装
```bash
pip install git+https://github.com/iFishin/AutoCom.git
```

## 📝 版本号规范

遵循语义化版本 (Semantic Versioning):

- **主版本号** (x.0.0): 不兼容的 API 修改
- **次版本号** (0.x.0): 向下兼容的功能新增
- **修订号** (0.0.x): 向下兼容的问题修正

示例:

- `1.0.0` -> `1.0.1`: 修复 bug
- `1.0.1` -> `1.1.0`: 新增功能
- `1.1.0` -> `2.0.0`: 重大更新,可能不兼容

## 🛠️ 项目结构

```text
AutoCom/
├── cli.py                   # CLI 入口
├── AutoCom.py               # 主执行引擎
├── version.py               # 版本号
├── pyproject.toml           # 构建配置
├── components/
│   ├── SessionStore.py      # SQLite 持久化（替代旧 DataStore）
│   ├── Context.py           # 运行时变量上下文
│   ├── PipelineScheduler.py # 流水线调度器（程序计数器 + 控制流）
│   ├── steps/               # Step Handler（serial/http/script/wait/action_batch）
│   ├── CommandExecutor.py   # 旧兼容层
│   ├── CommandDeviceDict.py # 设备管理
│   ├── Device.py            # 串口设备
│   └── Logger.py            # 日志系统
├── utils/
│   ├── TemplateEngine.py    # 模板引擎（变量替换 + 条件评估）
│   ├── ActionHandler.py     # Action 分发
│   ├── CustomActionHandler.py
│   ├── common.py            # 工具函数
│   └── dirs.py              # 路径管理
├── dicts/
│   └── AutoCom2_Dicts/      # 新格式示例配置 (7个)
├── data/
│   └── sessions.db          # SQLite 执行记录
├── docs/
│   ├── Started.md           # 本文件
│   ├── About.md             # 架构说明
│   ├── Actions.md           # Action 参考
│   └── MCP.md               # AI Agent 接口
├── tests/                   # 测试文件
└── scripts/
    └── dev.py               # 开发工具
```

## 💡 开发提示

### 日常开发

```bash
# 修改代码后测试
python scripts/dev.py test

# 直接运行命令测试
autocom --help
```

### 清理环境

```bash
# 清理构建产物
python scripts/dev.py clean

# 重新安装
python scripts/dev.py install
```

### 构建前检查

```bash
# 1. 测试
python scripts/dev.py test

# 2. 清理
python scripts/dev.py clean

# 3. 构建
python scripts/dev.py build
```

## 🔍 故障排查

### 命令找不到

```bash
# 重新安装
python scripts/dev.py install

# 或者使用绝对路径
python -m cli -v
```

### 导入错误

```bash
# 确保在开发模式下安装
pip uninstall autocom
python scripts/dev.py install
```

### 构建失败

```bash
# 清理后重试
python scripts/dev.py clean
python scripts/dev.py build
```

## 📚 更多信息

- 项目主页: https://github.com/iFishin/AutoCom
- 问题反馈: https://github.com/iFishin/AutoCom/issues

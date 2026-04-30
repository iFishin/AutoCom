# 贡献指南

感谢你考虑为 AutoCom 贡献代码！本文档提供了参与项目的指引。

## 报告问题

提交 Issue 时请包含：
- AutoCom 版本（`autocom -v`）
- 使用的 Python 版本和操作系统
- 完整的错误日志（来自 `device_logs/` 目录）
- 尽可能提供能复现问题的字典文件

## 提交 Pull Request

### 分支规范

- `main` — 稳定分支，保持可发布状态
- `feat/*` — 功能开发分支
- `fix/*` — 修复分支

### 开发流程

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/your-username/AutoCom.git
cd AutoCom

# 2. 开发模式安装
python scripts/dev.py install

# 3. 创建功能分支
git checkout -b feat/your-feature

# 4. 修改代码后运行测试
python scripts/dev.py test

# 5. 如果添加了新的 Action，更新文档
python scripts/update_actions_doc.py

# 6. 提交并推送
git add .
git commit -m "feat: 简短描述你的更改"
git push origin feat/your-feature
```

### Commit 规范

```
<type>: <简短描述>

<可选详细说明>
```

类型参考：
- `feat:` — 新功能
- `fix:` — 修复 Bug
- `refactor:` — 重构
- `docs:` — 文档更新
- `test:` — 测试相关
- `chore:` — 杂务（构建、CI 等）

## 添加新的 Action

1. 在 `utils/ActionHandler.py` 中添加 `handle_xxx` 方法
2. 编写包含说明和用法的 docstring（参见现有 action 的格式）
3. 运行 `python scripts/update_actions_doc.py` 自动更新文档
4. 在 PR 中同时包含代码和文档更改

## 代码风格

- 遵循 PEP 8 规范
- 变量命名使用 snake_case
- 类名使用 CamelCase
- 所有公开方法应包含 docstring
- 注释建议中英双语均可

## 运行测试

```bash
# 运行所有测试
python scripts/dev.py test

# 或直接使用 unittest
python -m unittest discover tests
```

## 许可证

提交代码即表示你同意将你的贡献以 MIT 许可证发布。
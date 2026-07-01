# autocom-helper 脚本

独立的工具脚本，不依赖 AutoCom 项目源码。

## 脚本列表

| 脚本 | 用途 |
|--------|---------|
| `lint_autocom_config.py` | Steps 格式 YAML/JSON 配置的结构与语义检查 |
| `batch_lint_autocom_configs.py` | 批量检查目录树中的所有配置 |
| `normalize_autocom_config.py` | 键排序与格式规范化 |
| `migrate_autocom_config.py` | JSON ↔ YAML 双向转换 |

## 使用方式

```bash
# 检查单个文件
python lint_autocom_config.py path/to/pipeline.yaml
python lint_autocom_config.py path/to/pipeline.json

# 批量检查目录
python batch_lint_autocom_configs.py dicts/
python batch_lint_autocom_configs.py dicts/ --stop-on-error

# 规范化（键排序）
python normalize_autocom_config.py path/to/pipeline.yaml --write
python normalize_autocom_config.py path/to/pipeline.json --out path/to/normalized.yaml

# JSON 与 YAML 互转
python migrate_autocom_config.py path/to/pipeline.json --to yaml
python migrate_autocom_config.py path/to/pipeline.yaml --to json --out path/to/pipeline.json
python migrate_autocom_config.py path/to/pipeline.json --to yaml --dry-run
```

## 退出码

| 码 | 含义 |
|------|---------|
| 0 | 无 blocker/major 问题，或操作成功 |
| 1 | 存在 blocker 或 major 问题（仅 lint） |
| 2 | 解析/参数错误 |

## 设计原则

- 尽量只使用标准库；YAML 解析依赖 `pyyaml`（未安装时会提示）。
- 检查规则与 `SKILL.md` 的审查清单和 `references/error-catalog.md` 保持一致。
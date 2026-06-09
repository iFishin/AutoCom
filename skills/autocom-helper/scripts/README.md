# autocom-helper scripts

本目录放置可独立分发的小工具脚本，默认不依赖 AutoCom 项目源码。

## 现有脚本

- lint_autocom_config.py
  - 用途: 对 AutoCom YAML/JSON 配置做结构与语义体检
  - 输入: 配置文件路径
  - 输出: findings 列表（blocker/major/minor）

- batch_lint_autocom_configs.py
  - 用途: 批量体检目录中的 YAML/JSON 配置
  - 输入: 目录路径（递归扫描）
  - 输出: 每个文件的 findings + 汇总

- normalize_autocom_config.py
  - 用途: 配置规范化（键排序、列表排序、可选重排 order）
  - 输入: 配置文件路径
  - 输出: 规范化后的配置（可原地覆盖或输出到新文件）

- migrate_autocom_config.py
  - 用途: JSON/YAML 双向迁移转换
  - 输入: 源文件路径 + 目标格式
  - 输出: 目标格式文件

## 使用方式

```bash
python lint_autocom_config.py path/to/dict.yaml
python lint_autocom_config.py path/to/dict.json

python batch_lint_autocom_configs.py path/to/configs

python normalize_autocom_config.py path/to/dict.yaml --write
python normalize_autocom_config.py path/to/dict.json --out path/to/dict.normalized.json

python migrate_autocom_config.py path/to/dict.json --to yaml
python migrate_autocom_config.py path/to/dict.yaml --to json --out path/to/dict.json
```

退出码:

- 0: 无 blocker/major 问题
- 1: 存在 blocker 或 major
- 2: 解析/参数错误

## 设计原则

- 尽量只用标准库
- YAML 解析依赖 pyyaml（若未安装会给出提示）
- 规则保持和 SKILL.md 的校验清单一致

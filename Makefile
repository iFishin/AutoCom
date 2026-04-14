# AutoCom Makefile
# 提供常用的开发命令

.PHONY: help dev-install dev-test dev-clean dev-build dev-version dev-publish

# 帮助信息
help:
	@echo "AutoCom 开发工具"
	@echo ""
	@echo "用法: make <目标>"
	@echo ""
	@echo "开发命令:"
	@echo "  dev-install     开发模式安装"
	@echo "  dev-test       运行测试"
	@echo "  dev-clean      清理构建产物"
	@echo "  dev-build      构建分发包"
	@echo "  dev-version    查看当前版本"
	@echo "  dev-publish    发布到 PyPI"
	@echo ""
	@echo "快捷方式:"
	@echo "  install        同 dev-install"
	@echo "  test           同 dev-test"
	@echo "  build          同 dev-build"
	@echo "  clean          同 dev-clean"
	@echo ""

# 开发命令 (使用 python -m)
dev-install:
	python -m scripts.dev install

dev-test:
	python -m scripts.dev test

dev-clean:
	python -m scripts.dev clean

dev-build:
	python -m scripts.dev build

dev-version:
	python -m scripts.dev version

dev-publish:
	python -m scripts.dev publish

# 快捷方式
install: dev-install
test: dev-test
build: dev-build
clean: dev-clean
publish: dev-publish

# 更新版本快捷方式
set-version VERSION=:
	python -m scripts.dev version $(VERSION)

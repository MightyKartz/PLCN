# GitHub Release 发布指南

## 当前发布方式

RetroArch 助手通过 [GitHub Actions](.github/workflows/release.yml) 构建产物。推送 `v*` tag 会生成预发布草稿，调试执行仅构建产物。

Release 草稿和初始附件由 tag 触发的 Actions run 创建。公开发布前核对状态、附件和签名。

## 开发 PR

开发 PR 在对应系统上构建并验收，发布时从已验收的 `main` 创建 tag。

## 发布前准备

1. 确认要发布的 commit 已经在 `main`。
2. 如果用户可见版本发生变化，更新 UI 中的版本展示。
3. 更新 `RELEASE_NOTES.md`，保持中文更新在前、英文更新在后。
4. 更新 `README.md` 和 `README_EN.md` 中的最新版本说明、安装说明或开发状态。
5. 核对工作流的双语草稿正文，公开前补上本次 `RELEASE_NOTES.md` 中的版本说明。

## 发布前验证

常规发布前至少运行：

```bash
python3 -m pytest -q
python3 -m py_compile src/*.py
git diff --check
```

如果改动涉及前端模板，还要运行 `python3 scripts/check_ui_js.py`。

## 创建发布 tag

只在确认要发布时，从最新 `main` 创建 tag：

```bash
git switch main
git pull --ff-only origin main

git tag -a vX.Y.Z -m "vX.Y.Z - 简短中文发布标题"
git push origin vX.Y.Z
```

推送 tag 后，GitHub Actions 会自动：

- 构建并检查 Windows 安装版和便携版、macOS Apple Silicon 和 Intel DMG，以及 Linux x64 CLI。
- 在 Windows 安装包上验证默认窗口启动、重复启动和退出。
- 将 `RetroArchAssistant-Windows-x64-Setup.exe`、`RetroArchAssistant-Windows-x64-Portable.zip`、`RetroArchAssistant-macOS-arm64.dmg`、`RetroArchAssistant-macOS-x64.dmg` 和 `RetroArchAssistant-Linux-x64.tar.gz` 上传至预发布草稿。

工作流生成的 Windows 和 macOS 附件是未做发行签名的预览包。发行签名、公证和真机检查见 [桌面使用指南](DOC/DESKTOP_GUIDE.md#签名与正式发布)。

## 发布后验证

```bash
gh run list --repo MightyKartz/retroarch-assistant --workflow release.yml --limit 3
gh run watch --repo MightyKartz/retroarch-assistant <run-id>
gh release view vX.Y.Z --repo MightyKartz/retroarch-assistant --json tagName,name,url,assets
```

确认版本说明、五个附件和签名状态与发布目标相符，再对外提供 Release 链接。

## GitHub 仓库介绍格式

GitHub 仓库描述保持中文在前、英文在后，例如：

```text
扫描 RetroArch 游戏列表，一键生成中文名并下载官方封面。 Scans RetroArch game lists, localizes names to Chinese, and downloads official artwork.
```

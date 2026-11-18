# GitHub Release 发布指南

## 当前发布方式

RetroArch 助手通过 `.github/workflows/desktop.yml` 构建和检查安装包。PR 和手动运行均可产生构建产物；推送 `v*` tag 时，`release.yml` 调用桌面构建并创建 **draft、prerelease** Release，尚不会公开发布。手动运行 `release.yml` 仅构建，不创建 Release。

普通开发 PR 不创建、移动或推送发布 tag。维护者决定发布后，从已通过验收的 main 提交创建 tag；检查草稿及附件后再决定公开。

## 发布前准备

1. 确认发布提交已合入 main，回归与平台构建通过。
2. 在 `src/app_version.py` 更新版本，并核对安装包与 UI 的版本展示；构建可使用 `RETROARCH_ASSISTANT_VERSION` 覆盖，tag 不会自动更新源码版本。
3. 同步中英文 README、使用指南、迁移说明与本次更新内容。Release 正文来源由 `release.yml` 配置；准备发布时核对其内联正文或 `body_path` 引用文件，不能仅更新历史 `RELEASE_NOTES.md`。
4. 验证旧用户迁移、新安装、运行与卸载；真机、签名及公证未完成时如实注明。

```sh
python3 -m pytest -q
python3 -m compileall -q src
python3 scripts/check_ui_js.py
git diff --check
```

pytest 会运行全部 `tests/*.test.cjs` 行为测试。CI 另在指定 Linux 配置强制执行真实浏览器和 CHD 工具测试。

## 安装包与草稿核对

| 平台 | 附件 |
|---|---|
| Windows x64 | `RetroArchAssistant-Windows-x64-Setup.exe`、`RetroArchAssistant-Windows-x64-Portable.zip` |
| macOS Apple Silicon | `RetroArchAssistant-macOS-arm64.dmg` |
| macOS Intel | `RetroArchAssistant-macOS-x64.dmg` |
| Linux x64 CLI | `RetroArchAssistant-Linux-x64.tar.gz` |

Windows / macOS 当前构建未做发行证书签名，macOS 未公证。CI 的安装运行检查不代表全部系统安全策略和 USB 设备均已人工验收。

发布获得明确授权后，使用维护者选定的版本创建 tag。不要仅为验证构建创建 tag，直接手动运行桌面工作流即可。

```sh
gh run list --repo MightyKartz/retroarch-assistant --workflow release.yml --limit 3
gh release view vX.Y.Z --repo MightyKartz/retroarch-assistant --json tagName,name,url,isDraft,isPrerelease,assets
```

确认目标提交、版本、草稿正文、附件和验收记录一致后，再公开 Release 并对外引用下载链接。

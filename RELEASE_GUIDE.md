# GitHub Release 发布指南

## 当前发布方式

PLCN 现在通过 GitHub Actions 自动发布。发布工作流位于 [`.github/workflows/release.yml`](.github/workflows/release.yml)，只在推送 `v*` tag 时触发。

不要再手动创建 release 或上传附件。Release 页面、构建产物和附件上传都由 tag 触发的 Actions run 完成。

## 本 PR 不发布

普通修复 PR 和文档 PR 不应创建、移动或推送 `v*` tag。当前 PLCN core safety PR 的预期也是 **不发布 release**：合并代码和文档即可，等维护者明确决定发布版本时再从 `main` 创建 tag。

## 发布前准备

1. 确认要发布的 commit 已经在 `main`。
2. 如果用户可见版本发生变化，更新 UI 中的版本展示。
3. 更新 `RELEASE_NOTES.md`，保持中文更新在前、英文更新在后。
4. 更新 `README.md` 和 `README_EN.md` 中的最新版本说明、安装说明或开发状态。
5. 确认 `RELEASE_NOTES.md` 是本次 release 页面要展示的正文；当前 workflow 会通过 `body_path: RELEASE_NOTES.md` 读取它。

## 发布前验证

常规发布前至少运行：

```bash
python3 -m pytest -q
python3 -m py_compile src/*.py
git diff --check
```

如果改动涉及 `src/templates/plcn.html`，还要对内联 `<script>` 代码做 JavaScript 语法检查。可使用下面的临时检查命令：

```bash
python3 - <<'PY'
from html.parser import HTMLParser
from pathlib import Path
import os
import subprocess
import tempfile


class ScriptCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        attrs = dict(attrs)
        script_type = attrs.get("type", "")
        self.in_script = not attrs.get("src") and script_type in {
            "",
            "text/javascript",
            "application/javascript",
            "module",
        }

    def handle_data(self, data):
        if self.in_script:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script":
            self.in_script = False


collector = ScriptCollector()
collector.feed(Path("src/templates/plcn.html").read_text(encoding="utf-8"))

with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
    tmp.write("\n;\n".join(collector.parts))
    tmp_path = tmp.name

try:
    subprocess.run(["node", "--check", tmp_path], check=True)
finally:
    os.unlink(tmp_path)
PY
```

## 创建发布 tag

只在确认要发布时，从最新 `main` 创建 tag：

```bash
git switch main
git pull --ff-only origin main

git tag -a vX.Y.Z -m "vX.Y.Z - 简短中文发布标题"
git push origin vX.Y.Z
```

推送 tag 后，GitHub Actions 会自动：

- 在 Ubuntu、Windows、macOS 上安装依赖并运行 PyInstaller。
- 打包 Linux 和 macOS 可执行文件为 `.tar.gz`，Windows 保留 `.exe`。
- 创建 GitHub Release，并使用 `RELEASE_NOTES.md` 作为 release notes。
- 上传以下资产：
  - `PLCN-Linux-x64.tar.gz`
  - `PLCN-macOS-x64.tar.gz`
  - `PLCN-Windows-x64.exe`

## 发布后验证

```bash
gh run list --repo MightyKartz/PLCN --workflow release.yml --limit 3
gh run watch --repo MightyKartz/PLCN <run-id>
gh release view vX.Y.Z --repo MightyKartz/PLCN --json tagName,name,url,assets
```

确认 release 页面使用的是当前 `RELEASE_NOTES.md` 正文，并且 Linux、macOS、Windows 三个平台资产都存在后，再对外引用 release 链接。

## GitHub 仓库介绍格式

GitHub 仓库描述保持中文在前、英文在后，例如：

```text
扫描 RetroArch 游戏列表，一键生成中文名并下载官方封面。 Scans RetroArch game lists, localizes names to Chinese, and downloads official artwork.
```

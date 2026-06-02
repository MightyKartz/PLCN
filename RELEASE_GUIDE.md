# GitHub Release 发布指南

## 当前发布版本

- 版本：`v3.0.0`
- Release 标题：`v3.0.0 - PLCN 设备库工作台`
- Release Notes：使用 [RELEASE_NOTES.md](RELEASE_NOTES.md)

## 命令行发布流程

```bash
python3 -m pytest -q

git add <需要发布的文件>
git commit -m "feat: release PLCN v3.0.0"
git push origin HEAD:main

git tag -a v3.0.0 -m "v3.0.0 - PLCN 设备库工作台"
git push origin v3.0.0

gh release create v3.0.0 \
  --repo MightyKartz/PLCN \
  --title "v3.0.0 - PLCN 设备库工作台" \
  --notes-file RELEASE_NOTES.md \
  --latest
```

推送 tag 后，GitHub Actions 会自动构建并上传：

- `PLCN-Linux-x64.tar.gz`
- `PLCN-macOS-x64.tar.gz`
- `PLCN-Windows-x64.exe`

## GitHub 仓库介绍格式

中文在前，英文在后，例如：

```text
扫描 RetroArch 游戏列表，一键生成中文名并下载官方封面。 Scans RetroArch game lists, localizes names to Chinese, and downloads official artwork.
```

## 验证

```bash
gh release view v3.0.0 --repo MightyKartz/PLCN
gh run list --repo MightyKartz/PLCN --workflow release.yml --limit 3
```

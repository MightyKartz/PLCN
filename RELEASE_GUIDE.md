# GitHub Release v2.6.6 创建指南

## ✅ 已完成步骤

1. ✅ Git tag `v2.6.6` 待创建
2. ✅ 所有代码更改已提交到 main 分支

## 📋 手动创建 Release 步骤

### 方法一：通过 GitHub 网页（推荐）

1. 打开浏览器，访问：
   ```
   https://github.com/MightyKartz/PLCN/releases/new?tag=v2.6.6
   ```

2. 填写以下信息：

**Release Title（标题）：**
```
v2.6.6 - 修复 LPL 更新与封面匹配问题
```

**Release Notes（发布说明）：**
```markdown
## 🛠️ 修复与优化

### 核心功能修复
- ✅ **修复 macOS 下 LPL 文件无法更新的问题**：引入了 Unicode (NFC) 标准化处理，解决了因文件路径编码差异（NFC vs NFD）导致无法正确匹配和更新播放列表条目的问题（例如 "太空战士"）。

### 封面匹配优化
- ✅ **优化标准名称匹配逻辑**：在搜索 Libretro 数据库时，现在会主动降低 "Anniversary Collection"、"Mini" 等后缀版本的权重。这修复了像 "魂斗罗4" 被错误匹配到 "Contra Anniversary Collection"（无独立封面）导致封面下载失败的问题，确保匹配到有封面的标准版本（如 "Contra - Hard Corps (USA)"）。

### 其他
- 包含 v2.6.5 的所有构建修复（Python 脚本替代 Shell 命令）。

---

**完整更新日志**: https://github.com/MightyKartz/PLCN/compare/v2.6.5...v2.6.6
```

3. 确保勾选 **"Set as the latest release"**

4. 点击 **"Publish release"** 按钮

### 方法二：安装 GitHub CLI（可选）

如果希望后续使用命令行创建 release，可以安装 GitHub CLI：

```bash
# macOS
brew install gh

# 认证
gh auth login

# 创建 release
gh release create v2.6.6 --title "v2.6.6 - 修复 LPL 更新与封面匹配问题" --notes-file release-notes.md
```

## 🎉 完成

创建 release 后，用户可以在以下位置查看：
- Release 页面: https://github.com/MightyKartz/PLCN/releases
- 具体版本: https://github.com/MightyKartz/PLCN/releases/tag/v2.6.6

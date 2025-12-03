# GitHub Release v2.6.5 创建指南

## ✅ 已完成步骤

1. ✅ Git tag `v2.6.5` 待创建
2. ✅ 所有代码更改已提交到 main 分支

## 📋 手动创建 Release 步骤

### 方法一：通过 GitHub 网页（推荐）

1. 打开浏览器，访问：
   ```
   https://github.com/MightyKartz/PLCN/releases/new?tag=v2.6.5
   ```

2. 填写以下信息：

**Release Title（标题）：**
```
v2.6.5 - 预览逻辑优化与构建修复 (Python Script)
```

**Release Notes（发布说明）：**
```markdown
## 🛠️ 改进与修复

### 预览与校对逻辑优化
- ✅ **优先使用中文文件夹名**：对于像 "棉花小魔女" 这样文件夹名为中文但 DAT 匹配为其他名称的情况，现在会优先使用文件夹名作为新标题，避免被错误的模糊匹配覆盖。
- ✅ **封面源回退逻辑优化**：当无法找到匹配的英文名时，封面源现在会回退使用文件名（而非中文名），大大提高了封面下载的成功率（例如 "天外魔境：自来也"）。

### 构建修复
- ✅ **修复 GitHub Actions 构建失败**：引入了专门的 Python 脚本 `scripts/copy_dats.py` 来处理 DAT 文件的复制。这彻底消除了 Shell 脚本在不同操作系统（Ubuntu/macOS/Windows）上的兼容性问题，确保构建过程稳定可靠。

### 其他
- 包含 v2.6.1 的所有 PC-98 修复和数据库打包改进。

---

**完整更新日志**: https://github.com/MightyKartz/PLCN/compare/v2.6.4...v2.6.5
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
gh release create v2.6.5 --title "v2.6.5 - 预览逻辑优化与构建修复 (Python Script)" --notes-file release-notes.md
```

## 🎉 完成

创建 release 后，用户可以在以下位置查看：
- Release 页面: https://github.com/MightyKartz/PLCN/releases
- 具体版本: https://github.com/MightyKartz/PLCN/releases/tag/v2.6.5

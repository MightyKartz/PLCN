# GitHub Release v2.6.2 创建指南

## ✅ 已完成步骤

1. ✅ Git tag `v2.6.2` 待创建
2. ✅ 所有代码更改已提交到 main 分支

## 📋 手动创建 Release 步骤

### 方法一：通过 GitHub 网页（推荐）

1. 打开浏览器，访问：
   ```
   https://github.com/MightyKartz/PLCN/releases/new?tag=v2.6.2
   ```

2. 填写以下信息：

**Release Title（标题）：**
```
v2.6.2 - 预览逻辑优化与修复
```

**Release Notes（发布说明）：**
```markdown
## 🛠️ 改进与修复

### 预览与校对逻辑优化
- ✅ **优先使用中文文件夹名**：对于像 "棉花小魔女" 这样文件夹名为中文但 DAT 匹配为其他名称的情况，现在会优先使用文件夹名作为新标题，避免被错误的模糊匹配覆盖。
- ✅ **封面源回退逻辑优化**：当无法找到匹配的英文名时，封面源现在会回退使用文件名（而非中文名），大大提高了封面下载的成功率（例如 "天外魔境：自来也"）。

### 其他
- 包含 v2.6.1 的所有 PC-98 修复和数据库打包改进。

---

**完整更新日志**: https://github.com/MightyKartz/PLCN/compare/v2.6.1...v2.6.2
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
gh release create v2.6.2 --title "v2.6.2 - 预览逻辑优化与修复" --notes-file release-notes.md
```

## 🎉 完成

创建 release 后，用户可以在以下位置查看：
- Release 页面: https://github.com/MightyKartz/PLCN/releases
- 具体版本: https://github.com/MightyKartz/PLCN/releases/tag/v2.6.2

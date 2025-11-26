# GitHub Release v2.0.0 创建指南

## ✅ 已完成步骤

1. ✅ Git tag `v2.0.0` 已创建并推送到 GitHub
2. ✅ 所有代码更改已提交到 main 分支

## 📋 手动创建 Release 步骤

### 方法一：通过 GitHub 网页（推荐）

1. 打开浏览器，访问：
   ```
   https://github.com/MightyKartz/PLCN/releases/new?tag=v2.0.0
   ```

2. 填写以下信息：

**Release Title（标题）：**
```
v2.0.0 - FBNeo 街机系统完整支持
```

**Release Notes（发布说明）：**
```markdown
## 🎮 主要新功能

### FBNeo 街机系统完整支持
- ✅ 完整支持 **FBNeo - Arcade Games** 系统
- ✅ 自动映射到 4 个 arcade 子系统（CPS1, CPS2, CPS3, NEOGEO）
- ✅ 智能识别并清理 arcade 游戏地区代码（如 `(World 900227)`）
- ✅ 支持 3 列 arcade CSV 格式（MAME Name, EN Name, CN Name）
- ✅ 多 DAT 文件同时加载支持

## 🚀 核心改进

### 数据库导入优化
- 修复 CSV 导入逻辑，自动检测并正确解析 arcade 3列格式
- 为 MAME ROM 名称创建别名，提高匹配率
- 优化数据库查询性能

### 翻译策略增强
- 确保所有翻译返回数据库标准中文名
- 改进模糊匹配算法（中文阈值 65，英文阈值 80）
- 支持系统映射，单次查询检索多个子系统

### UI/UX 改进
- 增强实时日志显示，详细展示下载进度和状态
- 优化系统下拉列表，自动包含映射系统
- 改进错误提示和状态反馈

## 🐛 Bug 修复

- 修复 FBNeo 系统在 UI 中显示 "(未找到匹配的翻译库)" 问题
- 修复 arcade 游戏名称无法匹配中文翻译问题
- 修复封面下载全部失败问题
- 修复预览内容不刷新问题
- 修复新名(New Label)不更新为标准中文名问题

## 📝 使用说明

### 重要提示
如果从旧版本升级，请删除旧数据库以应用新的导入逻辑：
```bash
rm -f plcn.db
```

数据库将在首次运行时自动重新导入。

### 支持的系统
现在支持所有 RetroArch 系统，特别优化了：
- FBNeo - Arcade Games（自动查询 CPS1/CPS2/CPS3/NEOGEO）
- 所有其他标准系统（SNES, MD, PS1, etc.）

---

**完整更新日志**: https://github.com/MightyKartz/PLCN/compare/v1.0.0...v2.0.0
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
gh release create v2.0.0 --title "v2.0.0 - FBNeo 街机系统完整支持" --notes-file release-notes.md
```

## 🎉 完成

创建 release 后，用户可以在以下位置查看：
- Release 页面: https://github.com/MightyKartz/PLCN/releases
- 具体版本: https://github.com/MightyKartz/PLCN/releases/tag/v2.0.0


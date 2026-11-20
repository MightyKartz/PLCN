# RetroArch 助手 beta2：桌面预览 / Desktop preview

## 中文更新

- 修复「一键补全」：中文名库里有译名的游戏，即使图库找不到图片也会正常改名；不再因图片缺失整块跳过。
- 修复中文名库路径失效：设置里指向已删除目录时自动改用应用内置数据，不再静默使用旧缓存。
- 补全统计与横幅一致：无法翻译的英文名称也计入「需手动处理」；「缺少封面」只统计真正缺封面的游戏。
- FBNeo/MAME 街机按 ROM 短名查找中文名：三国战纪、西游释厄传、怒首领蜂、彩京等系列共 32 个版本新增官方/惯用译名；同一游戏多版本（如 `kov` 与 `kov114`）各自独立匹配。
- 列表视图与封面视图选择统一：列表行新增勾选框与表头全选，两个视图共享选择状态；封面卡片移除冗余菜单，单个「移出列表」移入详情页；Esc 清空选择。
- 前端请求统一走 `desktopRequest`（自动续期与错误提示），图标统一使用 sprite 引用。

升级前退出应用，并在首次启动新版前完成[一次性数据迁移](https://github.com/MightyKartz/retroarch-assistant/blob/main/DOC/MIGRATION.md)。保留配置、人工规则和缓存；迁移不移动设备 ROM，已有新目录不会被自动合并覆盖。

下载对应系统的 Release 附件，无需 Python、Node.js 或 Xcode。Windows/macOS 包内置 ADB；macOS 另内置 MTP 运行库。Android 连接方式及 Windows 驱动要求见 [README](https://github.com/MightyKartz/retroarch-assistant#readme)。

当前 Windows/macOS 包未做发行证书签名，macOS 未公证。自动测试不代表所有设备已验收；真实掌机的换盘、存档衔接、CHD 替换及目录移动仍需验证。请先使用副本验证高级工具，核对任务结果。

## English updates

- Fix one-click completion: games with a known translation are renamed even when the artwork gallery has no images; a missing gallery no longer skips the whole entry.
- Fix the Chinese name source: a configured path that no longer exists now falls back to the bundled data instead of silently reusing a stale cache.
- Align completion counts with the banner: untranslatable English names count as manual work, and "missing cover" only counts games without box art.
- Match FBNeo/MAME arcade Chinese names by ROM short name: 32 approved names cover the Knights of Valour, Oriental Legend, DoDonPachi and CAVE sets, and same-game variants (`kov` vs `kov114`) resolve independently.
- Unify selection across cover and list views: rows gain checkboxes and a select-all header, both views share the selection, single removal moves to the details page, and Escape clears the selection.
- Route frontend requests through `desktopRequest` and reference icons from the shared sprite.

Quit both versions and [migrate the existing profile](https://github.com/MightyKartz/retroarch-assistant/blob/main/DOC/MIGRATION.md) before first launching this preview. Migration keeps settings, manual rules and caches; it does not move device ROMs or merge existing destinations.

Download the matching release attachment; Python, Node.js and Xcode are unnecessary. Windows/macOS packages bundle ADB, and macOS bundles the MTP runtime. Packages are not distribution-signed; macOS is not notarized. Device gameplay, disc swapping, save continuity and advanced replacement/move operations still require hardware acceptance. Validate advanced tools using copies first.

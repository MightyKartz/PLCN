# PLCN v3.1.1 中文父目录名称修复

## 中文更新

- 修复普通 ROM 列表扫描时，`gba中文游戏`、`中文游戏`、`游戏合集` 等中文父目录名被误写成所有游戏名称的问题。
- 修复已被旧版本污染的游戏列表：如果当前 label 已经变成泛化目录名，重新预览时会回到 ROM 文件名和数据库匹配结果。
- 调整匹配优先级：ROM 文件名、已有有效 label、Libretro DAT 和本地中文库优先，中文集合目录只作为弱线索，不再覆盖游戏身份。
- 保留 v3.1 状态驱动修复工作台、封面状态即时刷新、“写入名称 / 封面源英文名”拆分显示和 FBNeo/Arcade 匹配增强。
- 新增 GBA 中文父目录和已污染 label 的回归测试，防止扫描后整组游戏显示成同一个目录名。

## English Updates

- Fixed regular ROM playlist scans where Chinese parent folders such as `gba中文游戏`, `中文游戏`, or `游戏合集` could be written as every game's display name.
- Fixed playlists already polluted by older versions: when the current label is a generic collection folder name, preview now repairs it from the ROM filename and database match.
- Adjusted matching priority so ROM filenames, valid existing labels, Libretro DAT evidence, and the local Chinese database win over generic Chinese collection folders.
- Preserved the v3.1 status-driven repair workbench, immediate cover-state refresh, separated **Write Name / Cover Source Name** fields, and FBNeo/Arcade matching improvements.
- Added regression coverage for GBA Chinese parent folders and polluted labels so a whole scanned list cannot collapse to one folder name again.

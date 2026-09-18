# PLCN v3.2.3 游戏列表备份位置修复

## 中文更新

- 不再在 RetroArch `playlists` 文件夹中生成 `.bak`、临时或额外的游戏列表文件。
- 已清理设备上已有的多余 `.bak` 列表；现在 `playlists` 只保留正式系统列表。
- 本地列表备份改存到 PLCN 用户数据目录。
- ADB 写回备份改存到设备 `/sdcard/RetroArch/.plcn-backups/`，不会占用 `playlists` 目录。
- 保留 v3.2.2 的 ADB 图片失败直接重试和 v3.2.1 的光盘游戏去重显示。

## English Updates

- PLCN no longer creates `.bak`, temporary, or extra playlist files inside the RetroArch `playlists` folder.
- Existing extra `.bak` playlists on the device were cleaned up; `playlists` now contains only formal system lists.
- Local playlist backups are stored in the PLCN user data directory.
- ADB write backups are stored in `/sdcard/RetroArch/.plcn-backups/` on the device, outside `playlists`.
- Preserves v3.2.2 direct retry after failed ADB artwork downloads and v3.2.1 disc-game grouping.

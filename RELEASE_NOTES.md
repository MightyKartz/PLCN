# PLCN v3.3.1 多碟显示与界面精简

## 中文更新

- 光盘游戏改为按碟显示：没有 `.m3u` 时每张碟单独一行，存在 `.m3u` 时只显示 m3u，同一张碟的 cue 与音轨文件仍然合并。此前部分多碟游戏会被错误合并或重复。
- 预览页精简为 5 列，删除独立的“写入名称”列；名称可在行内直接编辑，改名后旁注显示原名，便于核对。
- “缺图”状态的理由改为悬停提示与读屏标签；官方图库查不到时明确标注，并提示可从备用图库手动补图。
- 移除旧的名称搜索工作台窗口；列表行与检查器里的放大镜改为打开单游戏补图窗口，其中包含名称库候选与备用图库回退。
- 旧版单机配置键会在首次读取时自动迁移到新的库配置，并写回配置文件；游戏列表与图片不受影响。

## English Updates

- Disc-based games are now listed per disc: without an `.m3u`, each disc gets its own row; with an `.m3u`, only the playlist is shown. cue and track files belonging to the same disc still merge. Some multi-disc games were previously merged or duplicated incorrectly.
- The repair preview is down to 5 columns; the separate write-name column is gone. Names are edited inline, and a renamed row shows the original name beside it.
- Missing-artwork reasons moved into tooltips and accessible labels; when the official gallery has no match this is stated, with a hint that the secondary gallery can be used manually.
- The old name-search workbench is removed. The magnifier in the list and inspector now opens a single-game artwork dialog with catalog candidates and a secondary-gallery fallback.
- Legacy single-game configuration keys are migrated automatically on first read and written back; playlists and artwork are unaffected.

# PLCN v3.3.0 中文名找图与分类图片状态

## 中文更新

- 可以直接用中文游戏名搜索官方图库图片。命中后会换算英文名并在候选列表中显示中文名与匹配来源，必须手动点选确认，不会自动写入。
- 候选按可靠性分级：完全匹配 → 名称库译名 → 英文关键词 → 模糊匹配。只有更高一级没有结果时才降级；模糊结果标注匹配度，供人工判断。
- 游戏列表的图片列按“封面 / 游戏截图 / 标题图”三类分别显示 `✓ 已有`、`○ 缺少`、`! 损坏`；“缺图”筛选在任意一类缺失时命中。
- 单个游戏可以一次勾选多个类型补图。三类图片仍互相独立，更换一类不会自动修复其他类型。
- 统一了图片相关术语与提示文案；批量窗口标题改为“搜索游戏名（中/英）”。
- 本次没有配置或游戏列表格式变更，覆盖安装即可升级。

## English Updates

- Chinese titles can now be searched against the official gallery. A match is translated to its English name and the candidates show both names plus how they were found; nothing is written until you click one.
- Candidates are graded: exact → catalog translation → English keyword → fuzzy. A lower tier is only used when higher ones return nothing, and fuzzy matches display their score for manual judgement.
- The playlist image column reports 封面 / 游戏截图 / 标题图 separately with `✓ present`, `○ missing`, `! damaged`; the missing filter matches a game when any of the three is absent.
- Several artwork types can be requested for one game at once. The three types stay independent — replacing one never repairs the others.
- Unified artwork wording; the batch dialog is now “搜索游戏名（中/英）”.
- No configuration or playlist format changes; install over the previous version.

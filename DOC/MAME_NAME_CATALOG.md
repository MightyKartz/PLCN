# MAME 名称目录与图片来源

`data/rom-name-cn/MAME.csv` 提供 2220 个街机 ROM 集名称、中英文标题的对照，按 ROM 集 ID 联结以下公开元数据。仅提取名称事实，不包含 ROM、图片或第三方程序代码。

- 英文描述：[Libretro database 的 MAME 2003 XML](https://github.com/libretro/libretro-database/blob/master/metadat/mame/MAME%202003%20XML.xml)。
- 中文名称：[RetroPie_gamelist2tw 的 mame32cn.lst](https://github.com/kospin/RetroPie_gamelist2tw/blob/master/mame32cn.lst)，原文件 GB18030，构建前转换为 UTF-8。

生成命令：`python scripts/build_mame_name_catalog.py MAME2003.xml mame32cn-utf8.lst data/rom-name-cn/MAME.csv`。英文保留地区、修订版描述；中文去掉括号中的地区说明，用于按作品推荐，不声称 ROM 版本已经验证。其他别名和未收录作品通过 `title_aliases.json` 维护。

缺少封面而有同一游戏截图时，预览和下载共用 `artwork_cover_fallback`，截图作为展示图写入 Named_Boxarts；下载明细记录真实的图片类型和来源。

程序下载的图片在本地记录来源与 SHA-256。推荐改为另一游戏时，只有现存图片仍匹配原下载哈希、且原选择不是人工指定，才会在预览中标记为过期。用户确认应用后，旧图片按内容哈希备份至用户数据目录的 `artwork-backups`，然后下载并验证替换。现存字节已变的用户图片会保留，MTP 发布仍检查读取时的设备文件哈希。

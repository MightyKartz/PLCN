# 项目使用的 Libretro DAT

`dat/` 为主库，`supplemental/` 为原项目手工补充/Virtual Console 记录。加载主库后合并补充记录，补充文件不能覆盖完整主库。

本轮固定的主库为 Sega - Saturn（Redump）和 Nintendo - Super Nintendo Entertainment System（No-Intro）。`sources.json` 记录官方来源、版本、下载日期、条目数和 SHA-256；缓存中与已知旧补充文件完全相同的副本不会遮住完整主库。其它平台的现有数据保持原样。

上游数据结构和来源说明：https://github.com/libretro/libretro-database#readme 。保留上游 DAT 头部；更新时同时更新数据和来源摘要。应用包自检验证两份主库及补充文件的摘要。

# PLCN 早期设想与当前实现对照

## 文档状态

本文保留 PLCN 的原始产品设想，并标注它与当前代码实现之间的差异。后续开发应以代码和 [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md) 为准；本文主要作为需求来源和方向参考。

## 早期设想

最初目标是开发一个“在 RetroArch 界面内显示中文游戏名称，并自动下载 RetroArch 游戏封面和截图”的第三方插件。

核心意图：

- 让 RetroArch 播放列表显示中文游戏名。
- 自动匹配并下载官方 Libretro 缩略图。
- 尽量兼容中文 ROM 文件名、英文标准名和不同平台命名差异。
- 原始设想曾考虑过外部辅助识别，但当前准确性路线已收敛为本地证据优先：ROM 路径、文件名、CRC/DAT、别名和用户手动修正沉淀，不依赖在线数据库、云端服务或 LLM 匹配。

## 当前实现

当前项目已经落地为一个 RetroArch 外部的本地辅助工具，而不是 RetroArch 内部插件：

- 入口：`src/plcn.py`，无参数时启动本地 Web UI，也支持命令行处理。
- Web API：`src/server.py`，提供配置、文件浏览、预览、应用、批量处理、搜索和进度接口。
- 播放列表处理：读取 `.lpl`，生成建议修改项，应用前备份并写回。
- 翻译与匹配：使用 `rom-name-cn` 数据、SQLite 缓存、别名/模糊匹配和 Libretro DAT 名称匹配。
- 缩略图下载：从 Libretro 缩略图服务器下载封面、截图和标题图。
- UI：`src/templates/plcn.html` 提供本地工作台式 Web UI。

## 已确认差异

| 主题 | 早期设想 | 当前代码现实 | 后续处理 |
| --- | --- | --- | --- |
| 产品形态 | RetroArch 内部第三方插件 | 本地 Python CLI + Web UI 工具 | README 已按当前形态描述；插件化作为远期方向 |
| RetroArch 集成 | 在 RetroArch 界面内直接显示中文 | 通过修改 `.lpl` 播放列表标签实现 | 先保证写回安全和可恢复，再评估更深集成 |
| 缩略图下载 | 自动下载封面和截图 | 已支持 Boxart、Snap、Title 下载，并返回成功/失败/跳过统计 | 下一步补充断言式测试、重试策略和失败恢复 |
| 外部辅助识别 | 早期曾考虑 API 辅助 | 当前不接入 ScreenScraper、Skraper、在线数据库、云服务或 LLM 匹配 | 继续坚持本地证据和可复现回归，避免远程匹配影响隐私与确定性 |
| 匹配置信度 | 设想中未细分 | 后端已开始返回 `match_score`、`match_status`、`match_source` 和 `match_reason`；前端已收敛为展示后端权威状态和人工校对状态 | 后续继续补充本地证据链和 UI 展示 |
| 数据维护 | 依赖外部数据源 | `rom-name-cn`、Libretro DAT、SQLite 混合使用 | 需要明确 `plcn.db` 是生成缓存还是版本化资产 |

## 后续方向

短期优先级不是重新做插件化，而是把现有本地工具做稳：

1. 先补齐断言式测试和播放列表写回安全。
2. 再把匹配链路整理成可解释、可回归的后端结果。
3. 然后拆分 UI/API，完善批量进度、错误恢复和打包发布。
4. 最后再评估是否需要 RetroArch 内部插件或更深的本地伴随服务；匹配准确性仍以本地证据、回归样本和手动 override 学习为边界。

## 参考资料

- https://github.com/yingw/rom-name-cn
- https://github.com/libretro/RetroArch
- https://docs.libretro.com/
- https://docs.libretro.com/guides/roms-playlists-thumbnails/
- https://docs.libretro.com/development/coding-standards/

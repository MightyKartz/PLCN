# RetroArch 手动扫描与核心管理调研

调研日期：2026-11-15。此文件为设计依据，本轮未修改运行逻辑、下载核心或写入掌机。

## 结论

PLCN 应以“游戏目录 → 主机 → 默认核心”为每个扫描配置的主线，保存设置供后续增量更新。默认核心在 RetroArch 手动扫描中技术上可不指定（DETECT），但对开箱即用的导入流程，应明确展示核心关联及其安装状态。

区分经典手动扫描与当前主线新扫描功能：2019 年官方介绍的手动扫描按文件名生成列表，不要求数据库匹配；当前主线增加扫描方式、数据库匹配模式等配置，不能把主线参数假定为用户已安装 Android 版本的功能。实施前应核对目标版本。

## 已核对的扫描规则

| 设置 | 官方行为及实现建议 |
| --- | --- |
| 内容目录 | 扫描指定位置；允许递归。MTP 定位与 Android 启动路径分别保存，不能把 mtp URI 写入游戏 path。 |
| 主机/系统名称 | 决定目标列表名称及图库对应关系；支持标准数据库名称、目录名称、自定义名称。默认优先标准名称，例如 Sega - Saturn。 |
| 默认核心 | 为扫描所得游戏设置启动核心；不是扫描成功或游戏可运行的证明。保留已有单项核心关联。 |
| 扩展名 | 显式扩展名优先；留空且已选核心时使用其支持格式；两者都无时可能纳入所有文件。GUI 描述要求空格分隔。核心支持格式来自 info 文件，不应靠目录名猜测。 |
| 递归扫描 | 开启时包含子目录。 |
| 扫描压缩包 | 开启时查找包内可支持内容，会增加读取成本。MTP 默认不整库读取 ZIP/7z；街机 ZIP 作为 ROM 集保留。 |
| 街机 DAT | Logiqx/MAME List XML 用于街机短名转标准名称；DAT Filter 开启后只纳入命中 DAT 的内容。必须匹配核心/ROM 集版本。 |
| 覆盖现有列表 | 开启先清除旧列表；关闭保留现有条目，仅添加缺少内容。PLCN 默认采用增量合并。 |
| 验证已有条目 | 检查并移除缺失内容或扩展名无效条目。PLCN 首版改为预览失效项并独立确认，不因 MTP 读取失败判断文件被删除。 |
| 刷新列表 | 可利用保存的 scan_* 字段重用配置；只写目标版本可识别的字段。 |

光盘格式必须按入口而非所有文件计数，避免 CUE 与 BIN 音轨重复。保留当前用户的逐碟记录；发现 M3U 时展示与分碟文件的关系，不静默重组已有列表。

## 核心推荐策略（产品建议，不代表官方最佳排名）

推荐顺序：保留用户已选且可用的核心 → 确认 RetroArch 应用 ABI 与可用官方构建 → 按主机、性能、游戏格式、BIOS 和 ROM 集兼容性推荐一个 → 允许更换。手机 CPU 为 64 位不能证明 RetroArch 应用为 64 位。

候选基线：NES Nestopia UE；SNES Snes9x；GB/GBC Gambatte；GBA mGBA；MD Genesis Plus GX；PS1 PCSX ReARMed（ARM 性能方向）；FBNeo 按匹配的 FBNeo ROM 集使用 FinalBurn Neo。MAME 不固定跨版本替换，要先确认 ROM 集。SS 需单独真机验证 Beetle Saturn 等候选的性能与兼容性，不提前宣称最佳。

特别发现：官方 YabaSanshiro libretro 文档目前明确标记该核心过时、问题较多且无人维护，建议优先其他 Saturn 核心。不能把独立 Android Yaba Sanshiro 应用的口碑直接等同于该 libretro 核心。

2026-11-15 实际读取官方 arm64-v8a 目录，存在上述常见候选的 Android ZIP，并存在 mednafen_saturn、yabasanshiro、yabause、swanstation；该目录未检出 kronos。目录存在文件仅表示当时提供构建，不表示适用于当前掌机或已通过游戏测试。运行时应重新检查下载可用性。

## 官方下载与 Android 安装

1. 优先使用掌机 RetroArch 内的 Online Updater → Core Downloader。
2. PLCN 代下载只使用 Libretro 官方 buildbot 对应平台/ABI 的索引，例如 nightly/android/latest/arm64-v8a/。不混用 macOS/Linux 同架构产物。
3. 记录下载来源、构建时间（如可得）与本地 SHA-256；本地摘要用于追踪，不声称是官方认证。下载后核对 ZIP 与 ELF 架构；核心 info 配套更新。
4. MTP 无权写入应用私有 cores 目录时，将官方核心放入用户可访问的下载目录，用户在 RetroArch“Load Core → Install or Restore a Core”完成安装。不能把“已下载/已传输”显示成“已安装”。
5. 不猜测 Android 核心绝对路径；从可访问配置/已有列表恢复，无法确认时等待用户指定或在 RetroArch 端关联。应用 ABI、包名、版本、目录在纯 MTP 下不一定都能自动识别。
6. BIOS 与核心分开检查；本流程不将 BIOS 当作核心附带下载。

建议状态：已安装可关联 / 可官方下载 / 已下载待传输 / 已传输待安装 / 安装状态未知。只有有证据时显示已安装；是否能运行还需 RetroArch 端验证。

## 建议交互

“更新游戏库” → 选择目录 → 确认主机 → 推荐核心（可更换、查看官方来源与安装状态） → 扫描预览新增/保留/失效项 → 确认更新 → 衔接名称与图片补全。

扫描配置记住后，后续沿用，不要求重复选择目录、主机、核心。首次选择推荐核心与更新已有核心是两种操作；不在扫描时自动升级用户已用核心。

## 官方依据

- [手动扫描最初定义](https://www.libretro.com/index.php/retroarch-manual-content-scanning-coming-very-soon/)
- [当前主线扫描配置实现](https://github.com/libretro/RetroArch/blob/master/manual_content_scan.c)
- [当前主线菜单规则与帮助文本](https://github.com/libretro/RetroArch/blob/master/intl/msg_hash_us.h)
- [列表格式与 scan 字段](https://docs.libretro.com/guides/roms-playlists-thumbnails/)
- [核心安装、架构、info 与应用内导入](https://docs.libretro.com/guides/download-cores/)
- [Android arm64 官方构建目录](https://buildbot.libretro.com/nightly/android/latest/arm64-v8a/)
- [街机核心与 ROM 集规则](https://docs.libretro.com/guides/arcade-getting-started/)
- [Nestopia](https://docs.libretro.com/library/nestopia/)、[Snes9x](https://docs.libretro.com/library/snes9x/)、[Gambatte](https://docs.libretro.com/library/gambatte/)、[mGBA](https://docs.libretro.com/library/mgba/)、[Genesis Plus GX](https://docs.libretro.com/library/genesis_plus_gx/)、[PCSX ReARMed](https://docs.libretro.com/library/pcsx_rearmed/)
- [Beetle Saturn](https://docs.libretro.com/library/beetle_saturn/)、[YabaSanshiro 维护状态](https://docs.libretro.com/library/yabasanshiro/)

## 首版实施

已接入目录扫描和独立预览计划，详见 DESKTOP_GUIDE。默认增量新增而非替换；现有单项设置保持。压缩包先按单个入口处理，不进行包内扫描。MTP 私有核心安装由 RetroArch 端完成，PLCN 明确区分下载、传输与安装状态。官方核心下载的 ELF 架构及信息文件已实测校验，设备写入流程先在隔离测试库验收。

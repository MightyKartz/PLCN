# Android 存储验证版

这是 ARM64 掌机的开发验证 APK。Kotlin 负责 Android 目录授权和文件读写，WebView 显示随 APK 打包的页面，Chaquopy 运行桌面项目共用的 `PlaylistManager` 和 `safe_io`。验收仅使用名为 `RAA-Probe.lpl`、包含 `retroarch_assistant_probe: true` 且只有一条记录的测试列表。

## 构建

使用 JDK 17、带 pip 的 Python 3.13、Android SDK 36 和 Build Tools 35.0.0。构建机器需能运行 `python3.13 -m pip`。在仓库根目录执行：

```sh
./android/gradlew -p android :app:assembleDebug
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Android CI 也会构建相同的调试签名 APK。应用包名带 `.probe` 后缀，可与日后的正式版分别安装。

## 验收

1. 在内置共享目录和 SD 卡各建一个测试文件夹，分别复制 [测试播放列表](fixtures/RAA-Probe.lpl)。如需用 RetroArch 启动，将列表内的 `path` 改为设备上合法测试 ROM 的实际启动路径，并提前安装对应核心。
2. 点「授权测试目录」，在系统选择器中选择含列表的目录。重新启动应用后，应显示授权有效。Android 11 及更新版本对根目录和其他应用的 `Android/data` 有授权限制。
3. 点「预览 RAA-Probe.lpl」，确认名称、RetroArch 启动路径及依赖自检结果。预览只写应用缓存。点「备份并写入测试列表」前退出 RetroArch。
4. 确认应用报告写入并读回校验，且列表只改变显示名称。原始字节保存在应用私有 `files/backups/`。调试构建可用 `adb shell run-as io.github.mightykartz.retroarchassistant.probe ls files/backups` 检查。
5. 在 RetroArch 中将测试文件夹设为播放列表目录，打开测试列表并实际运行条目，分别记录内置存储与 SD 卡的结果。更改 RetroArch 配置前备份原设置。
6. 在预览之后用其他工具修改测试文件，验证当前提案会被拒绝。应用会在备份并验证原始字节后写入。目录提供者的原位写入可能中断，因此这个验证版只处理测试文件。

授权 URI 用于读写测试文档。列表内的游戏启动路径保留原值，由 RetroArch 决定是否可用。

## Python 依赖

ARM64 模拟器验证了 Python 3.13、Pillow 11.0.0、Requests 2.34.2 和 RapidFuzz 3.14.6。当前 Chaquopy 和 PyPI 索引没有适用的 RapidFuzz Android 原生 wheel。Gradle 从上游源码构建纯 Python wheel，保留现有匹配接口。模拟器验证了评分和候选提取，完整游戏库的匹配耗时和结果仍需测量。

## 已验证范围

Android 16 ARM64 模拟器的内置共享目录和虚拟 SD 卡均完成授权、应用重新启动后复用授权、预览、备份、写回和字节读回。验证过原内容与备份完全一致、启动路径未改变，以及外部修改后旧预览被拒绝。实体 SD 卡和目标掌机上的 RetroArch 实际游戏启动仍待验证。

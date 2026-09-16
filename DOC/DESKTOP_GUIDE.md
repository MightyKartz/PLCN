# PLCN 桌面预览版使用与发布

本轮是 v3.2 桌面体验预览，尚未发布正式版本。PR：[MightyKartz/PLCN#5](https://github.com/MightyKartz/PLCN/pull/5)。

## 普通用户

Windows：安装 `PLCN-Windows-x64-Setup.exe` 后，从开始菜单启动；也可以解压便携 ZIP 后双击 `PLCN/PLCN.exe`。便携包默认仍使用用户数据目录，程序升级不会覆盖配置。

macOS：选择对应架构的 `PLCN-macOS-arm64.dmg`（Apple Silicon）或 `PLCN-macOS-x64.dmg`（Intel），将 PLCN.app 拖到 Applications。当前 CI 产物为未签名/未公证预览，不能作为正式分发就绪的声明；发布者应完成下方签名验收。

打开后出现浏览器工作台，关闭标签不停止服务。再次启动会打开已有服务，不创建第二个实例。需要停止时用右上角“退出”，有运行任务时会提示先等待或取消。

1. 点击“选择游戏目录”，选择 RetroArch、SD 卡或挂载目录；程序识别列表和图片目录。也可使用“自动检测”，或展开“高级配置与手动路径”直接指定列表。
2. 选择本次操作：修复名称并补图、仅修复名称、仅补全图片。仅补图按原 label 保存图片，不重写 `.lpl`。
3. 预览、核对并应用。风险条目仍须逐项核对；界面的匹配说明以证据与冲突为主，不把规则评分当成准确率。
4. “任务”显示本次运行的进度和错误；可以取消、重试未完成的本地图片。取消在安全边界生效，已写回的名称、已下载的图片会保留。当前网络请求/数据包构建结束前可能仍显示运行中。
5. “恢复”列出最近 100 条本地列表写回记录。恢复前检查列表与备份的摘要，列表被其它程序修改则拒绝覆盖；同时保留恢复前备份。图片不会随列表恢复删除。ADB 备份仍在设备上，当前需手动恢复。

系统文件选择器运行于独立 helper 的主线程；不可用时自动回退内置文件浏览。原生选择器的真实桌面交互仍在人工验收清单中。

## 数据库更新

右上角“数据库”提供检查上游版本、下载并比较、比较已安装包、启用和回滚。查看任务中的新增、移除、译名变化和未翻译数量后再启用；这些数量不是准确率评估。切换会清除旧预览，人工规则保留。首次数据导入可能需要等待几秒，之后使用缓存。

数据包在应用数据目录的 `packs/`；比较普通 CSV 时创建可复用的 baseline 快照。更新包不自动启用。启动时不会自动联网更新名称数据；DAT 未缓存时仍沿用现有按需下载行为。失败图片重试不会再次改名；命名冲突和 ADB 推送不在此重试入口中，需修正后重新预览。

## 数据存储与迁移

| 内容 | Windows | macOS |
| --- | --- | --- |
| 配置、规则、数据包、历史、日志 | `%LOCALAPPDATA%\PLCN` | `~/Library/Application Support/PLCN` |
| 可重建缓存、DAT | `%LOCALAPPDATA%\PLCN\cache` | `~/Library/Caches/PLCN` |

Linux 使用 XDG 用户数据/缓存目录。`PLCN_HOME` 可显式指定独立数据目录，用于便携场景和测试；设置后缓存也放在该目录下。它应为可写、仅当前用户使用的目录。

首次启动复制已知旧程序目录中的 `config.json` 与人工规则，不删除原件；将旧相对路径转换为绝对路径，失效的内置数据路径改回资源默认值。已有新配置不覆盖。迁移记录为 `migration.json`，桌面日志为 `logs/desktop.log`，超过 5 MiB 时在下次启动轮换。之前自行移动程序、把配置放在其它目录的情况，需从高级设置重新选择路径或手动迁移。

源文件与内置名称数据只读使用；运行时不再依赖安装目录可写。旧根目录 `plcn.db` 仍不改动，缓存可从 CSV 重建。原始列表和相邻备份仍留在用户游戏库。

## 从源码与本地打包

```powershell
# Windows，项目根目录
.\venv\Scripts\python.exe src\plcn.py ui
# 无控制台入口（系统的 pythonw 或虚拟环境 pythonw）
.\venv\Scripts\pythonw.exe src\desktop.py

python -m pip install -r requirements.txt pytest
python -m pytest -q -rs
python scripts/check_ui_js.py
python scripts/package_desktop.py --arch x64
# 已安装 Inno Setup 6 时生成安装程序
python scripts/package_desktop.py --arch x64 --installer
```

macOS 在对应架构机器上执行 `python3 scripts/package_desktop.py --arch arm64` 或 `--arch x64`。脚本使用 onedir/app bundle，核对 Python 实际架构，并从临时工作目录启动 `--self-check` 验证资源和写入目录；不支持跨 OS 编译。Linux 继续保留 `plcn.spec` 的 CLI 打包。

## 签名与正式发布

桌面 CI 在 Windows x64、macOS Intel、Apple Silicon 上构建，产物明确命名为 `unsigned`。Tag 工作流只创建草稿预发布，保留 Linux CLI；不会直接发布未经人工验收的稳定版本。

macOS：将自己的 Developer ID Application 证书导入构建机器钥匙串，通过环境变量 `PLCN_CODESIGN_IDENTITY` 指定身份后重新构建。PyInstaller 会签署内部二进制，应用使用 `packaging/macos-entitlements.plist`；仍需检查 hardened runtime 和最终嵌套签名。构建后提交 DMG：

```bash
codesign --verify --deep --strict --verbose=2 dist/PLCN.app
codesign -d --verbose=4 dist/PLCN.app
xcrun notarytool submit dist/PLCN-macOS-arm64.dmg --keychain-profile PLCN-notary --wait
xcrun stapler staple dist/PLCN-macOS-arm64.dmg
xcrun stapler validate dist/PLCN-macOS-arm64.dmg
spctl --assess --type execute --verbose=4 dist/PLCN.app
```

`PLCN-notary` 是发布者自己事先配置的钥匙串 profile，占位名称不代表已存在凭据；Intel 产物同样处理。公证后从下载的 DMG 安装并检查 Gatekeeper、启动、文件选择和写回。不要仅因 CI 上自检成功就认为下载隔离环境也通过。

Windows：使用自己的代码签名证书和 Windows SDK `signtool` 签署 `dist/PLCN/PLCN.exe`，再生成安装程序和便携 ZIP，随后签署 Setup.exe，并用 `signtool verify /pa` 验证。证书密码只经发布环境/密钥库注入，不提交仓库。当前没有导入或申请任何签名证书。

正式发布前还需人工验收：安装/卸载与升级后配置保留、非 ASCII 路径、只读程序目录、双击重复启动、系统文件选择器、关闭/取消、恢复、真实 ADB 与外接卷断开。桌面 UI 的完整键盘/多语言检查继续保留为发布检查项。

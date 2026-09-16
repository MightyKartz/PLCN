# 名称数据包与安全写回

适用于 2026-09-16 的开发分支；尚未发布为新版本。

## 更新名称数据

名称数据包与 Libretro DAT 是两类数据。名称包提供按平台隔离的英文名、中文名及派生别名；DAT 提供 ROM 识别线索。中文译名、ROM 身份、图片来源分别处理，不能用其他平台的同名游戏自动确定当前 ROM。

在项目根目录运行，下列命令的输出目录必须尚不存在：

```bash
# 从仓库内数据构建可重复使用的离线快照
python src/plcn.py data build --source data/rom-name-cn --output .plcn_runtime/packs/bundled

# 从 yingw/rom-name-cn 获取数据：先把 ref 解析为固定 commit，再构建
python src/plcn.py data fetch --ref master --output .plcn_runtime/packs/upstream

# 校验数据库、源文件指纹与 schema；查看各平台记录数和空译名数
python src/plcn.py data inspect --pack .plcn_runtime/packs/upstream

# 对比同一 (system, english_name) 的记录变化
python src/plcn.py data compare --before .plcn_runtime/packs/bundled --after .plcn_runtime/packs/upstream

# 只有这一步切换配置中的数据源
python src/plcn.py data activate --pack .plcn_runtime/packs/upstream

# 恢复上一次数据源，可再次执行以切换回来
python src/plcn.py data rollback
```

自定义配置路径放在子命令前：`python src/plcn.py data --config /path/config.json activate --pack /path/pack`。切换后刷新 Web UI，再重新生成预览；已打开的旧预览不会重新计算。CLI 显式传入的 `--rom-name-cn-path` 优先于配置。

包目录包含 `manifest.json`、只读打开的 `catalog.sqlite3` 和 `rom-name-cn/` 源文件副本。manifest 记录来源仓库、固定 commit（本地构建则为 `local-snapshot`）、构建时间、schema、SHA-256 和按平台统计。下载和构建不会自动激活，不会修改原始 CSV 或人工修正规则。

保留上游 README、贡献说明和存在的 LICENSE/COPYING 文件。中文系列偏好 JSON 随包保存，当前不会把所有系列配置导入成游戏身份别名。空中文名称保留为未翻译记录，不视为成功匹配。`compare` 统计的是记录差异，不代表准确率提升；特别是移除记录和大批译名变化，应抽样校对后再切换。

## 缓存与人工修正

- 普通 CSV 目录按内容指纹缓存到 `.plcn_runtime/catalogs/`。源数据变化生成新的缓存，正在运行的任务继续使用原快照。
- 数据包直接只读查询自己的 catalog。旧 schema 数据库通过 `DatabaseManager` 打开时，先创建 `*.bak-schema1-*` 备份再迁移。
- 仓库根目录的旧 `plcn.db` 不再是默认运行缓存；运行新版本不会覆盖它。旧缓存可以从 CSV 重建；其中自行追加且未保存到 CSV 的数据应另行导出。
- 人工规则保存在 `manual_overrides.json`，或配置的 `manual_overrides_path`。数据包更新、缓存刷新和回滚都不会清空它。
- CRC 必须是八位十六进制（兼容 `0x` 和 `|crc` 表示）。两条有效 CRC 冲突时，不允许退回同文件名规则。

## 预览与写回

1. 保留原列表的全部条目及索引，不隐式去重。混合列表优先用每个条目的 `db_name`，缺失时用所选系统。
2. 模糊匹配、跨系统建议和证据冲突进入人工复核。直接 CLI 和批量任务默认跳过这些条目；Web UI 中校对后点击“已核对，加入应用”，再检查最终摘要。
3. 同一目标采用 PLCN 协作锁，检查预览条目快照及文件变化，创建时间戳备份，再通过同目录临时文件和原子替换写回，随后读回验证。只为确认写回成功的条目处理图片。
4. ADB 写回先比较设备原列表，上传临时文件并验证，再检查原列表、备份并验证备份，最后替换和读回。出错时不会把尚未验证的写回当成成功。

协作锁约束 PLCN 任务，不能锁住 RetroArch 或其他程序；最后一次比较与替换之间也不是跨程序事务。建议处理时关闭 RetroArch，避免其退出时覆盖列表。实机 ADB、断电恢复及网络文件系统原子性仍需发布前验证。

恢复列表时先停止相关任务，找到输出中的 `backup_path`，保留当前文件，再用对应备份恢复。ADB 备份在设备上。若 PLCN 异常退出留下 `.plcn-lock`，先确认没有该文件的任务在运行，再移除锁文件。当前没有一键恢复 UI。

## 图片状态

预览分别检查封面、截图和标题图，区分存在、损坏、可复用英文名图片、缺失和缺少来源。更名后优先复制本地有效英文名图片；下载后验证 PNG，再原子保存。HTTP 404、无效图片、其他 HTTP 错误与网络/写入失败分别报告。

同一图片任务合并下载；不同英文来源落到同一中文文件名时报告 `filename_collision`，需保留地区/版本区分。现有图片的格式有效性不等于游戏身份正确，仍需人工核对。当前 resolver 提供按 ROM 文件名查图的接口，UI 尚未接入对应的 RetroArch 设置读取；完整在线图片索引与失败缓存属于后续阶段。

## 本地服务和开发验证

服务只监听 `127.0.0.1`。端口 7777 被占用时使用系统分配的端口，不终止其他进程。浏览器会话 cookie、Host、Origin 与 Fetch Metadata 检查用于阻止跨站调用本地 API；不提供任意静态文件下载。它不是面向公网的服务，也不替代操作系统的本机访问控制。

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q -rs
python -m compileall -q src
python scripts/check_ui_js.py
git diff --check
```

最后一项脚本需要 Node.js。回归测试使用临时 SQLite、离线小型 DAT、模拟 HTTP 和 ADB，不依赖用户缓存，不修改真实 ROM。CI 配置覆盖三个系统与 Python 3.9/3.13；本次本地验证环境为 Windows / Python 3.13，不能据此宣称其它平台或打包产物已验证。

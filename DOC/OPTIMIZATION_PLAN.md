# PLCN 后续优化方案

生成日期：2026-06-02

## 目标

本方案基于当前代码实现制定，目标是把 PLCN 从“可用的本地工具”推进到“越用越准确、可回归测试、可持续维护”的 RetroArch 游戏列表中文化与缩略图匹配工具。

当前优先级：准确性第一，写回安全第二，UI 和发布流程服务于前两者。任何新功能都不能降低匹配可信度，遇到证据冲突时宁可标记为需人工确认，也不要自动写入错误名称或错误封面源。

## 准确性原则

PLCN 是本地运行工具，不接入 ScreenScraper、Skraper、在线游戏数据库、云同步或 LLM 在线匹配。准确性只能来自本地证据、本地数据和可复现回归。

1. 强证据优先：ROM 路径、文件名、zip short name、RetroArch `crc32`、本地可读 zip CRC、Libretro DAT 校验和、确定性别名，优先级高于中文目录名和模糊搜索。
2. 弱证据只做提示：中文目录名、已有中文 label、模糊中文搜索只能辅助生成候选，不能覆盖更强的 ROM/DAT/CRC 证据。
3. 宁可跳过，不要误改：当英文封面源、中文名和 ROM 证据互相冲突时，默认进入 `需人工确认`，不进入可自动修复。
4. 每个误匹配都变成回归样本：用户反馈的 `.lpl` 条目、ROM 文件名、zip 名、`crc32`、期望封面源，都应沉淀为最小 fixture。
5. 人工修正要能沉淀：用户手动修正的中文名、英文封面源和别名，应能保存到本地 override/alias 数据中，后续扫描同类游戏时优先使用。
6. 中文名和封面源分离：中文名用于 playlist 显示，封面源英文名用于 Libretro 缩略图匹配，两者不能互相冒充。

## 当前实现事实

- 项目形态：Python CLI + 本地 Web UI，不是 RetroArch 内部插件。
- 主入口：`src/plcn.py`，无参数或 `ui` 子命令会启动本地 Web UI。
- 本地 Web 服务：`src/server.py`，只在本机运行，提供配置、运行时统计、文件浏览/打开目录、系统列表、预览、应用、批量处理、搜索和进度路由。
- 设备目录扫描：`src/retroarch_scanner.py` 负责浅层识别本地/挂载 RetroArch 根目录和 ADB 授权设备中的 `playlists`、`thumbnails`、`retroarch.cfg` 和 `.lpl` 摘要。
- 核心流程：读取 `.lpl` -> 去重 -> 匹配中文名/英文标准名 -> 生成建议变更 -> 用户确认 -> 备份并写回 -> 下载缩略图。
- 数据来源：`data/rom-name-cn`、Libretro DAT、SQLite 缓存 `plcn.db`。
- UI 状态：`src/templates/plcn.html` 是单文件工作台 UI，已接入真实顶部统计、行勾选应用、批量选项和结构化下载汇总，但体量偏大。
- 测试状态：已有多个 `test_*.py`，但部分测试偏脚本化输出，断言和稳定 fixture 还不足。

## 模块地图

| 模块 | 关键路径 | 职责 | 当前风险 |
| --- | --- | --- | --- |
| CLI / 编排 | `src/plcn.py` | 启动 UI、解析参数、分析游戏列表、应用变更 | 核心函数承担过多职责，写回逻辑与匹配逻辑耦合 |
| 本地 Web 服务 | `src/server.py` | 本机 HTTP 路由、配置保存、预览/应用/批量任务 | 单线程服务、全局状态较多、端口处理偏粗暴 |
| 游戏列表读写 | `src/playlist_manager.py` | 读取、去重、保存 `.lpl` | 需要更多 Unicode、重复项和路径匹配回归测试 |
| 翻译数据库 | `src/database.py` | 导入 CSV、SQLite 查询、模糊搜索 | `english_name` 全局唯一可能造成跨系统冲突；别名 JSON 未充分利用 |
| 匹配器 | `src/translator.py` | 精确、反查、别名、缩写、模糊和 Libretro fallback | 需要更细的证据优先级、冲突判断和本地修正沉淀 |
| Libretro DAT | `src/libretro_db.py` | 下载/解析/搜索 DAT | 文本解析和网络缓存需要失败恢复策略 |
| 缩略图下载 | `src/thumbnail_downloader.py` | 并发下载 Boxart/Snap/Title，返回成功/失败/跳过结构化统计 | 需要补充断言式测试、失败重试策略和断点友好行为 |
| 目录扫描 | `src/retroarch_scanner.py` | 扫描本地/挂载/ADB RetroArch 目录，列出 `.lpl`、缩略图目录和配置文件 | 尚未支持 SSH/SFTP；未检查本地单个封面是否已存在 |
| Web UI | `src/templates/plcn.html` | 配置、预览、校对、进度、日志、下载明细 | 单文件过大；前端置信度是启发式，不应替代本地后端真实匹配结果 |
| 打包发布 | `plcn.spec`、`.github/workflows` | PyInstaller 分发 | 需要确认数据文件、缓存文件和平台行为一致 |

## 风险与开发难点

### P1：游戏列表写回安全

写回 `.lpl` 是项目最高价值也最高风险的环节。当前流程会在分析和应用阶段都涉及去重与匹配，应用时依赖路径/NFC 标准化并带有索引 fallback。后续必须保证预览项和实际写回项一一对应，避免重复 ROM、Unicode 差异或游戏列表变动导致错误标签写入。

优化方向：

- 为每个建议变更生成稳定 `proposal_id`。
- 应用时以路径、原始 label、db_name、索引快照组成复合校验。
- 应用后重新读取 `.lpl` 做 read-back verification。
- 备份文件改为带时间戳，保留恢复路径。

### P1：匹配准确性必须持续提高

当前匹配链路能工作，本地后端已初步输出 `match_score`、`match_status`, `match_source` 和 `match_reason`，UI 也会优先展示这些字段。但评分仍是粗粒度分类，尚未细分精确匹配、别名匹配、模糊匹配、DAT 标准化、CRC 命中和 fallback 的可信差异。项目后续的关键不是“匹配更多”，而是“越来越少误匹配”。

优化方向：

- 将当前 dict proposal 收敛为正式 `MatchResult` / `ChangeProposal` 数据结构。
- 将匹配过程拆成可解释的本地证据链：`rom_filename`、`zip_short_name`、`playlist_crc32`、`local_zip_crc`、`libretro_dat`、`exact_alias`、`manual_override`、`fuzzy_candidate`。
- 为每类证据制定固定分数区间和冲突规则，强证据冲突时直接进入 `需人工确认`。
- 本地后端保持返回权威置信度，UI 只负责展示和手动编辑后的本地标记。
- 用户手动确认的修正应能写入本地 override/alias 文件，下一次扫描成为强于模糊搜索的本地证据。
- Snatcher 误匹配、GBA 中文父目录污染、FBNeo zip short name、PS1 bin/cue 等案例必须长期保留为回归 fixture。

### P1：本地数据模型决定长期准确性

`plcn.db` 是运行缓存还是仓库资产需要明确。当前数据库 schema 中 `english_name` 全局唯一，对同名跨系统游戏可能不够安全；`name_alias(Chinese).json` 数据还需要真正纳入导入和查询链路。准确性提升不能依靠临时规则堆叠，必须沉淀到可重建、可测试的本地数据模型里。

优化方向：

- 明确 `plcn.db` 版本化策略：若是生成缓存，就不提交；若是发布资产，就提供重建脚本和版本说明。
- 将翻译唯一性调整为 `(system, english_name)` 或等价约束。
- 导入并测试中文别名 JSON。
- 增加本地 `manual_overrides.json` 或等价机制，记录用户确认过的 ROM 文件名、CRC、中文名和封面源英文名。
- 为 override 增加导入、导出和去重规则，避免用户修正被新版数据覆盖。

### P2：准确性回归样本不足

已有测试文件覆盖了批量、搜索、模糊匹配等方向，近期已开始把脚本式测试改成 pytest 断言，并新增了一批 `.lpl` fixture。下一步重点不是增加大量泛化测试，而是建立“误匹配样本库”：每个真实错误都要有最小输入、期望输出和反例。

优化方向：

- 继续将脚本式测试改为 pytest 断言。
- 扩充最小 `.lpl` fixture：中文 label、英文标准名、NFC/NFD 路径、重复条目、缺失缩略图源、ROM 文件名与中文目录冲突、同中文名跨系统冲突。
- 为 Snatcher 这类“看似有中文名但英文封面源错了”的问题增加负例测试。
- 为每类匹配来源建立评分断言，防止模糊匹配分数过高进入自动修复。
- 为写回结果、跳过原因和 read-back verification 增加快照测试。

### P2：UI 与本地后端边界需要整理

UI 已经具备工作台形态，但 `src/templates/plcn.html` 过大，状态、渲染和交互逻辑集中在一个文件里。后续继续堆功能会让回归成本上升。

近期已完成：

- 顶部数据库、DAT、离线状态改为从 `/api/stats` 获取。
- 新增 `/api/device/scan` 和 `src/retroarch_scanner.py`，可扫描本地或已挂载 RetroArch 目录并列出 `.lpl` 游戏列表摘要。
- `/api/device/scan` 已支持 ADB 授权设备，能识别 RG_476H 这类 Android 掌机上的 `/sdcard/RetroArch` 游戏列表目录。
- ADB playlist 可拉取到本地缓存进行预览；应用时会先备份设备上的 `.lpl` 再推回修改后的游戏列表。
- UI 左侧已加入“设备与目录”入口，选择扫描到的游戏列表后会自动填入路径、系统和缩略图目录，并进入预览校对。
- 预览表已增加封面缩略图和封面状态列，底部进度区改为“扫描设备 -> 生成修复计划 -> 下载官方封面”的三阶段结构。
- 预览表行复选框已参与应用请求，未勾选项不会写回或下载。
- 单个/批量下载选项已进入本地任务请求；暂未支持的选项已在 UI 中禁用并说明。
- 下载汇总改为读取后端结构化结果，区分成功、失败和跳过。
- “打开封面文件夹”改为调用本地后端打开系统文件管理器。
- 预览建议项已增加 `proposal_id`、原始 label/db_name 快照、后端 `match_score`、`match_status`、`match_source` 和 `match_reason`。
- 应用变更前会校验 proposal 快照，游戏列表在预览后被用户或外部程序修改时会跳过过期建议，避免覆盖新状态。

优化方向：

- 先保持单页应用体验，拆分 JS 状态、本地路由调用、渲染函数和样式段落。
- 所有匹配判断从本地后端返回，前端减少重复推断。
- 前端重点展示证据链、冲突原因和跳过原因，不自行“猜测”是否准确。
- 增加移动端和窄屏截图回归。

### P2：实机连接与封面存在性检查

PLCN v3.0 第一版已经支持本地目录、挂载设备目录和 ADB 授权 Android 设备，这覆盖了 Steam Deck SD 卡、Linux 掌机 U 盘挂载、Windows/macOS 本机 RetroArch 和 Android 掌机的一部分常见路径。SSH/SFTP 仍需要协议层设计，不能只靠 UI 按钮假装完成。

优化方向：

- Android ADB：已完成基础检测和 playlist 预览；后续补充多设备选择、授权状态解释、超时重试和更细的写回确认。
- Linux 掌机 SSH/SFTP：保存主机配置，探测 `~/.config/retroarch`、`/run/media/*` 等路径，明确只读扫描和写回确认。
- Steam Deck：优先支持已挂载 SD 卡目录和本机 Linux 路径，再评估 SSH 模式。
- 本地封面存在性：扫描 `thumbnails/<system>/Named_Boxarts|Named_Snaps|Named_Titles`，在 UI 中区分“已存在、可下载、缺源、下载失败”。
- 修复计划导出：在写回前生成 dry-run JSON，便于回滚、复核和问题反馈。

### P2：本地服务可靠性与边界

当前本地服务器默认端口固定，并存在杀端口进程的逻辑。服务绑定、文件浏览边界、并发请求和批量任务状态都需要更稳妥。

优化方向：

- 默认绑定 `127.0.0.1`。
- 避免默认强杀端口占用进程，改为提示或自动换端口。
- 批量任务使用明确 job id 和可查询状态。
- 文件浏览限制在用户选择过的目录上下文内。

## 阶段计划

| 阶段 | 目标 | 关键任务 | 退出标准 |
| --- | --- | --- | --- |
| 0. 本地边界与仓库卫生 | 让项目状态可信 | 更新 README/DOC；明确不接外部刮削/云匹配；确认 `plcn.db`、`plcn` 启动脚本、`output/` 的跟踪策略 | README 与代码形态一致；本地运行边界清晰 |
| 1. 准确性基线 | 先减少误匹配 | 建立误匹配 fixture；覆盖 GBA 中文父目录、Snatcher、FBNeo zip、PS1 bin/cue、Unicode、重复项、缺封面源 | 每个已知误匹配都有回归测试；强证据不会被弱证据覆盖 |
| 2. 匹配证据链 | 让匹配可解释、可调参 | 提取纯匹配 pipeline；引入细粒度证据来源、分数区间和冲突规则；导入 alias JSON；调整 DB 唯一性 | 本地后端返回权威证据链和原因；UI 不再自造置信度 |
| 3. 本地修正闭环 | 让用户校正变成下一次准确性 | 设计 `manual_overrides`；保存用户确认的 ROM/CRC/中文名/封面源；支持导入导出和去重 | 同一类手动修正下次自动命中；override 有测试和可读文件 |
| 4. 写回与封面安全 | 准确结果安全落盘 | 完善 read-back verification、备份恢复、dry-run 修复计划、本地封面存在性检查 | 写回、跳过、封面状态都可解释且可回滚 |
| 5. UI 与发布产品化 | 降低使用和维护成本 | 拆分 UI 逻辑；完善本地任务状态；验证三平台 PyInstaller；更新 release checklist | 扫描、预览、校对、应用、批量均有可复测路径 |

## 第一批建议任务

1. 建立“误匹配样本库”：优先加入 Snatcher、GBA 中文父目录污染、FBNeo zip short name、PS1 bin/cue、同名跨系统、hack/合集、缺封面源。
2. 为 `match_score` 制定更细粒度评分规则，区分 CRC/DAT 命中、文件名精确、zip short name、别名、模糊、fallback，并规定哪些分数允许自动修复。
3. 把匹配证据链从 `src/plcn.py` 中抽成纯函数或独立模块，保证每条建议都能解释“为什么是这个中文名、为什么是这个封面源”。
4. 设计本地 `manual_overrides` 文件：记录用户确认过的 ROM 文件名、CRC、系统、中文名、封面源英文名和时间。
5. 将用户手动修改后的正确结果写入本地 override，并在下一次扫描时优先于模糊搜索。
6. 将 proposal 快照校验扩展为应用后的 read-back verification，并在 UI 中展示被跳过的过期项和验证失败项。
7. 将本地封面存在性检查加入 `src/retroarch_scanner.py` 或独立 `artwork_resolver.py`，让 UI 区分已存在、待下载、缺源和下载失败。
8. 拆分 `src/templates/plcn.html`，把本地路由调用、预览表、详情栏和下载汇总拆成独立 JS 模块。

## 验证门禁

每个阶段至少运行：

```bash
python3 -m py_compile src/*.py
python3 -m pytest --collect-only -q
python3 -m pytest -q
```

涉及 UI 的阶段额外验证：

```bash
python3 src/plcn.py ui
```

并在浏览器中完成：

- 单个游戏列表预览。
- 应用前校对。
- 应用后日志和下载结果检查。
- 批量处理至少两个 `.lpl` 文件。
- 窄屏/移动端布局检查。

## 需要确认的决策

- PLCN 的长期产品形态：继续强化独立本地工具，还是重新评估 RetroArch 内部插件路线。
- `plcn.db` 是否作为发布资产随包携带，还是始终在用户本机重建。
- `manual_overrides` 是否默认保存在项目目录、用户配置目录，还是跟随打包应用的数据目录。
- 本地服务是否必须支持局域网访问；默认建议只绑定本机 `127.0.0.1`。
- 批量处理失败时的默认策略：遇错继续、遇错停止，还是用户可配置。

## 文档维护规则

- `README.md` / `README_EN.md`：只描述当前用户可用能力和基本开发命令。
- `DOC/DOC1.md`：保留早期设想与代码现实的差异说明。
- `DOC/OPTIMIZATION_PLAN.md`：作为后续开发主计划，阶段完成后及时更新状态和验证结果。
- 发布版本说明继续放在 `RELEASE_GUIDE.md` 或对应 release note 中，不与路线图混用。

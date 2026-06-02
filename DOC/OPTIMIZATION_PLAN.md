# PLCN 后续优化方案

生成日期：2026-06-02

## 目标

本方案基于当前代码实现制定，目标是把 PLCN 从“可用的本地工具”推进到“可稳定发布、可回归测试、可持续维护”的 RetroArch 游戏列表中文化与缩略图匹配工具。

当前优先级：先保障游戏列表写回安全和匹配准确性，再优化 UI 结构、批量任务可靠性和发布流程。

## 当前实现事实

- 项目形态：Python CLI + 本地 Web UI，不是 RetroArch 内部插件。
- 主入口：`src/plcn.py`，无参数或 `ui` 子命令会启动本地 Web UI。
- API 服务：`src/server.py`，提供配置、运行时统计、文件浏览/打开目录、系统列表、预览、应用、批量处理、搜索和进度接口。
- 设备目录扫描：`src/retroarch_scanner.py` 负责浅层识别本地/挂载 RetroArch 根目录和 ADB 授权设备中的 `playlists`、`thumbnails`、`retroarch.cfg` 和 `.lpl` 摘要。
- 核心流程：读取 `.lpl` -> 去重 -> 匹配中文名/英文标准名 -> 生成建议变更 -> 用户确认 -> 备份并写回 -> 下载缩略图。
- 数据来源：`data/rom-name-cn`、Libretro DAT、SQLite 缓存 `plcn.db`。
- UI 状态：`src/templates/plcn.html` 是单文件工作台 UI，已接入真实顶部统计、行勾选应用、批量选项和结构化下载汇总，但体量偏大。
- 测试状态：已有多个 `test_*.py`，但部分测试偏脚本化输出，断言和稳定 fixture 还不足。

## 模块地图

| 模块 | 关键路径 | 职责 | 当前风险 |
| --- | --- | --- | --- |
| CLI / 编排 | `src/plcn.py` | 启动 UI、解析参数、分析游戏列表、应用变更 | 核心函数承担过多职责，写回逻辑与匹配逻辑耦合 |
| Web API | `src/server.py` | 本地 HTTP API、配置保存、预览/应用/批量任务 | 单线程服务、全局状态较多、端口处理偏粗暴 |
| 游戏列表读写 | `src/playlist_manager.py` | 读取、去重、保存 `.lpl` | 需要更多 Unicode、重复项和路径匹配回归测试 |
| 翻译数据库 | `src/database.py` | 导入 CSV、SQLite 查询、模糊搜索 | `english_name` 全局唯一可能造成跨系统冲突；别名 JSON 未充分利用 |
| 匹配器 | `src/translator.py` | 精确、反查、别名、缩写、模糊和 Libretro fallback | 缺少统一置信度、来源链路和可解释结果对象 |
| Libretro DAT | `src/libretro_db.py` | 下载/解析/搜索 DAT | 文本解析和网络缓存需要失败恢复策略 |
| 缩略图下载 | `src/thumbnail_downloader.py` | 并发下载 Boxart/Snap/Title，返回成功/失败/跳过结构化统计 | 需要补充断言式测试、失败重试策略和断点友好行为 |
| 目录扫描 | `src/retroarch_scanner.py` | 扫描本地/挂载/ADB RetroArch 目录，列出 `.lpl`、缩略图目录和配置文件 | 尚未支持 SSH/SFTP；未检查本地单个封面是否已存在 |
| Web UI | `src/templates/plcn.html` | 配置、预览、校对、进度、日志、下载明细 | 单文件过大；前端置信度是启发式，不应替代后端真实匹配结果 |
| 打包发布 | `plcn.spec`、`.github/workflows` | PyInstaller 分发 | 需要确认数据文件、缓存文件和平台行为一致 |

## 风险与开发难点

### P1：游戏列表写回安全

写回 `.lpl` 是项目最高价值也最高风险的环节。当前流程会在分析和应用阶段都涉及去重与匹配，应用时依赖路径/NFC 标准化并带有索引 fallback。后续必须保证预览项和实际写回项一一对应，避免重复 ROM、Unicode 差异或游戏列表变动导致错误标签写入。

优化方向：

- 为每个建议变更生成稳定 `proposal_id`。
- 应用时以路径、原始 label、db_name、索引快照组成复合校验。
- 应用后重新读取 `.lpl` 做 read-back verification。
- 备份文件改为带时间戳，保留恢复路径。

### P1：匹配结果不可解释

当前匹配链路能工作，后端已初步输出 `match_score`、`match_status`、`match_source` 和 `match_reason`，UI 也会优先展示这些字段。但评分仍是粗粒度分类，尚未细分精确匹配、别名匹配、模糊匹配、DAT 标准化和 fallback 的可信差异。

优化方向：

- 将当前 dict proposal 收敛为正式 `MatchResult` / `ChangeProposal` 数据结构。
- 所有匹配路径细化来源、分数、原因和是否需要人工复核。
- API 保持返回后端权威置信度，UI 只负责展示和手动编辑后的本地标记。

### P1：数据模型与缓存策略不清

`plcn.db` 是运行缓存还是仓库资产需要明确。当前数据库 schema 中 `english_name` 全局唯一，对同名跨系统游戏可能不够安全；`name_alias(Chinese).json` 数据还需要真正纳入导入和查询链路。

优化方向：

- 明确 `plcn.db` 版本化策略：若是生成缓存，就不提交；若是发布资产，就提供重建脚本和版本说明。
- 将翻译唯一性调整为 `(system, english_name)` 或等价约束。
- 导入并测试中文别名 JSON。

### P2：测试保护不足

已有测试文件覆盖了批量、搜索、模糊匹配等方向，但部分测试以打印 `[PASS]` / `[FAIL]` 为主，失败不一定让 pytest 失败。`test_chinese_fuzzy.py` 还需要排查超时和 fixture 依赖。

优化方向：

- 将脚本式测试改为 pytest 断言。
- 增加最小 `.lpl` fixture：中文 label、英文标准名、NFC/NFD 路径、重复条目、缺失缩略图源。
- 为写回结果增加快照测试。

### P2：UI 与 API 边界需要整理

UI 已经具备工作台形态，但 `src/templates/plcn.html` 过大，状态、渲染和交互逻辑集中在一个文件里。后续继续堆功能会让回归成本上升。

近期已完成：

- 顶部数据库、DAT、离线状态改为从 `/api/stats` 获取。
- 新增 `/api/device/scan` 和 `src/retroarch_scanner.py`，可扫描本地或已挂载 RetroArch 目录并列出 `.lpl` 游戏列表摘要。
- `/api/device/scan` 已支持 ADB 授权设备，能识别 RG_476H 这类 Android 掌机上的 `/sdcard/RetroArch` 游戏列表目录。
- ADB playlist 可拉取到本地缓存进行预览；应用时会先备份设备上的 `.lpl` 再推回修改后的游戏列表。
- UI 左侧已加入“设备与目录”入口，选择扫描到的游戏列表后会自动填入路径、系统和缩略图目录，并进入预览校对。
- 预览表已增加封面缩略图和封面状态列，底部进度区改为“扫描设备 -> 生成修复计划 -> 下载官方封面”的三阶段结构。
- 预览表行复选框已参与应用请求，未勾选项不会写回或下载。
- 单个/批量下载选项已进入 API 请求；暂未支持的选项已在 UI 中禁用并说明。
- 下载汇总改为读取后端结构化结果，区分成功、失败和跳过。
- “打开封面文件夹”改为调用本地后端打开系统文件管理器。
- 预览建议项已增加 `proposal_id`、原始 label/db_name 快照、后端 `match_score`、`match_status`、`match_source` 和 `match_reason`。
- 应用变更前会校验 proposal 快照，游戏列表在预览后被用户或外部程序修改时会跳过过期建议，避免覆盖新状态。

优化方向：

- 先保持单页应用体验，拆分 JS 状态、API client、渲染函数和样式段落。
- 所有匹配判断从 API 返回，前端减少重复推断。
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
| 0. 文档与仓库卫生 | 让项目状态可信 | 更新 README/DOC；确认 `plcn.db`、`plcn` 启动脚本、`output/` 的跟踪策略 | `git status` 中只剩有意修改；README 与代码形态一致 |
| 1. 安全底座 | 防止错误写回和无效测试 | 改造 pytest 断言；新增 `.lpl` fixture；实现应用前后校验；强化备份 | 写回相关测试可稳定失败/通过；手动回滚路径清晰 |
| 2. 匹配核心重构 | 让匹配可解释、可回归 | 提取纯匹配 pipeline；引入 `MatchResult` / `ChangeProposal`；导入 alias JSON；调整 DB 唯一性 | API 返回权威匹配分数和原因；UI 不再自造置信度 |
| 3. 设备库与 UI/API 稳定化 | 降低维护成本 | 拆分 UI 逻辑；完善目录扫描；加入本地封面存在性检查；完善批量任务 job 状态；补齐结构化下载结果测试；改进错误提示 | 扫描、预览、应用、批量、搜索均有可复测路径 |
| 4. 发布产品化 | 稳定交付用户 | 明确缓存/数据打包；验证三平台 PyInstaller；更新 release checklist | 每个版本有构建、冒烟测试和发布说明 |

## 第一批建议任务

1. 确认仓库资产策略：`plcn.db`、`test_cn_fuzzy.db`、`output/` 和缺失的 `plcn` 启动脚本分别保留、忽略、重建还是删除。
2. 把 `test_batch.py`、`test_optimizations.py` 中的关键路径改为真正的 pytest 断言。
3. 新增 `tests/fixtures/playlists/`，覆盖中文文件名、NFC/NFD、重复条目和已中文化 label。
4. 将 proposal 快照校验扩展为应用后的 read-back verification，并在 UI 中展示被跳过的过期项。
5. 为 `match_score` 制定更细粒度评分规则，区分精确、别名、模糊、DAT 标准化和 fallback。
6. 拆分 `src/templates/plcn.html`，把 API client、预览表、详情栏和下载汇总拆成独立 JS 模块。
7. 将本地封面存在性检查加入 `src/retroarch_scanner.py` 或独立 `artwork_resolver.py`，让 UI 区分已存在与待下载。
8. 设计 ADB/SSH 连接器前先完成 dry-run 修复计划导出，降低实机写回风险。

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

- PLCN 的长期产品形态：继续强化外部本地工具，还是重新评估 RetroArch 内部插件路线。
- `plcn.db` 是否作为发布资产随包携带，还是始终在用户本机重建。
- 是否引入 LLM 辅助匹配；如果引入，需要确认 API 成本、隐私、离线降级和缓存策略。
- 本地服务是否必须支持局域网访问；默认建议只绑定本机。
- 批量处理失败时的默认策略：遇错继续、遇错停止，还是用户可配置。

## 文档维护规则

- `README.md` / `README_EN.md`：只描述当前用户可用能力和基本开发命令。
- `DOC/DOC1.md`：保留早期设想与代码现实的差异说明。
- `DOC/OPTIMIZATION_PLAN.md`：作为后续开发主计划，阶段完成后及时更新状态和验证结果。
- 发布版本说明继续放在 `RELEASE_GUIDE.md` 或对应 release note 中，不与路线图混用。

# AGENTS

## ExFAT 卷与 AppleDouble 文件

仓库位于 ExFAT 卷上，macOS 会在任何读写操作后生成 `._*` AppleDouble 文件。
它们会：让 `scripts/check_ui_js.py` 的 `node --check` 失败、被 PyInstaller
打进 .app 导致 codesign 失败、混进 `.git/objects` 引发 `non-monotonic index`
报错、被 `git add -A` 误提交。

**在运行测试、打包或提交之前，一律先清理：**

```sh
find . -name '._*' -delete   # 含 .git 与 dist/
```

## 测试

- Python：`python3 -m pytest`（`pytest.ini` 已限定 `tests/python`，约 2.5 分钟，
  613 项；`test_browser_smoke.py` 会真启 Chrome，占大部分时间）。
- JS 语法/事件处理器：`python3 scripts/check_ui_js.py`。
- Node 单测：`node tests/<name>.test.cjs`（`browser_smoke.cjs` 需 ws 参数，
  不能单独跑，由 pytest 驱动）。

## 打包（macOS）

```sh
~/.venvs/plcn-build/bin/python scripts/package_desktop.py --arch arm64
```

- venv 必须建在 APFS（`~/.venvs/plcn-build`，Python 3.13 + PyInstaller +
  pywebview）；ExFAT 上建 venv 会因 `._` 文件失败。
- PyInstaller 打包后 bundle 内的 `._*` 会让 codesign 失败，需先
  `find dist -name '._*' -delete` 再按 `package_desktop.py` 中的命令手动 ad-hoc 重签。
- self-check：`RETROARCH_ASSISTANT_HOME=$(mktemp -d)` 运行
  `Contents/MacOS/RetroArchAssistant --self-check`，结果写到该目录的
  `self-check.json`（stdout 无输出，需要 `RETROARCH_ASSISTANT_HOME`，否则静默退出码 1）。

## 前端

- 所有接口请求走 `desktopRequest`（desktop.js），它会处理 403 会话续期、
  Content-Type 校验和 `data.error`；新代码不要再写裸 `fetch` 或原生 `alert`。
- 图标统一用 `icon(name)` 引用 `workbench-icons.svg`（Tabler，1.7 线宽，24 网格），
  不要内联 SVG；`plcn.html` 里用 `data-ui-icon` 占位由 JS 填充。
- 封面/列表两视图共用 `gameLibrary.selection`，选择工具栏在
  `game-management.js` 的 `renderGameSelection`。
- `desktop.js` 最后加载；测试 harness 加载单个脚本时需要先 stub
  `desktopRequest`/`fetch`。

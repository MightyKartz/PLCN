# 一次性数据迁移 / One-time profile migration

退出旧版与新版应用后，先执行迁移，再首次启动新版。迁移保留配置、人工规则、封面备份、列表备份、恢复记录及缓存；更新其中的目录引用，备份和事务快照保持原始字节。成功后移除源目录，不建立旧路径别名。不会移动掌机或存储卡上的 ROM。

Quit both versions before migrating, and migrate **before first launching the new version**. Migration retains settings, manual rules, backups, recovery records and caches. It updates live directory references while preserving backup bytes. Sources are removed only after the new directories are complete. Device ROM files are not moved. Existing destination directories are refused to prevent overwriting data.

macOS（源码方式 / from source）：

```sh
python3 src/retroarch_assistant.py migrate \
  --from "$HOME/Library/Application Support/PLCN" \
  --cache-from "$HOME/Library/Caches/PLCN"
```

Linux（安装的 CLI / packaged CLI）：

```sh
retroarch-assistant migrate \
  --from "${XDG_DATA_HOME:-$HOME/.local/share}/PLCN" \
  --cache-from "${XDG_CACHE_HOME:-$HOME/.cache}/PLCN"
```

Windows（源码方式 / from source）：

```powershell
python src/retroarch_assistant.py migrate --from "$env:LOCALAPPDATA\PLCN"
```

如果没有独立缓存目录，省略 `--cache-from`。自定义目录请将 `--from` 替换为实际旧数据路径；需要自定义新目录时，先设置 `RETROARCH_ASSISTANT_HOME`。不再读取 `PLCN_HOME`，也不再提供 `plcn` 或 `PLCN.exe` CLI 别名。

Omit `--cache-from` when no separate cache exists. For custom profiles, supply the actual source path and set `RETROARCH_ASSISTANT_HOME` to select a custom destination. `PLCN_HOME` and the previous CLI aliases are not supported.

| 平台 / Platform | 新数据目录 / New data | 新缓存目录 / New cache |
|---|---|---|
| macOS | `~/Library/Application Support/RetroArchAssistant` | `~/Library/Caches/RetroArchAssistant` |
| Windows | `%LOCALAPPDATA%\RetroArchAssistant` | 数据目录下的 `cache` / `cache` under data |
| Linux | `$XDG_DATA_HOME/RetroArchAssistant` 或 / or `~/.local/share/RetroArchAssistant` | `$XDG_CACHE_HOME/RetroArchAssistant` 或 / or `~/.cache/RetroArchAssistant` |

迁移失败时会报告原因，保留源数据。若新版已经创建目标目录，应先退出应用并检查两边数据，手动将目标目录另存后再迁移；迁移不会自动合并或覆盖配置。

On failure, the source data remains available. If the new version has already created its destination, quit it and inspect both profiles. Move the destination aside before retrying; migration does not merge or overwrite profiles.

---
name: buddy-manager
description: Manage Claude Code buddy companion — switch species/rarity, rename, mute/unmute, apply bones-swap patch. Full TUI with live preview. 18 species × 5 rarities. Supports both native and npm installations.
---

# Buddy Manager — TUI Mode

When the user invokes `/buddy-manager`, launch the interactive TUI in a dedicated window.

**Script path:** `<SCRIPTS_DIR>/buddy.py`

---

## First-time setup (if terminal alias not yet configured)

```bash
python "<SCRIPTS_DIR>/buddy.py" setup
```

This updates `skill.md` paths for this machine, adds `alias buddy-manager=...` (and `export PYTHONUTF8=1` on Windows) to `~/.bashrc`. After running, user must `source ~/.bashrc`.

---

## Startup

**Windows** — Run via Bash tool:
```
powershell.exe -File "<SCRIPTS_DIR>/launch_buddy.ps1"
```

**Mac/Linux** — Run via Bash tool:
```
bash "<SCRIPTS_DIR>/launch_buddy.sh"
```

Both scripts check for an existing "Buddy Manager" window first:
- Found → focuses it (no new window)
- Not found → opens a new terminal window and runs buddy.py

On Windows, buddy.py also handles singleton detection via `FindWindowW('Buddy Manager')`.

---

## TUI layout

- **Left panel** — species list (↑↓ or mouse to navigate), `✓` marks current species
- **Right panel** — live buddy card preview (auto-width, animated)
- **Rarity row** — `[COMMON]` `[UNCOMMON]` `[RARE]` `[EPIC]` `[LEGENDARY]`, `✓` marks current rarity
- **Action buttons:**

| Key | Button | Action |
|-----|--------|--------|
| S | `[S] Save` | Save selection; takes effect immediately if bones-swap active |
| R | `[R] Reset` | Revert preview to current saved buddy |
| U | `[U] Reload` | Reload buddy_config.json without closing TUI (for manual edits) |
| A | `[A] Data Update` / `[A] Updating...` | Fetch fresh data from API for all 90 species×rarity combos; all-or-nothing write |
| P | `[P] Patch` | Apply / verify bones-swap patch to claude executable (native or npm) |
| M | `[M] Buddy OFF` / `[M] Buddy ON` | Toggle companion speech bubble (mute/unmute) |
| Q | `[Q] Quit` | Exit TUI |

---

## After TUI exits

Check stdout. Handle signal if present:

### `PATCH_READY:<exe_path>`

First-time bones-swap patch was applied to a **native** binary. Kill ALL Claude instances so the patched exe loads:

```python
import subprocess, sys
if sys.platform == 'win32':
    subprocess.run(['taskkill', '/F', '/IM', 'claude.exe'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
else:
    subprocess.run(['pkill', '-x', 'claude'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```

For **npm** installations, the patch is applied directly to `cli.js` (no process kill needed). The TUI displays a restart reminder instead of emitting `PATCH_READY`.

### No signal

User saved or quit normally. Do nothing.

---

## Quick CLI commands

Run directly without opening the TUI:

| Command | Description |
|---------|-------------|
| `info` | Show current buddy card + stats |
| `list` | List all 18 species with numbers |
| `show <species\|number> [rarity]` | Preview a specific species card |
| `preview <species> [rarity]` | Same as show (alias) |
| `search <species> [rarity]` | Find matching seeds in exe |
| `switch <species> [rarity]` | Switch buddy (bones-swap: instant; otherwise: restart) |
| `name <new-name>` | Rename buddy |
| `mute` / `unmute` | Toggle speech bubble |
| `restore` | Restore original ghost companion |
| `sync` | Detect and fix exe/companion mismatch |
| `cfgsync` | Sync buddy_config.json with live Claude state (CLI only) |
| `update [--force]` | Re-scan exe + regenerate all personality descriptions |
| `setup` | Update skill.md paths + add `buddy-manager` alias to ~/.bashrc |

**Species:** duck · goose · blob · cat · dragon · octopus · owl · penguin · turtle · snail · ghost · axolotl · capybara · cactus · robot · rabbit · mushroom · chonk

**Rarity:** legendary · epic · rare · uncommon · common

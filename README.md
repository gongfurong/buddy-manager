# Buddy Manager

Claude Code 伙伴管理工具。通过逆向和一次性 patch `claude.exe`（bones-swap），实现在 18 种物种 × 5 个品质之间自由切换伙伴，切换后实时生效。

---

## 功能

| 功能 | 说明 |
|------|------|
| 查看伙伴 | ASCII 卡片展示物种、品质、属性、帽子/眼睛 |
| 切换物种 | 18 种 × 5 品质随意切换，实时生效 |
| 预览 | 切换前先看卡片效果 |
| 重命名 | 自定义伙伴名字 |
| 静音控制 | 开关气泡显示（Buddy ON/OFF） |
| Patch 管理 | 一键应用/校验 bones-swap，版本升级后自动重新 patch |
| 配置同步 | 检测并修复 exe/companion 不一致 |
| 更新人格描述 | 调 Claude API 批量生成 90 种组合的 personality |

---

## 使用方式

### 通过 Claude Code（推荐）
```
/buddy-manager                    ← 打开交互 TUI
```

### 终端直接运行
```bash
buddy-manager                     ← 打开交互 TUI（首次需运行 setup）
python scripts/buddy.py info      ← 查看当前伙伴
python scripts/buddy.py switch dragon legendary
python scripts/buddy.py setup     ← 初始化 ~/.bashrc alias
```

### TUI 按钮说明

| 键 | 按钮 | 功能 |
|----|------|------|
| S | `[S] Save` | 保存选中物种/品质，bones-swap 已激活时立即生效 |
| R | `[R] Reset` | 撤销预览，恢复到当前保存的伙伴 |
| U | `[U] Reload` | 重新载入 buddy_config.json（手动改配置后刷新） |
| A | `[A] Data Update` | 调 Claude API 批量更新 90 种组合的 personality（后台运行） |
| P | `[P] Patch` | 应用 / 校验 bones-swap（首次使用或 Claude 升级后） |
| M | `[M] Buddy OFF/ON` | 切换气泡显示（mute/unmute） |
| Q | `[Q] Quit` | 退出 TUI |

---

## 完整流程

### 首次使用（bones-swap 未 patch）

在 TUI 中按 `[P] Patch`：
```
检查 exe 是否已 patch
  → 未 patch → 关闭所有 Claude 进程 → 写入 patch → 重新打开 Claude
  → 已 patch 但版本不匹配 → 提示确认 → 重新 patch
  → 已 patch 且版本匹配 → 提示已是最新，可二次确认强制 patch
```

### 正常切换（bones-swap 已激活）

```
TUI 选物种 → [S] Save
  → 更新 .claude.json companion 字段 + buddy_config.json
  → Claude Code 文件监听到变化 → 伙伴图标实时刷新
  → 下一条消息时系统提示词重建，伙伴描述同步更新
  → 无需重启，立即生效
```

### Claude Code 自动更新后（patch 丢失）

```
TUI 中 [P] Patch 会检测版本变化 → 提示重新 patch → 走首次使用流程
```

---

## 技术原理

### wyhash 模拟

Claude Code 用 `Bun.hash()` (wyhash) 决定伙伴属性：

```
hash(accountUuid + nv_seed) → species + rarity + stats + hat/eye
```

buddy.py 用纯 Python 实现了完全相同的算法。

### exe 内的伙伴生成函数

```js
// claude.exe 中的 NI() 函数（简化）
function NI() {
    let H = z8().companion;         // 读 .claude.json companion 字段
    if (!H) return;
    let { bones: $ } = cS6(lS6()); // wyhash(uuid + nv_seed) → 骨架数据
    return { ...H, ...$ }           // 原始：$ 覆盖 H → NV_ 种子永远赢
}
```

**Bones-swap patch（一次性）：**
```js
return { ...$, ...H }  // 修改后：H 覆盖 $ → companion.species 赢
```

### 为什么切换实时生效

Claude Code 对 `.claude.json` 有**文件监听**，`companion` 字段变化后 UI 伙伴图标立即刷新。系统提示词在每次发送消息前重新构建，重新读取 `.claude.json`，伙伴描述同步更新。

### Singleton 检测

TUI 启动时调用 `FindWindowW(None, 'Buddy Manager')`：
- 找到已有窗口 → 聚焦它，立即退出（不启动新实例）
- 没有 → 用 `SetConsoleTitleW('Buddy Manager')` 标记当前窗口，正常启动

`launch_buddy.ps1` 也在 `Start-Process` 之前做同样检查，避免打开多余窗口。

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `~/.claude.json` | Claude Code 核心配置，`companion` 字段存物种/品质/名字/人格/属性 |
| `claude.exe` / `claude` | Claude Code 可执行文件，含 bones-swap patch 和 NV_ 种子 |
| `buddy_config.json` | 90 种官方配置缓存（gitignore，本地生成） |
| `scripts/buddy.py` | 主脚本：wyhash 实现、patch 逻辑、TUI、所有 CLI 命令 |
| `scripts/launch_buddy.ps1` | Windows 启动器：检测已有窗口后聚焦或新开 |
| `scripts/launch_buddy.sh` | Mac/Linux 启动器：AppleScript / wmctrl / gnome-terminal 等 |
| `skill.md` | Claude Code skill 指令（`/buddy-manager` 命令执行逻辑） |

---

## 物种 & 品质

**18 种物种：**
duck · goose · blob · cat · dragon · octopus · owl · penguin · turtle · snail · ghost · axolotl · capybara · cactus · robot · rabbit · mushroom · chonk

**5 个品质：**

| 品质 | 概率 |
|------|------|
| 🟡 legendary | 1% |
| 🟣 epic | 4% |
| 🔵 rare | 10% |
| 🟢 uncommon | 25% |
| ⚪ common | 60% |

# Buddy Manager

Claude Code 伙伴管理工具。通过逆向和一次性 patch Claude 可执行文件（bones-swap），实现在 18 种物种 × 5 个品质之间自由切换伙伴，切换后实时生效。

支持 **native 安装**（`claude.exe` / ELF / Mach-O 二进制）和 **npm 安装**（`node cli.js`）两种模式，自动检测，核心功能一致。

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

### Patch 流程

在 TUI 中按 `[P] Patch`：
```
1. 比较记录版本 vs 当前文件版本
   → 不一致 / 无记录 → 进入 patch
   → 一致 → 提示"已是最新"，再按一次 [P] 可强制 re-patch

2. Patch 过程（native 和 npm 共用 .bak/.patched 机制）
   → 检查 .bak 是否存在：没有则从原文件创建
   → .bak 与当前文件版本不同（Claude 更新）→ 用当前文件更新 .bak
   → 以 .bak 为源打 patch → 生成 .patched
     - native：字节替换 return{...H,...$} → return{...$,...H}
     - npm：正则替换 cli.js 中对应 JS 函数的展开顺序

3. 应用 patch
   → native：退出所有 Claude 进程 → .patched 覆盖 exe
   → npm：.patched 覆盖 cli.js（JS 文件无进程锁，可直接覆盖），提示重启 Claude
   → 更新版本记录
```

`.bak` 文件（`claude.exe.bak` / `cli.js.bak`）：
- 首次 patch 时自动创建，永不删除
- 始终保持与当前文件版本同步
- 是所有 patch 操作的干净源

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

### 可执行文件内的伙伴生成函数

两种安装模式下，伙伴生成逻辑相同，变量名因编译/压缩而不同：

**native (`claude.exe` / ELF / Mach-O)：**
```js
// 编译后的伙伴合并函数（简化）
function NI() {
    let H = z8().companion;         // 读 .claude.json companion 字段
    if (!H) return;
    let { bones: $ } = cS6(lS6()); // wyhash(uuid + nv_seed) → 骨架数据
    return { ...H, ...$ }           // 原始：$ 覆盖 H → NV_ 种子永远赢
}
```

**npm (`cli.js`)：**
```js
// 压缩 JS 中等价函数（变量名因混淆而不同，以实际为准）
function lC() {
    let q = w8().companion;
    if (!q) return;
    let { bones: K } = tS1(eS1());
    return { ...q, ...K }           // 原始：K 覆盖 q → NV_ 种子永远赢
}
```

**Bones-swap patch（一次性，两种模式都支持）：**
```js
// native：字节替换
return { ...$, ...H }  // 修改后：H 覆盖 $ → companion.species 赢

// npm：正则替换（动态捕获变量名，适应混淆器重命名）
return { ...K, ...q }  // 修改后：q 覆盖 K → companion.species 赢
```

npm patch 使用正则动态提取变量名，版本更新后混淆器可能重命名变量，patch 仍有效。

### 为什么切换实时生效

Claude Code 对 `.claude.json` 有**文件监听**，`companion` 字段变化后 UI 伙伴图标立即刷新。系统提示词在每次发送消息前重新构建，重新读取 `.claude.json`，伙伴描述同步更新。

### Singleton 检测

启动脚本（`launch_buddy.ps1` / `launch_buddy.sh`）在打开新窗口前先检查是否已有 "Buddy Manager" 窗口：
- 找到已有窗口 → 聚焦它，不开新窗口
- 没有 → 新开终端窗口运行 buddy.py

Windows 上 buddy.py 还会调用 `FindWindowW` 做二次检测；Mac/Linux 依赖启动脚本检测。

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `~/.claude.json` | Claude Code 核心配置，`companion` 字段存物种/品质/名字/人格/属性 |
| `claude.exe` / `claude` | native 安装的 Claude Code 可执行文件 |
| `cli.js` | npm 安装的 Claude Code JS 入口（`node_modules/@anthropic-ai/claude-code/cli.js`） |
| `*.bak` | 原始文件备份（`claude.exe.bak` 或 `cli.js.bak`，首次 patch 时自动创建，永不删除） |
| `buddy_config.json` | 90 种官方配置缓存（gitignore，本地生成） |
| `scripts/buddy.py` | 主脚本：wyhash 实现、native+npm patch 逻辑、TUI、所有 CLI 命令 |
| `scripts/launch_buddy.ps1` | Windows 启动器：检测已有窗口后聚焦或新开，出错时窗口停留 |
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

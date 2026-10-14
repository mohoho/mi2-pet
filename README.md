# 觅2 · 编码代理桌面宠物

一张 8 列 × 9 行的精灵图，9 种状态。

已发布到 [Petdex](https://petdex.dev/pets/mi2)，ChatGPT（Codex）、Qoder、Claude Code、Gemini CLI、OpenCode、Kimi Code、CodeBuddy、OMP 都能装。

## 预览
| 待机 `idle` · 6 帧 | 向右跑 `runningRight` · 8 帧 | 向左跑 `runningLeft` · 8 帧 |
|:--:|:--:|:--:|
| <img src="assets/idle.gif" width="110"> | <img src="assets/runningRight.gif" width="110"> | <img src="assets/runningLeft.gif" width="110"> |
| 招手 `waving` · 4 帧 | 被抓住 `jumping` · 5 帧 | 出错 `failed` · 8 帧 |
| <img src="assets/waving.gif" width="110"> | <img src="assets/jumping.gif" width="110"> | <img src="assets/failed.gif" width="110"> |
| 等待 `waiting` · 6 帧 | 干活中 `running` · 6 帧 | 审查 `review` · 6 帧 |
| <img src="assets/waiting.gif" width="110"> | <img src="assets/running.gif" width="110"> | <img src="assets/review.gif" width="110"> |

## 安装

任选一种，装好后在对应客户端里选中「觅2」即可。

### 方式一：Petdex CLI（推荐）

```bash
npx petdex install mi2
```

需要 Node 20+；装了 Bun 就用 `bunx petdex install mi2`。命令会把宠物**同时**写进两个目录，一次覆盖 Qoder 与 Codex：

```
~/.petdex/pets/mi2/          # Qoder、Petdex 桌面版读取
~/.codex/pets/mi2/           # ChatGPT（Codex）桌面版读取
```

### 方式二：官方安装脚本

不想用 CLI，可以直接跑安装脚本，效果与 CLI 相同：

```bash
# macOS / Linux
curl -sSf https://petdex.dev/install/mi2 | sh

# Windows PowerShell
irm https://petdex.dev/install/mi2 | iex
```

### 方式三：手动拷贝

把仓库里的 `dist/mi2/` 整个目录拷到目标目录，然后**重启客户端**：

| 客户端 | 宠物目录 |
|---|---|
| Qoder / Petdex 桌面版 | `~/.petdex/pets/mi2/` |
| ChatGPT（Codex）桌面版 | `~/.codex/pets/mi2/` |

Windows 下把 `~` 换成 `C:\Users\<你>\`。目录内容：

```
mi2/
├── pet.json
└── spritesheet.png
```

### 方式四：Petdex 桌面版

下载 [Petdex Desktop](https://petdex.dev/download)（macOS / Linux / Windows）：在 **Settings → Pets** 里选中「觅2」，再到 **Settings → Agents** 给本机的编码代理一键装好钩子，宠物就会跟着每次工具调用动起来。

> 精灵图只在客户端启动时读一次，不重启看不到变化。

## 内容

| 路径 | 说明 |
|---|---|
| `dist/mi2/spritesheet.png` | 精灵图 1536×1872，单元 192×208 |
| `dist/mi2/pet.json` | `{"id":"mi2","displayName":"觅2","spriteVersionNumber":1}` |
| `assets/` | 每行合成后的动画 GIF（从精灵图逐行导出，README 展示用） |

## 格式约束

8 列 × 9 行；`cellWidth × 13 == cellHeight × 12`（本宠 192 × 208），且 `cellW ≥ 48`、`cellH ≥ 52`；
文件 ≤ 32 MB；`pet.json` 的 `id` 必须等于目录名；`spritesheet.png` 与 `spritesheet.webp` 只能存在一个。

## 素材来源

素材来自 B 站 UP 主 [space.bilibili.com/1238329219](https://space.bilibili.com/1238329219)。
版权归原作者所有，仅供个人学习使用。
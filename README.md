# 觅2 · Qoder 桌面宠物

一张 8 列 × 9 行的精灵图，9 种状态。

## 在线预览

**<https://mi2-pet-animations-e952iuq3fe9.qoder.website>**

下面每张 GIF 就是精灵图对应那一行的实际帧序与节奏：

| 待机 `idle` · 6 帧 | 向右跑 `runningRight` · 8 帧 | 向左跑 `runningLeft` · 8 帧 |
|:--:|:--:|:--:|
| <img src="assets/idle.gif" width="110"> | <img src="assets/runningRight.gif" width="110"> | <img src="assets/runningLeft.gif" width="110"> |
| 招手 `waving` · 4 帧 | 被抓住 `jumping` · 5 帧 | 出错 `failed` · 8 帧 |
| <img src="assets/waving.gif" width="110"> | <img src="assets/jumping.gif" width="110"> | <img src="assets/failed.gif" width="110"> |
| 等待 `waiting` · 6 帧 | 干活中 `running` · 6 帧 | 审查 `review` · 6 帧 |
| <img src="assets/waiting.gif" width="110"> | <img src="assets/running.gif" width="110"> | <img src="assets/review.gif" width="110"> |

每行的帧数和播放节奏由 Qoder 运行时写死，包侧改不了；没用到的列留透明即可。

## 安装

把 `dist/mi2/` 整个目录拷到 Qoder 的宠物目录下，然后**重启 Qoder**：

```
~/.petdex/pets/mi2/          # Windows: C:\Users\<你>\.petdex\pets\mi2\
├── pet.json
└── spritesheet.png
```

精灵图只在 Qoder 启动时读一次，不重启看不到变化。

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

图中角色与动画**非本人原创**，素材来自 B 站 UP 主 [space.bilibili.com/1238329219](https://space.bilibili.com/1238329219)。
本仓库只做精灵图切帧、抠像与排版，版权归原作者所有，仅供个人学习使用，请勿商用。

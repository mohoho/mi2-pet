#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把素材编译成 Qoder 桌宠包（petdex v1 规格）。

素材在 assets/ 下：五个场景 GIF（待机/工作/出错/review/挥手）当整幅底图，
跳跃.png 当蜂的大特写（抠出蜂、去掉书架），01.png 是表情包原图（等待那行由它变换生成）。

布局由 Qoder 桌面端校验，不可随意改动：
  ~/.petdex/pets/<slug>/pet.json + spritesheet.png（或 .webp，二者只能有一个）
  精灵图 8 列 x 9 行，cellWidth*13 == cellHeight*12，cellWidth>=48，cellHeight>=52
  行序 = 0 idle / 1 runningRight / 2 runningLeft / 3 waving / 4 jumping
        / 5 failed / 6 waiting / 7 running / 8 review

静图行由原图做仿射变换生成（缩放 / 旋转 / 位移 / 残影），变换在预乘 alpha 空间完成，
避免半透明边缘出现黑边；GIF 行原样取帧，不叠变换（理由见 GIF_FRAMES 注释）。

用法：python build_pet.py     然后   python verify_pet.py
"""

from pathlib import Path
import json

import numpy as np
from PIL import Image, ImageSequence
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"      # 素材：场景 GIF、特写静图、表情包原图
DIST = HERE / "dist"

SLUG = "mi2"
DISPLAY_NAME = "觅2"
PKG = DIST / SLUG             # 包目录名必须等于 slug

CELL_W, CELL_H = 192, 208     # 192*13 == 208*12
GROUND = 200                  # 角色底边所在的 y（下面留 8px 防旋转裁切）
SCALE = 0.98                  # 相对 162px 原画布的缩放；所有姿势共用，保证大小一致
FIT_MARGIN = 6                # 整幅装进格子时四周留的余量，免得内容贴到格边渗进邻格

# 场景 GIF 行的取帧。帧数必须等于该行 delays 的长度，否则 build 时直接报错。
#   工作.gif 前 18 帧是同一个场景（之后换画面）。场景本身逐像素静止，动的只有中右侧
#   握笔的那只手：手连笔一起绕笔尖摆动，六帧里 99.9% 的变化都落在 x[810,975] y[460,680]
#   这一小块（格内约 26x34 px），盒外每帧只剩个位数像素。f0~f7 与 f12/f13 是静止帧
#   （f12 与 f0 只差 1557px 的笔身抖动，循环处接得上），f8~f11 与 f14~f16 是两组"握笔写"。
#   所以干活中那行取 0,8,9,10,11,12，原样播——画面不动、手里的动作是真的。
#   不要再叠位移（会被读成"画面在抖"），也不要放大帧间差异：手和笔都是黑描边高对比，
#   外推一旦超过 1 倍就把描边顶到全黑/全白，笔会一闪黑一闪白。
#   待机.gif 第 19 帧起是黑底数字钟。
#   出错.gif 65 帧不是一整段连贯动作，而是**同一个循环重复了两遍**：每轮 29 帧 = 坐在桌前干活
#   （12~22，其中夹着两帧一抖的小动作）→ 被掀翻（23~27，硬切）→ 摔在桌上趴着（28~40）。
#   所以必须在**同一轮内**按时间递增取帧；跨轮取（每 8 帧一取）会取出"趴着→坐起来→趴着"来回跳的顺序。
#   review.gif 14 帧：0/1 是蜂正脸怼着镜头，2/3 是低头转开的过渡，4 起才是转过去之后的姿态
#   （4~8 之间只剩亚像素级的小抖动，8~13 逐像素完全相同）。只取后半段 4,5,6,7,8,13，
#   蜂全程低着头装作没看见，不再从正脸硬跳到转过去。代价是这 6 帧几乎一样（格内帧间差 0.4/255），
#   这一行读起来是定格——不要再往前取帧去"制造动作"，那正是用户要去掉的。
#   挥手.gif 17 帧是一整轮挥手：0~7 不动（f16 与 f0 逐像素相同，源循环无缝），8/9 抬起左手，
#   10/11 是手扫过镜头前的过渡（#10 那只手大得糊住整张脸，绝对不能取），12/13 抬起右手，
#   14~16 放下。取 6,9,12,16 = 静止→抬左手→抬右手→静止：两端幅度对称（与静止帧的差异
#   分别是 8.1 / 10.1），首尾同帧所以循环处不跳（差 0.9）。
GIF_FRAMES = {
    "待机.gif": [0, 3, 6, 9, 13, 17],
    "工作.gif": [0, 8, 9, 10, 11, 12],
    "出错.gif": [12, 16, 21, 24, 26, 28, 33, 38],
    "review.gif": [4, 5, 6, 7, 8, 13],
    "挥手.gif": [6, 9, 12, 16],
}

# 整幅行的缩放系数：绝对值由 load_art 按「整幅装得进格子」反推，这里只做微调。
# 左右跑这两行会连着格子边一起倾斜，特写的幅面太宽，要缩一点才不蹭到邻格；
# 肌肉形态和它们是同一张特写，不缩就会比左右跑大一圈，跟着取同一个系数对齐。
ROW_SCALE = {"idle": 1.0, "running": 1.0, "failed": 1.0,
             "jumping": 0.88, "runningRight": 0.88, "runningLeft": 0.88}

# 每行：英文名、中文名、底图、是否左右翻转、每帧变换、每帧停留毫秒（与 Qoder 运行时一致）
ROWS = [
    # 待机：底图换成 待机.gif（蜂抱着一条灰鱼趴着），帧里的动作差异是真的，不再叠变换。
    ("idle", "待机", ("待机.gif", GIF_FRAMES["待机.gif"]), False, [
        {},
    ] * 6, [280, 110, 110, 140, 140, 320]),

    # 底图用 跳跃.png 那张特写（蜂的拳头顶在左边，等于朝左）：row1 用翻转版、row2 用原图。
    # rot 为正 = 顺时针 = 顶部向右倒；残影放在行进方向的后方。
    ("runningRight", "向右跑", ("跳跃.png", "bee"), True, [
        {"sx": 0.98, "rot": -6, "dy": -2, "ghost": [(9, 0.15)]},
        {"sx": 0.98, "rot": -3, "dy": 0},
        {"sx": 0.98, "rot": -6, "dy": -2.5, "ghost": [(9, 0.15)]},
        {"sx": 0.98, "rot": -3, "dy": 0},
        {"sx": 0.98, "rot": -6, "dy": -2, "ghost": [(9, 0.15)]},
        {"sx": 0.98, "rot": -3, "dy": 0},
        {"sx": 0.97, "rot": -6.5, "dy": -3, "ghost": [(11, 0.18)]},
        {"rot": -2, "dy": 0},
    ], [120, 120, 120, 120, 120, 120, 120, 220]),

    ("runningLeft", "向左跑", ("跳跃.png", "bee"), False, [
        {"sx": 0.98, "rot": 6, "dy": -2, "ghost": [(-9, 0.15)]},
        {"sx": 0.98, "rot": 3, "dy": 0},
        {"sx": 0.98, "rot": 6, "dy": -2.5, "ghost": [(-9, 0.15)]},
        {"sx": 0.98, "rot": 3, "dy": 0},
        {"sx": 0.98, "rot": 6, "dy": -2, "ghost": [(-9, 0.15)]},
        {"sx": 0.98, "rot": 3, "dy": 0},
        {"sx": 0.97, "rot": 6.5, "dy": -3, "ghost": [(-11, 0.18)]},
        {"rot": 2, "dy": 0},
    ], [120, 120, 120, 120, 120, 120, 120, 220]),

    # 招手：底图换成 挥手.gif（蜂抬起左右手各挥一下），动作来自 GIF 本身。
    ("waving", "招手", ("挥手.gif", GIF_FRAMES["挥手.gif"]), False, [
        {},
    ] * 4, [140, 140, 140, 280]),

    # 肌肉形态：底图换成 跳跃.png（蜂抡起一拳的特写），只留蜂，旁边的书架一并抠掉。
    ("jumping", "肌肉形态", ("跳跃.png", "bee"), False, [
        {},
        {"sy": 1.02, "dy": -2},
        {"sx": 1.02, "sy": 0.99},
        {"sy": 1.01, "dy": -1},
        {"sy": 0.995},
    ], [140, 140, 140, 140, 280]),

    # 出错：底图换成 出错.gif（蜂在桌前干活时被掀翻、摔趴在桌上），动作来自 GIF 本身。
    # 取帧必须来自同一轮（见 GIF_FRAMES 注释），否则会播成"趴着→坐起来→趴着"来回跳。
    ("failed", "出错", ("出错.gif", GIF_FRAMES["出错.gif"]), False, [
        {},
    ] * 8, [140, 140, 140, 140, 140, 140, 140, 240]),

    ("waiting", "等待", "01.png", False, [
        {},
        {"dy": -2, "rot": -1.5},
        {"dy": -3.5, "rot": -2.5, "sy": 1.008},
        {"dy": -2, "rot": -1.5},
        {"dy": 0.5, "rot": 0.5},
        {},
    ], [150, 150, 150, 150, 150, 260]),

    # 干活中：底图换成 工作.gif（蜂趴在桌前敲笔记本，一只手握着笔）。
    # 「不要抖动、但手里的动作要」——这一行不叠任何位移/缩放/放大：GIF 里画面是静止的，
    # 手和笔的动作是真的，原样播就同时满足这两条（见 GIF_FRAMES 注释）。
    ("running", "干活中", ("工作.gif", GIF_FRAMES["工作.gif"]), False, [
        {},
    ] * 6, [120, 120, 120, 120, 120, 220]),

    # 拍照审查：底图换成 review.gif（一只手举枪指着蜂，蜂把头转过去装作没看见）。
    # 只取"已经转过去"的后半段（见 GIF_FRAMES 注释），所以这一行是定格，不叠变换。
    ("review", "审查", ("review.gif", GIF_FRAMES["review.gif"]), False, [
        {},
    ] * 6, [150, 150, 150, 150, 150, 280]),
]


# ---------------------------------------------------------------- 预乘 alpha 工具

def _to_pm(rgba):
    """RGBA float(0..1) -> (预乘 RGB, alpha)"""
    return rgba[..., :3] * rgba[..., 3:4], rgba[..., 3]


def _from_pm(pm_rgb, alpha):
    out = np.zeros((*alpha.shape, 4), np.float32)
    m = alpha > 1e-4
    out[..., :3] = np.where(m[..., None], pm_rgb / np.maximum(alpha[..., None], 1e-4), 0.0)
    out[..., 3] = alpha
    return np.clip(out, 0.0, 1.0)


def _resize_pm(rgba, size):
    pm, a = _to_pm(rgba)
    rgb_im = Image.fromarray((np.clip(pm, 0, 1) * 255.0 + 0.5).astype(np.uint8)).resize(size, Image.LANCZOS)
    a_im = Image.fromarray(a.astype(np.float32)).resize(size, Image.LANCZOS)
    pm2 = np.asarray(rgb_im, np.float32) / 255.0
    a2 = np.clip(np.asarray(a_im, np.float32), 0.0, 1.0)
    return _from_pm(pm2, a2)


def _warp_pm(rgba, matrix, size):
    pm, a = _to_pm(rgba)
    rgb_im = Image.fromarray((np.clip(pm, 0, 1) * 255.0 + 0.5).astype(np.uint8))
    a_im = Image.fromarray(a.astype(np.float32))
    rgb_t = rgb_im.transform(size, Image.AFFINE, matrix, resample=Image.BILINEAR, fill=0)
    a_t = a_im.transform(size, Image.AFFINE, matrix, resample=Image.BILINEAR, fill=0.0)
    pm2 = np.asarray(rgb_t, np.float32) / 255.0
    a2 = np.clip(np.asarray(a_t, np.float32), 0.0, 1.0)
    return _from_pm(pm2, a2)


def over(bg, fg):
    """fg 叠在 bg 上（都用非预乘 RGBA float）"""
    fa, ba = fg[..., 3:4], bg[..., 3:4]
    oa = fa + ba * (1.0 - fa)
    rgb = np.where(oa > 1e-5, (fg[..., :3] * fa + bg[..., :3] * ba * (1.0 - fa)) / np.maximum(oa, 1e-5), 0.0)
    return np.concatenate([rgb, oa], axis=-1)


def with_alpha(rgba, k):
    out = rgba.copy()
    out[..., 3] *= k
    return out


def brighten(rgba, k):
    out = rgba.copy()
    m = rgba[..., 3:4] > 1e-4
    out[..., :3] = np.where(m, np.clip(rgba[..., :3] * k, 0.0, 1.0), rgba[..., :3])
    return out


# ---------------------------------------------------------------- 帧生成

def resolve_src(name):
    return ASSETS / name


# ---------------------------------------------------------------- GIF 抠像
#
# 三个源 GIF 都是整幅不透明场景，只抠掉平涂的背景（工作.gif 的浅紫蓝墙、
# 待机.gif 的浅灰墙 + 米色桌沿、出错.gif 的白墙 + 米色桌面），桌椅/显示器/手枪
# 这些有深色描边的物件全部保留。
#
# 不写死背景色：从画框四边采样出现频率够高的亮色当调色板，再按颜色距离判定，
# 最后只删「从四边能走到」的那部分。这样被描边围住的同色区域（工作.gif 的翅膀
# 和墙是一个色号）不会被误删，桌沿线那种横穿整幅的细条也能一并去掉。

BG_TOL = 45           # 与背景调色板的颜色距离阈值
BG_MIN_FRAC = 0.015   # 边框上占比低于这个的颜色不算背景
BG_MIN_LEVEL = 120    # 太暗的颜色不当背景（黑色描边不参与）

_GIF_CACHE = {}


def _bg_palette(rgb):
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    q = (border // 16 * 16).astype(np.int32)
    cols, cnt = np.unique(q.reshape(-1, 3), axis=0, return_counts=True)
    keep = [c for c, n in zip(cols, cnt)
            if n >= BG_MIN_FRAC * len(border) and c.max() >= BG_MIN_LEVEL]
    return np.array(keep, np.float32)


def _cut_frame(rgb):
    """不透明场景 -> 前景 mask（rgb 是 0..255）"""
    pal = _bg_palette(rgb)
    if not len(pal):
        return np.ones(rgb.shape[:2], bool)
    dist = np.min(np.linalg.norm(rgb[..., None, :] - pal[None, None, :, :], axis=-1), axis=-1)
    bg = dist < BG_TOL
    seeds = np.zeros_like(bg)
    seeds[0], seeds[-1], seeds[:, 0], seeds[:, -1] = bg[0], bg[-1], bg[:, 0], bg[:, -1]
    return ~ndi.binary_propagation(seeds, mask=bg)


def gif_frames(name, idxs):
    """GIF 的指定帧 -> [RGBA(float 0..1)]，所有帧共用同一个取景框

    取景框取这几帧前景的并集：帧间本来就有亚像素抖动，逐帧各算 bbox 会把抖动放大成跳动；
    但动作幅度大的（出错.gif 里蜂会翻倒）必须用并集，否则会把探出头的部分切掉。
    """
    key = (name, tuple(idxs))
    if key not in _GIF_CACHE:
        raw = [np.asarray(f.convert("RGB"), np.float32)
               for f in ImageSequence.Iterator(Image.open(resolve_src(name)))]
        masks = [_cut_frame(raw[i]) for i in idxs]
        ys, xs = np.where(np.any(masks, axis=0))
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        _GIF_CACHE[key] = [
            np.dstack([raw[i][y0:y1, x0:x1] / 255.0, masks[k][y0:y1, x0:x1].astype(np.float32)])
            for k, i in enumerate(idxs)]
    return _GIF_CACHE[key]


# ---------------------------------------------------------------- 特写静图抠像
#
# 跳跃.png 是蜂的大特写，和上面三个 GIF 不是一回事：
#   · 蜂身周围有一层柔光晕，比米白底暗一点点；
#   · 右边的书架也是浅灰，和光晕同属「亮而不饱和」。
# 这两样都从画框往里灌掉。翅膀是纯白、和背景同色，但被深色描边围住，灌不进去。
# 剩下的亮像素拆成块，只有黄/白算蜂自己的；深色像素里成块的藏青（蜂身）也算蜂，
# 其余的（描边、书脊轮廓）按「离哪个块最近」归属——贴蜂的跟蜂走，贴书架的跟书架走。

BEE_MIN_AREA = 40     # 候选块最小面积，滤掉抗锯齿碎屑
BEE_OPEN_R = 4        # 深色块的「成块」标准：比这细的算描边
BEE_SOFT = 195        # 背景候选的亮度下限
BEE_SOFT_SAT = 40     # 背景候选的彩度上限（max-min）
BEE_DARK = 150        # 深/亮分界，与 _cut_frame 一致
BEE_NAVY = 20         # 深色里 B-R 超过这个才算蜂的藏青（书脊的墨绿/暗红不算）
BEE_YELLOW = (246, 217, 68)
BEE_WHITE = (251, 252, 253)
BEE_D_YELLOW, BEE_D_WHITE = 18, 25


def _disk(r):
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (yy * yy + xx * xx) <= r * r


def _nearest(cand, labels):
    """每个像素归给最近的候选块 -> 标签图"""
    ind = ndi.distance_transform_edt(cand == 0, return_distances=False, return_indices=True)
    return labels[ind[0], ind[1]]


def cut_bee(name):
    """特写静图 -> 只留蜂的 RGBA float（去背景、去光晕、去旁边的书架）"""
    rgb = np.asarray(Image.open(resolve_src(name)).convert("RGB"), np.float32)
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)

    soft = (mx >= BEE_SOFT) & (mx - mn <= BEE_SOFT_SAT)
    seeds = np.zeros_like(soft)
    seeds[0], seeds[-1], seeds[:, 0], seeds[:, -1] = soft[0], soft[-1], soft[:, 0], soft[:, -1]
    fg = ~ndi.binary_propagation(seeds, mask=soft)

    light, dark = fg & (mx >= BEE_DARK), fg & (mx < BEE_DARK)
    navy_dark = dark & (rgb[..., 2] - rgb[..., 0] > BEE_NAVY)
    lab_l, n_l = ndi.label(light, structure=np.ones((3, 3), int))
    lab_d, n_d = ndi.label(ndi.binary_opening(navy_dark, structure=_disk(BEE_OPEN_R)),
                           structure=np.ones((3, 3), int))
    comb = np.where(lab_l > 0, lab_l, 0) + np.where(lab_d > 0, n_l + lab_d, 0)

    ci = np.arange(1, n_l + n_d + 1)
    area = ndi.sum(np.ones_like(comb), labels=comb, index=ci)
    sums = np.stack([ndi.sum(rgb[..., c], labels=comb, index=ci) for c in range(3)], axis=-1)
    mean = sums / np.maximum(area, 1)[:, None]
    body = ((np.linalg.norm(mean - np.array(BEE_YELLOW, np.float32), axis=-1) < BEE_D_YELLOW) |
            (np.linalg.norm(mean - np.array(BEE_WHITE, np.float32), axis=-1) < BEE_D_WHITE))
    good = ci[(body | (ci > n_l)) & (area >= BEE_MIN_AREA)]

    # 亮像素和藏青描边在全候选里找归属；书脊那种墨绿/暗红的描边只在亮块里找——
    # 否则它们会顺着「同样是深色」被并进蜂身，跟着蜂一起留下。
    own = _nearest(comb > 0, comb)
    own_light = _nearest(lab_l > 0, lab_l)
    m = fg & np.isin(np.where(navy_dark | ~dark, own, own_light), good)

    # 蜂身黄/白连成一体算蜂；货架的横线、书脊的轮廓可能被归到蜂这边，但和蜂身不连，
    # 按分量丢掉。
    core = np.isin(comb, ci[body & (area >= BEE_MIN_AREA)])
    lab, n = ndi.label(m, structure=np.ones((3, 3), int))
    touch = ndi.maximum(core.astype(np.uint8), lab, index=np.arange(1, n + 1)) > 0
    m = np.isin(lab, np.where(touch)[0] + 1)

    ys, xs = np.where(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return np.dstack([rgb[y0:y1, x0:x1] / 255.0, m[y0:y1, x0:x1].astype(np.float32)])


def load_art(src, mirror=False, scale=SCALE, fit=False):
    """把素材装进 cell 画布：bbox 底边中点对齐到 (CELL_W/2, GROUND)

    src 是文件名，或已是裁好的 RGBA float 数组（GIF 帧，取景框在 gif_frames 里定好）。
    fit=True 时 scale 只当系数用，绝对值按「整幅装得进格子」反推——场景 GIF 带桌面，
    只能整体缩放才放得下。
    """
    if isinstance(src, str):
        rgba = np.asarray(Image.open(resolve_src(src)).convert("RGBA"), np.float32) / 255.0
        if mirror:
            rgba = rgba[:, ::-1]
        ys, xs = np.where(rgba[..., 3] > 0)
        rgba = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    else:
        rgba = src[:, ::-1] if mirror else src

    h, w = rgba.shape[:2]
    if fit:
        scale = min((CELL_W - 2 * FIT_MARGIN) / w, (GROUND - FIT_MARGIN) / h) * scale
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    art = _resize_pm(rgba, size)

    canvas = np.zeros((CELL_H, CELL_W, 4), np.float32)
    x = round((CELL_W - size[0]) / 2)
    y = GROUND - size[1]
    canvas[y:y + size[1], x:x + size[0]] = art
    return canvas


def frame(base, spec):
    """对底图施加一次变换（绕脚下基准点缩放/旋转，再整体位移）

    旋转符号约定：rot 为正是顺时针（顶部向右倒），已与 PIL rotate 做基准比对验证过。
    所以“向右跑”要用正的 rot。
    """
    sx = spec.get("sx", 1.0)
    sy = spec.get("sy", 1.0)
    rot = np.deg2rad(spec.get("rot", 0.0))
    dx = spec.get("dx", 0.0)
    dy = spec.get("dy", 0.0)

    ax, ay = CELL_W / 2.0, float(GROUND)
    c, s = np.cos(rot), np.sin(rot)
    # A = S^-1 * R^T ，把输出坐标映射回输入坐标
    a, b = c / sx, s / sx
    d, e = -s / sy, c / sy
    cx, cy = ax + dx, ay + dy
    matrix = (a, b, ax - (a * cx + b * cy), d, e, ay - (d * cx + e * cy))

    img = _warp_pm(base, matrix, (CELL_W, CELL_H))

    for gdx, galpha in spec.get("ghost", []):
        gspec = dict(spec)
        gspec["ghost"] = []
        gspec["dx"] = dx + gdx
        img = over(img, with_alpha(frame(base, gspec), galpha))
    return img


def row_sources(src, count):
    """把一行的素材解析成 count 张 RGBA float

    src 有三种写法：文件名（静图，原样用）、(文件名, "bee")（特写静图，先抠出蜂）、
    (文件名, [帧号])（GIF，按帧号取，一帧一张）。
    """
    if isinstance(src, tuple):
        name, idxs = src
        if idxs == "bee":
            return [cut_bee(name)] * count
        if len(idxs) != count:
            raise ValueError(f"{name}: 取了 {len(idxs)} 帧，但该行需要 {count} 帧")
        return gif_frames(name, idxs)
    return [src] * count


def build_spritesheet():
    sheet = Image.new("RGBA", (CELL_W * 8, CELL_H * len(ROWS)), (0, 0, 0, 0))
    empty = np.zeros((CELL_H, CELL_W, 4), np.float32)
    report = []

    for r, (name, _cn, src, mirror, specs, delays) in enumerate(ROWS):
        count = len(delays)                      # 帧数一律以 delays 为准
        srcs = row_sources(src, count)
        fit = isinstance(src, tuple)             # 场景 GIF 只能整体缩放，按装得进格子反推
        cells = []
        for i in range(count):
            base = load_art(srcs[i], mirror, SCALE * ROW_SCALE.get(name, 1.0), fit=fit)
            img = frame(base, specs[i])
            if specs[i].get("bright"):
                img = brighten(img, specs[i]["bright"])
            cells.append(img)

        for c in range(8):
            img = cells[c] if c < count else empty
            cell = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
            sheet.paste(cell, (c * CELL_W, r * CELL_H))
        report.append((r, name, count, delays))

    return sheet, report


def check_edge(sheet, thresh=0.02):
    """确认每格四周没有像素贴边（贴边说明变换被裁切了）"""
    arr = np.asarray(sheet.convert("RGBA"), np.float32)[..., 3] / 255.0
    bad = []
    for r, (name, _cn, *_rest) in enumerate(ROWS):
        for c in range(8):
            cell = arr[r * CELL_H:(r + 1) * CELL_H, c * CELL_W:(c + 1) * CELL_W]
            if cell.max() <= 0:
                continue
            hits = [f"{side}={v:.2f}" for side, v in
                    (("上", cell[0].max()), ("下", cell[-1].max()),
                     ("左", cell[:, 0].max()), ("右", cell[:, -1].max())) if v > thresh]
            if hits:
                bad.append(f"{name}[{c}] " + " ".join(hits))
    return bad


def preview_html(delays_by_row, rel_img):
    rows_js = json.dumps([
        {"name": n, "cn": cn, "frames": len(ds), "delays": ds}
        for (n, cn, _s, _m, specs, ds) in ROWS
    ], ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>觅2 桌宠 · 动画预览</title>
<style>
  :root {{ --bee:#ffd230; --deep:#f5b800; --navy:#232c4a; --soft:#3c4870; }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; padding:40px 22px 70px; font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
         color:var(--navy); background:radial-gradient(circle at 12% 0%,#fff4cf 0,transparent 42%),
         radial-gradient(circle at 88% 4%,#ffe9ef 0,transparent 36%),#fffaf0; }}
  .wrap {{ max-width:1000px; margin:0 auto }}
  h1 {{ font-size:30px; margin:0 0 6px }} h1 em {{ font-style:normal; color:var(--deep) }}
  p.sub {{ margin:0 0 26px; color:var(--soft); font-size:14px }}
  .bar {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:22px;
          background:#fff; border:1px solid #f0e4c8; border-radius:14px; padding:12px 16px; box-shadow:0 6px 20px rgba(35,44,74,.06) }}
  .bar label {{ font-size:13.5px; font-weight:600 }}
  input[type=range] {{ accent-color:var(--deep); width:190px }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:16px }}
  .card {{ background:#fff; border-radius:18px; overflow:hidden; box-shadow:0 6px 20px rgba(35,44,74,.08) }}
  .stage {{ height:190px; display:grid; place-items:end center; padding-bottom:8px;
    background-image:linear-gradient(45deg,#f7f2e6 25%,transparent 25%),linear-gradient(-45deg,#f7f2e6 25%,transparent 25%),
      linear-gradient(45deg,transparent 75%,#f7f2e6 75%),linear-gradient(-45deg,transparent 75%,#f7f2e6 75%);
    background-size:16px 16px; background-position:0 0,0 8px,8px -8px,-8px 0 }}
  .stage i {{ display:block; background-image:url('{rel_img}'); background-repeat:no-repeat; }}
  .meta {{ padding:9px 12px 12px; border-top:1px solid #f7f2e6 }}
  .meta b {{ font-size:14px }} .meta span {{ display:block; font-size:11.5px; color:#9a9488; margin-top:3px }}
  .meta code {{ font-size:11px; color:var(--soft) }}
  .strip {{ display:flex; gap:3px; margin-top:8px }}
  .strip i {{ flex:0 0 auto; background-image:url('{rel_img}'); background-repeat:no-repeat; transform-origin:top left }}
  footer {{ margin-top:34px; color:#a49e92; font-size:12.5px; line-height:1.9 }}
</style>
</head>
<body>
<div class="wrap">
  <h1>觅2 <em>·</em> 桌宠动画预览</h1>
  <p class="sub">9 种状态：待机 / 干活中 / 出错 / 审查 / 招手 五行的底图是 <code>待机.gif</code>、<code>工作.gif</code>、
    <code>出错.gif</code>、<code>review.gif</code>、<code>挥手.gif</code>（只抠掉平涂的背景，桌椅、显示器、桌上的东西都留着），
    肌肉形态和左右跑用的是 <code>跳跃.png</code> 特写（只留蜂，旁边的书架抠掉了；左右跑两行互为水平翻转），
    等待还由表情包原图变换生成。
    下面的动效与 Qoder 桌宠运行时的帧时序一致：每行能播几帧由桌面端写死。干活中那一行不叠任何位移、
    也不放大帧间差异（整幅平移会被读成“画面在抖”；放大差异会把黑描边的手和笔顶成纯黑/纯白，一闪一闪），
    原样播 工作.gif 的 6 帧——场景逐像素静止，动的只有握笔的那只手；审查那行是定格，取的是
    review.gif 里蜂把头转过去之后的几帧（正脸和过渡帧
    都不要）；招手那行取的是 挥手.gif 里蜂抬起左右手的那 4 帧，帧间差异本身就是动作，不叠变换。</p>
  <div class="bar" style="display:block;line-height:1.9">
    <b style="font-size:13.5px">触发关系</b>
    <span style="font-size:13px;color:var(--soft)">
      · <b>鼠标悬停</b> → <code>jumping</code>（肌肉形态） ·
      <b>拖拽</b> → <code>runningLeft/Right</code> ·
      <b>启动问候 2.6s</b> → <code>waving</code> ·
      <b>Agent 干活/等待/出错/审查</b> → <code>running / waiting / failed / review</code> ·
      其余时间 → <code>idle</code>
    </span>
  </div>
  <div class="bar">
    <label for="z">缩放</label><input id="z" type="range" min="40" max="220" value="100">
    <span id="zv" style="font-size:13px;color:var(--soft)">100%</span>
    <label style="margin-left:auto"><input id="strip" type="checkbox"> 显示逐帧</label>
  </div>
  <div class="grid" id="grid"></div>
  <footer>精灵图 8 列 × 9 行 · 单元 192×208 · 安装位置 ~/.petdex/pets/mi2/</footer>
</div>
<script>
const ROWS = {rows_js};
const CW = {CELL_W}, CH = {CELL_H}, SW = CW * 8, SH = CH * 9;
const grid = document.getElementById('grid');
const zoom = document.getElementById('z'), zv = document.getElementById('zv');
const stripBox = document.getElementById('strip');
let scale = 1;

const cards = ROWS.map(row => {{
  const card = document.createElement('div'); card.className = 'card';
  card.innerHTML = '<div class="stage"><i></i></div>' +
    '<div class="meta"><b>' + row.cn + ' <code>' + row.name + '</code></b>' +
    '<span>' + row.frames + ' 帧 · ' + row.delays.reduce((a, b) => a + b, 0) + 'ms</span>' +
    '<div class="strip"></div></div>';
  grid.appendChild(card);
  return {{ row, sprite: card.querySelector('.stage i'), strip: card.querySelector('.strip') }};
}});

function draw(el, row, col, s) {{
  el.style.width = (CW * s) + 'px'; el.style.height = (CH * s) + 'px';
  el.style.backgroundSize = (SW * s) + 'px ' + (SH * s) + 'px';
  el.style.backgroundPosition = (-col * CW * s) + 'px ' + (-row * CH * s) + 'px';
}}

function layout() {{
  zv.textContent = Math.round(scale * 100) + '%';
  cards.forEach((c, i) => {{
    draw(c.sprite, i, c.col || 0, scale);
    c.strip.style.display = stripBox.checked ? 'flex' : 'none';
    if (stripBox.checked && !c.strip.dataset.built) {{
      for (let f = 0; f < c.row.frames; f++) {{
        const t = document.createElement('i'); draw(t, i, f, 0.28); c.strip.appendChild(t);
      }}
      c.strip.dataset.built = '1';
    }}
  }});
}}

// 按 Qoder 运行时的帧延迟循环播放
cards.forEach((c, i) => {{
  let f = 0;
  const step = () => {{
    c.col = f; draw(c.sprite, i, f, scale);
    f = (f + 1) % c.row.frames;
    setTimeout(step, c.row.delays[c.col]);
  }};
  setTimeout(step, Math.random() * 300);
}});

zoom.addEventListener('input', () => {{ scale = zoom.value / 100; layout(); }});
stripBox.addEventListener('change', layout);
layout();
</script>
</body>
</html>
"""


def main():
    PKG.mkdir(parents=True, exist_ok=True)
    sheet, report = build_spritesheet()

    png = PKG / "spritesheet.png"
    sheet.save(png, "PNG", optimize=True)

    (PKG / "pet.json").write_text(
        json.dumps({"id": SLUG, "displayName": DISPLAY_NAME, "spriteVersionNumber": 1},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (DIST / "index.html").write_text(
        preview_html(report, f"{SLUG}/spritesheet.png"), encoding="utf-8")

    w, h = sheet.size
    print(f"包目录      : {PKG}")
    print(f"精灵图      : {w}x{h}  cell {w // 8}x{h // 9}")
    print(f"比例校验    : cellW*13={w // 8 * 13}  cellH*12={h // 9 * 12}  "
          f"{'OK' if w // 8 * 13 == h // 9 * 12 else 'FAIL'}")
    print(f"文件大小    : {png.stat().st_size / 1024:.1f} KB (上限 32MB)")
    print("行布局      :")
    for r, name, n, delays in report:
        print(f"  行{r} {name:<13} {n} 帧  延迟 {delays}")
    edge = check_edge(sheet)
    print("边缘裁切    : " + ("无" if not edge else " / ".join(edge)))


if __name__ == "__main__":
    main()

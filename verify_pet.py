#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 Qoder 桌面端 nativeDesktopPetPackageMainService 的校验规则复核宠物包。

规则来源（app.asar 反查）：pet.json <=64KB、spritesheet 只能有一个且 <=32MB、
id 必须等于目录名、displayName 1..128 无控制字符、宽%8==0、高%9==0、
cellW>=48、cellH>=52、cellW*13 == cellH*12。
"""

import json
import re
import sys
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,127})$")
PET_JSON_MAX = 64 * 1024
SHEET_MAX = 32 * 1024 * 1024

try:
    from PIL import Image
except ImportError:
    Image = None


def verify(root: Path) -> list[str]:
    msgs = []

    def ok(msg):
        msgs.append("✓ " + msg)

    def err(msg):
        msgs.append("✗ " + msg)

    slug = root.name
    ok(f"目录名 {slug!r} 合法") if SLUG_RE.match(slug) else err(f"目录名 {slug!r} 不匹配 {SLUG_RE.pattern}")

    pj = root / "pet.json"
    if not pj.is_file():
        err("缺少 pet.json")
    elif pj.is_symlink():
        err("pet.json 是符号链接")
    elif not 0 < pj.stat().st_size <= PET_JSON_MAX:
        err(f"pet.json 大小非法：{pj.stat().st_size}")
    else:
        ok(f"pet.json {pj.stat().st_size} B")
        try:
            data = json.loads(pj.read_text("utf-8"))
        except Exception as exc:
            err(f"pet.json 不是合法 JSON：{exc}")
            data = None
        if isinstance(data, dict):
            pid = data.get("id", data.get("slug"))
            ok(f"id={pid!r} 与目录名一致") if pid == slug else err(f"id={pid!r} 必须等于目录名 {slug!r}")
            name = data.get("displayName", data.get("name"))
            if not isinstance(name, str):
                err("displayName 必须是字符串")
            else:
                t = name.strip()
                if not t or len(t) > 128 or re.search(r"[\u0000-\u001f\u007f]", t):
                    err(f"displayName 非法：{name!r}")
                else:
                    ok(f"displayName={t!r}")
            ver = data.get("spriteVersionNumber", 1)
            if ver in (1, 2):
                rows = 9 if ver == 1 else 11
                ok(f"spriteVersionNumber={ver}（{rows} 行）")
            else:
                err(f"spriteVersionNumber 非法：{ver!r}")
                rows = 9
        else:
            err("pet.json 顶层必须是对象")
            rows = 9

    sheets = [p for p in (root / "spritesheet.webp", root / "spritesheet.png") if p.is_file()]
    if len(sheets) != 1:
        err(f"spritesheet 必须存在且仅存在一个，实际 {len(sheets)} 个")
        return msgs
    sheet = sheets[0]
    ok(f"spritesheet={sheet.name} {sheet.stat().st_size / 1024:.1f} KB")
    if not 0 < sheet.stat().st_size <= SHEET_MAX:
        err(f"spritesheet 大小非法：{sheet.stat().st_size}")

    if Image is None:
        err("未安装 Pillow，跳过图像校验")
        return msgs

    im = Image.open(sheet)
    w, h = im.size
    ok(f"尺寸 {w}x{h} format={im.format.lower()}")
    if im.format.lower() != sheet.suffix.lstrip(".").lower():
        err(f"扩展名与真实格式不符：{im.format} vs {sheet.suffix}")
    if getattr(im, "n_frames", 1) != 1:
        err("精灵图不能是多帧图")
    if w % 8:
        err(f"宽 {w} 不是 8 的倍数")
    if h % rows:
        err(f"高 {h} 不是 {rows} 的倍数")
    cw, ch = w // 8, h // rows
    if cw < 48 or ch < 52:
        err(f"单元过小 {cw}x{ch}（需 >=48x52）")
    elif cw * 13 != ch * 12:
        err(f"单元比例错误 {cw}x{ch}：{cw}*13={cw * 13} != {ch}*12={ch * 12}")
    else:
        ok(f"单元 {cw}x{ch} 比例 12:13 且 >=48x52")

    # 逐行确认帧数与内容
    delays = [6, 8, 8, 4, 5, 8, 6, 6, 6]
    names = ["idle", "runningRight", "runningLeft", "waving", "jumping",
             "failed", "waiting", "running", "review"]
    rgba = im.convert("RGBA")
    empty = []
    for r in range(rows):
        for c in range(8):
            cell = rgba.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            has = cell.getchannel("A").getbbox() is not None
            if c < delays[r] and not has:
                empty.append(f"{names[r]}[{c}]")
    if empty:
        err("这些被使用的帧是空白的：" + ", ".join(empty))
    else:
        ok("9 行动画帧全部有内容（空列均在未使用区）")

    return msgs


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "dist" / "mi2"
    print(f"校验 {root}\n" + "-" * 60)
    msgs = verify(root)
    for m in msgs:
        print("  " + m)
    print("-" * 60)
    bad = [m for m in msgs if m.startswith("✗")]
    if bad:
        print(f"不通过 {len(bad)} 项")
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()

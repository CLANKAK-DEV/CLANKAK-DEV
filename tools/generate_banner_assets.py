from __future__ import annotations

import math
import random
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PORTRAIT = ASSETS / "pixel-character.png"
PROFILE_REFERENCE = ASSETS / "profile-reference.png"

W, H = 1180, 610
ART_X, ART_Y = 54, 116
ART_SCALE = 2.25
MAP_W, MAP_H = 144, 170
PANEL_X, PANEL_Y = 36, 86
PANEL_W, PANEL_H = 360, 478
INFO_X = 430
VALUE_X = 706


def load_avatar() -> Image.Image:
    if PROFILE_REFERENCE.exists():
        return Image.open(PROFILE_REFERENCE).convert("RGBA")
    return Image.open(PORTRAIT).convert("RGBA")


def write_portrait(source: Image.Image) -> None:
    ASSETS.mkdir(exist_ok=True)
    pixel = source.resize((96, 96), Image.Resampling.BILINEAR).resize((288, 288), Image.Resampling.NEAREST)
    pixel.save(PORTRAIT)


def avatar_cells(source: Image.Image) -> dict[str, list[tuple[int, int]]]:
    img = ImageOps.contain(source.convert("RGB"), (MAP_W, MAP_H), method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (MAP_W, MAP_H), (160, 158, 151))
    canvas.paste(img, ((MAP_W - img.width) // 2, (MAP_H - img.height) // 2))

    bg = ImageStat.Stat(canvas.crop((0, 0, 8, 8))).mean
    diff = ImageChops.difference(canvas, Image.new("RGB", canvas.size, tuple(int(v) for v in bg))).convert("L")
    subject = diff.point(lambda p: 255 if p > 24 else 0).filter(ImageFilter.MaxFilter(3))
    gray = ImageOps.grayscale(canvas)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    boundary = ImageChops.subtract(subject, subject.filter(ImageFilter.MinFilter(3)))

    outline: list[tuple[int, int]] = []
    fill: list[tuple[int, int]] = []
    shade: list[tuple[int, int]] = []
    glint: list[tuple[int, int]] = []

    for y in range(MAP_H):
        for x in range(MAP_W):
            lum = gray.getpixel((x, y))
            is_subject = subject.getpixel((x, y)) > 0
            edge = boundary.getpixel((x, y)) > 0 or edges.getpixel((x, y)) > 48
            dither = (x * 7 + y * 11) % 23
            if edge and is_subject:
                outline.append((x, y))
            elif not is_subject:
                continue
            elif lum < 74:
                shade.append((x, y))
            elif lum < 132 and dither < 15:
                shade.append((x, y))
            elif lum < 198 and dither < 10:
                fill.append((x, y))
            elif lum >= 198 and dither < 4:
                glint.append((x, y))

    return {"fill": fill, "shade": shade, "outline": outline, "glint": glint}


def path_from_cells(cells: list[tuple[int, int]], scale: int = 1) -> str:
    return "".join(f"M{x * scale} {y * scale}h{scale}v{scale}h-{scale}z" for x, y in cells)


def art_layers(cells_by_layer: dict[str, list[tuple[int, int]]], screen: str, ink: str, accent: str, seed: int) -> str:
    rng = random.Random(seed)
    noise = []
    all_cells = [cell for cells in cells_by_layer.values() for cell in cells]
    subject_set = set(all_cells)
    for _ in range(460):
        x = rng.randrange(0, MAP_W)
        y = rng.randrange(0, MAP_H)
        if rng.random() < 0.35 or (x, y) in subject_set:
            noise.append((x, y))

    groups: list[dict[str, list[tuple[int, int]]]] = [
        {name: [] for name in cells_by_layer} for _ in range(24)
    ]
    center = (MAP_W * 0.46, MAP_H * 0.42)
    for layer, cells in cells_by_layer.items():
        for x, y in cells:
            dist = math.hypot((x - center[0]) / 1.35, y - center[1])
            idx = int(min(23, max(0, dist * 0.16 + rng.uniform(-3.5, 3.5))))
            groups[idx][layer].append((x, y))

    layer_style = {
        "fill": (accent, 0.45),
        "shade": (ink, 0.68),
        "outline": (ink, 0.96),
        "glint": ("#e0f2fe", 0.72),
    }

    parts = [f'<g transform="translate({ART_X},{ART_Y}) scale({ART_SCALE})" shape-rendering="crispEdges">']
    parts.append(f'<rect x="0" y="0" width="{MAP_W}" height="{MAP_H}" fill="{screen}" opacity="0.88"/>')
    parts.append(
        f'<path d="{"".join(f"M{x} {y}h1v1h-1z" for x in range(0, MAP_W, 3) for y in range(0, MAP_H, 3))}" '
        f'fill="{ink}" opacity="0.12"/>'
    )
    for i in range(9):
        chunk = noise[i * 40 : (i + 1) * 40]
        parts.append(
            f'<g opacity="0"><animate attributeName="opacity" values="0;0.65;0.28" '
            f'dur="1.1s" begin="{0.16 + i * 0.055:.2f}s" fill="freeze"/>'
            f'<path d="{path_from_cells(chunk)}" fill="{ink}"/></g>'
        )

    parts.append(f'<rect x="{int(center[0])}" y="{int(center[1])}" width="1" height="1" fill="{ink}" opacity="0">'
                 '<animate attributeName="opacity" values="0;1" begin="0.12s" dur="0.08s" fill="freeze"/></rect>')
    for i, group in enumerate(groups):
        begin = 0.28 + i * 0.14
        paths = []
        for layer, cells in group.items():
            if not cells:
                continue
            color, opacity = layer_style[layer]
            paths.append(f'<path d="{path_from_cells(cells)}" fill="{color}" opacity="{opacity}"/>')
        parts.append(
            f'<g class="reveal" opacity="0"><animate attributeName="opacity" values="0;1" dur="0.18s" '
            f'begin="{begin:.2f}s" fill="freeze"/>{"".join(paths)}</g>'
        )

    parts.append(
        f'<rect x="-1" y="-1" width="{MAP_W + 2}" height="{MAP_H + 2}" fill="none" stroke="currentColor" '
        'stroke-width="0.45" opacity="0.35"/>'
    )
    parts.append("</g>")
    return "\n".join(parts)


def text(x: int, y: int, value: str, fill: str, size: int = 14, weight: str = "400", **attrs: str) -> str:
    extra = " ".join(f'{k.replace("_", "-")}="{escape(v)}"' for k, v in attrs.items())
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" {extra}>{escape(value)}</text>'


def info_row(y: int, label: str, value: str, color: str, value_color: str, delay: float) -> str:
    return (
        '<g>'
        f'<text x="{INFO_X}" y="{y}" font-size="16" fill="{color}" font-weight="700">{escape(label)}</text>'
        f'<line x1="566" y1="{y - 5}" x2="690" y2="{y - 5}" stroke="{color}" stroke-opacity="0.22"/>'
        f'<text x="{VALUE_X}" y="{y}" font-size="16" fill="{value_color}" font-weight="650">{escape(value)}</text></g>'
    )


def banner(theme: str, cells_by_layer: dict[str, list[tuple[int, int]]]) -> str:
    dark = theme == "dark"
    bg0 = "#070b16" if dark else "#f8fafc"
    bg1 = "#0b1120" if dark else "#ffffff"
    top = "#0d1526" if dark else "#edf2f7"
    fg = "#f8fafc" if dark else "#0f172a"
    muted = "#94a3b8" if dark else "#64748b"
    dim = "#475569" if dark else "#94a3b8"
    cyan = "#22d3ee" if dark else "#0891b2"
    green = "#10b981" if dark else "#059669"
    screen = "#22d3ee" if dark else "#67e8f9"
    ink = "#061827" if dark else "#083344"
    portrait_dim = "#075985" if dark else "#0891b2"
    live = "#10b981" if dark else "#059669"

    rows = [
        ("Subject", "CLANKAK", 158, 0.72),
        ("Role", "Software Engineer", 182, 0.82),
        ("Origin", "Morocco", 206, 0.92),
        ("Education", "Software Engineering", 230, 1.02),
        ("Status", "Building + Learning + Shipping", 254, 1.12),
        ("Toolchain", "Android Studio, VS Code, Git, Figma", 278, 1.22),
        ("Core.Lang", "Kotlin, Dart, TypeScript, Python", 310, 1.38),
        ("Core.Frontend", "Flutter, Jetpack Compose, Angular", 334, 1.48),
        ("Core.Backend", "Firebase, Supabase", 358, 1.58),
        ("Core.Database", "Room, MySQL, SQLite", 382, 1.68),
        ("Core.Infra", "CI/CD, GitHub Actions, Git", 406, 1.78),
        ("Grid.Mail", "choukerlahoucine@gmail.com", 454, 2.04),
        ("Grid.Portfolio", "clankak.online", 478, 2.14),
        ("Grid.PlayStore", "Clankak Apps", 502, 2.24),
        ("Grid.LinkedIn", "clankak", 526, 2.34),
        ("Grid.GitHub", "@CLANKAK-DEV", 550, 2.44),
    ]
    row_svg = "\n".join(info_row(y, label, value, cyan, fg if y < 430 else cyan, delay) for label, value, y, delay in rows)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace" role="img" aria-label="CLANKAK-DEV animated profile card">
<defs><clipPath id="winClip"><rect x="2" y="2" width="1176" height="606" rx="12"/></clipPath></defs>
<rect x="2" y="2" width="1176" height="606" rx="12" fill="{bg0}"/>
<g clip-path="url(#winClip)">
<rect x="2" y="2" width="1176" height="606" fill="{bg1}"/>
<rect x="2" y="2" width="1176" height="50" fill="{top}"/>
<line x1="2" y1="52" x2="1178" y2="52" stroke="{cyan}" stroke-opacity="0.32"/>
<circle cx="30" cy="25" r="5.5" fill="#ff5f56"/><circle cx="50" cy="25" r="5.5" fill="#ffbd2e"/><circle cx="70" cy="25" r="5.5" fill="#27c93f"/>
<text x="590" y="30" text-anchor="middle" font-size="14" fill="{muted}">choukerlahoucine@gmail.com  ~  ./profile.sh --live</text>
{text(38, 77, "VISUAL.MAP", dim, 11, letter_spacing="2")}
<rect x="{PANEL_X}" y="{PANEL_Y}" width="{PANEL_W}" height="{PANEL_H}" rx="6" fill="{bg1}" stroke="{cyan}" stroke-opacity="0.46"/>
<g color="{cyan}">
{art_layers(cells_by_layer, screen, ink, portrait_dim, 23 if dark else 37)}
</g>
{text(INFO_X, 80, "SYSTEM.INFO", cyan, 14, letter_spacing="2")}
<line x1="545" y1="76" x2="1080" y2="76" stroke="{cyan}" stroke-opacity="0.20"/>
<rect x="1094" y="64" width="51" height="21" rx="4" fill="{live}"/>
<text x="1119" y="79" text-anchor="middle" font-size="12" fill="#ffffff" font-weight="800">LIVE<animate attributeName="opacity" values="1;0.45;1" dur="1.6s" repeatCount="indefinite"/></text>
<g>
<rect x="{INFO_X}" y="94" width="318" height="31" rx="4" fill="{cyan}" opacity="0.13"/>
<text x="444" y="115" font-size="16" font-weight="800" fill="{cyan}">choukerlahoucine@gmail.com</text>
<line x1="764" y1="109" x2="1145" y2="109" stroke="{cyan}" stroke-opacity="0.18"/>
</g>
{row_svg}
<g>
<text x="{INFO_X}" y="430" font-size="12" fill="{muted}" letter-spacing="2">CONTACT</text>
<line x1="515" y1="426" x2="1145" y2="426" stroke="{cyan}" stroke-opacity="0.18"/></g>
<g>
<text x="{INFO_X}" y="584" font-size="13" fill="{muted}">scan complete  /  more projects below <tspan fill="{cyan}">|<animate attributeName="fill-opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></tspan></text>
</g>
<g transform="translate(54 542)">
<text x="0" y="0" font-size="11" fill="{muted}">SCAN</text>
<rect x="48" y="-7" width="194" height="5" rx="2.5" fill="{dim}" opacity="0.35"/>
<rect x="48" y="-7" width="194" height="5" rx="2.5" fill="{cyan}" transform="scale(0 1)">
<animateTransform attributeName="transform" type="scale" values="0 1;1 1" dur="3.4s" fill="freeze"/></rect>
<text x="254" y="0" font-size="11" fill="{green}" font-weight="800">COMPLETE</text>
</g>
</g>
<rect x="3" y="3" width="1174" height="604" rx="11" fill="none" stroke="{cyan}" stroke-width="1.5" stroke-opacity="0.62"/>
</svg>
'''


def main() -> None:
    source = load_avatar()
    write_portrait(source)
    cells_by_layer = avatar_cells(source)
    (ROOT / "dark.svg").write_text(banner("dark", cells_by_layer), encoding="utf-8")
    (ROOT / "light.svg").write_text(banner("light", cells_by_layer), encoding="utf-8")


if __name__ == "__main__":
    main()

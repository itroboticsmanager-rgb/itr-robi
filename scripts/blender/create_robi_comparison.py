"""Assemble unchanged reference/render images into a self-contained SVG board."""
from pathlib import Path
import base64
import html

root=Path(__file__).resolve().parents[2]
out=root/'out'/'robi-polished'
def embedded(path):
    return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode('ascii')

panels=[
    ('01 / РЕФЕРЕНС','Форма й характер персонажа',root/'assets'/'references'/'robi-reference-3d-anniversary.png'),
    ('02 / СПЕРЕДУ','Нейтральна симетрична поза',out/'review-Front.png'),
    ('03 / ТРИ ЧВЕРТІ','Оновлена геометрія й матеріали',out/'review-ThreeQuarter.png'),
]
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="920" viewBox="0 0 1800 920">',
     '<rect width="1800" height="920" fill="#eef3f8"/>',
     '<g font-family="Segoe UI,Arial,sans-serif" fill="#193045">',
     '<text x="40" y="61" font-size="34" font-weight="650">ROBI / уточнення форми</text>',
     '<text x="40" y="97" font-size="19" fill="#506779">Версія 2 · корпус, обличчя, кисті, стопи та м’який пластик</text>']
for i,(title,subtitle,path) in enumerate(panels):
    x=40+580*i
    svg += [f'<rect x="{x}" y="133" width="560" height="679" rx="16" fill="#ffffff"/>',
            f'<text x="{x+22}" y="171" font-size="17" font-weight="700">{html.escape(title)}</text>',
            f'<text x="{x+22}" y="201" font-size="16" fill="#506779">{html.escape(subtitle)}</text>',
            f'<image x="{x+12}" y="226" width="536" height="566" preserveAspectRatio="xMidYMid meet" href="{embedded(path)}"/>']
svg += ['<text x="40" y="859" font-size="18">Шапка, реквізит і поза референсу не перенесені. У моделі збережено нейтральну позу.</text>',
        '<text x="40" y="889" font-size="16" fill="#506779">У файлі .blend: 23 кістки, керування поглядом і морганням, окремий тестовий кліп привітання.</text>',
        '</g></svg>']
(out/'reference-comparison.svg').write_text('\n'.join(svg),encoding='utf-8')
print(out/'reference-comparison.svg')

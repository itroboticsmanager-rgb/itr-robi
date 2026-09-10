"""Self-contained SVG board with the unchanged supplied reference and actual renders."""
from pathlib import Path
import base64
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'out'/'robi-sport'
def src(p): return 'data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode('ascii')
items=[('РЕФЕРЕНС','Новий образ ROBI',ROOT/'assets'/'references'/'robi-sport-reference.png'),('СПЕРЕДУ','Нейтральна A-поза',OUT/'review-Front.png'),('ТРИ ЧВЕРТІ','Геометрія, одяг і матеріали',OUT/'review-ThreeQuarter.png')]
s=['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="830" viewBox="0 0 1800 830">','<rect width="1800" height="830" fill="#eef3fa"/>','<g font-family="Segoe UI,Arial,sans-serif" fill="#193045">','<text x="40" y="56" font-size="32" font-weight="700">ROBI / жовта футболка та кросівки</text>','<text x="40" y="91" font-size="18" fill="#506779">Окрема нова модель · нейтральна поза · базовий риг</text>']
for i,(title,sub,p) in enumerate(items):
    x=40+580*i
    s += [f'<rect x="{x}" y="124" width="560" height="628" rx="16" fill="white"/>',f'<text x="{x+20}" y="161" font-size="17" font-weight="700">{title}</text>',f'<text x="{x+20}" y="190" font-size="16" fill="#506779">{sub}</text>',f'<image x="{x+12}" y="207" width="536" height="530" preserveAspectRatio="xMidYMid meet" href="{src(p)}"/>']
s += ['<text x="40" y="793" font-size="18">Шестерня й фон не входять у модель. Голова, тулуб, кінцівки та пальці мають окреме керування.</text>','</g></svg>']
(OUT/'reference-comparison.svg').write_text('\n'.join(s),encoding='utf-8')
print(OUT/'reference-comparison.svg')

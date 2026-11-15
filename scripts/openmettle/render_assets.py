"""Render the OpenMettle web assets from the brand originals.

Usage: python scripts/openmettle/render_assets.py <OpenMettle/.github checkout>

Needs Pillow. The originals are checked against the sha256 recorded in
static/static/openmettle/provenance.json, and the file is rewritten with the
sha256 of every output, so a rerun shows in `git diff` whether anything changed.
"""

import base64
import hashlib
import io
import json
import sys
from pathlib import Path

import PIL
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'static' / 'static' / 'openmettle'
PROVENANCE = OUT / 'provenance.json'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def welcome(source: Image.Image, target: Path) -> None:
    # 224 px is twice the 112 px the welcome shows. Lossless, so transparency and edges are kept.
    source.resize((224, 224), Image.LANCZOS).save(target, lossless=True, quality=100, method=6)


def square(size: int):
    """The head mark on its ivory square, as Open WebUI's favicon and touch icon are full tiles."""

    def render(source: Image.Image, target: Path) -> None:
        source.convert('RGB').resize((size, size), Image.LANCZOS).save(target, optimize=True)

    return render


def padded(size: int):
    """Mettle on ivory inside the central 72%, so a maskable icon's circle crop keeps him whole."""

    def render(source: Image.Image, target: Path) -> None:
        tile = Image.new('RGBA', (size, size), IVORY)
        inner = round(size * 0.72)
        offset = (size - inner) // 2
        tile.alpha_composite(source.resize((inner, inner), Image.LANCZOS), (offset, offset))
        tile.convert('RGB').save(target, optimize=True)

    return render


def transparent(size: int):
    def render(source: Image.Image, target: Path) -> None:
        source.resize((size, size), Image.LANCZOS).save(target, optimize=True)

    return render


def ico(source: Image.Image, target: Path) -> None:
    source.convert('RGB').save(target, sizes=[(16, 16), (32, 32), (48, 48)])


def svg(source: Image.Image, target: Path) -> None:
    # No vector master exists (brand README), so the SVG icon wraps a 128 px PNG.
    png = io.BytesIO()
    source.convert('RGB').resize((128, 128), Image.LANCZOS).save(png, format='PNG', optimize=True)
    data = base64.b64encode(png.getvalue()).decode()
    target.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="128" height="128" viewBox="0 0 128 128"><image width="128" height="128" '
        f'xlink:href="data:image/png;base64,{data}"/></svg>\n'
    )


IVORY = (0xF2, 0xEB, 0xDD, 255)
TRANSPARENT_AVATAR = 'assets/brand/current/openmettle-avatar-transparent.png'
IVORY_AVATAR = 'assets/brand/current/openmettle-avatar.png'

# Brand files keep Open WebUI's names; the branding switch copies them over the stock ones. The icon
# and splash are 256 px rather than 512 px: shown at 96 px at most, they stay sharp at 2x and are a
# quarter of the bytes. Manifest icons keep the sizes the manifests declare.
RENDERERS = {
    'mettle.webp': (TRANSPARENT_AVATAR, welcome),
    'brand/favicon.png': (IVORY_AVATAR, square(256)),
    'brand/favicon-96x96.png': (IVORY_AVATAR, square(96)),
    'brand/favicon.ico': (IVORY_AVATAR, ico),
    'brand/favicon.svg': (IVORY_AVATAR, svg),
    'brand/apple-touch-icon.png': (IVORY_AVATAR, square(180)),
    'brand/web-app-manifest-192x192.png': (TRANSPARENT_AVATAR, padded(192)),
    'brand/web-app-manifest-512x512.png': (TRANSPARENT_AVATAR, padded(512)),
    'brand/logo.png': (TRANSPARENT_AVATAR, padded(500)),
    'brand/splash.png': (TRANSPARENT_AVATAR, transparent(256)),
    'brand/splash-dark.png': (TRANSPARENT_AVATAR, transparent(256)),
}


def main(brand_repo: Path) -> None:
    provenance = json.loads(PROVENANCE.read_text())
    sources = {item['path']: item for item in provenance['sources']}
    outputs = []
    for name, (source_path, render) in RENDERERS.items():
        source_file = brand_repo / source_path
        if sha256(source_file) != sources[source_path]['sha256']:
            sys.exit(f'{source_path} differs from the original recorded in {PROVENANCE.name}')
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        render(Image.open(source_file).convert('RGBA'), target)
        if target.suffix == '.svg':
            size = '128x128 PNG in SVG'
        elif target.suffix == '.ico':
            size = '16x16, 32x32, 48x48'
        else:
            with Image.open(target) as rendered:
                size = f'{rendered.width}x{rendered.height}'
        outputs.append({'file': name, 'source': source_path, 'size': size, 'sha256': sha256(target)})
    provenance['outputs'] = outputs
    provenance['tool'] = f'scripts/openmettle/render_assets.py, Pillow {PIL.__version__}, Lanczos resampling'
    PROVENANCE.write_text(json.dumps(provenance, indent='\t') + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))

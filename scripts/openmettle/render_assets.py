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


def head(source: Image.Image, margin: float) -> Image.Image:
    """Mettle's head cropped to the artwork (alpha above 24/255), centred on a transparent square.

    The original has about 27% empty space around the head; at 16-96 px that space is what makes
    the mark unreadable, so every output starts from this crop and adds back only `margin`.
    """
    box = source.getchannel('A').point(lambda a: 255 if a > 24 else 0).getbbox()
    art = source.crop(box)
    side = round(max(art.size) * (1 + 2 * margin))
    square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    square.alpha_composite(art, ((side - art.width) // 2, (side - art.height) // 2))
    return square


def transparent(size: int, margin: float = 0.03):
    """The head alone: browser tabs, the splash and the welcome. Its ivory rim and red tab keep it
    visible on light and dark surfaces."""

    def render(source: Image.Image, target: Path) -> None:
        image = head(source, margin).resize((size, size), Image.LANCZOS)
        if target.suffix == '.webp':
            image.save(target, lossless=True, quality=100, method=6)
        else:
            image.save(target, optimize=True)

    return render


def tile(size: int, scale: float):
    """The head on a warm ivory tile (#F2EBDD). Solid, so it reads on light and dark surfaces alike;
    ivory rather than white so it does not glare in dark mode. `scale` is the head's share of the
    tile: 0.78 stays inside the inscribed circle that avatars and the sidebar crop to, 0.62 inside the
    80% safe zone of maskable install icons."""

    def render(source: Image.Image, target: Path) -> None:
        canvas = Image.new('RGBA', (size, size), IVORY)
        mark = head(source, 0).resize((round(size * scale),) * 2, Image.LANCZOS)
        offset = (size - mark.width) // 2
        canvas.alpha_composite(mark, (offset, offset))
        canvas.convert('RGB').save(target, optimize=True)

    return render


def ico(source: Image.Image, target: Path) -> None:
    head(source, 0.03).save(target, sizes=[(16, 16), (32, 32), (48, 48)])


def svg(source: Image.Image, target: Path) -> None:
    # No vector master exists (brand README), so the SVG icon wraps a 128 px PNG of the head.
    png = io.BytesIO()
    head(source, 0.03).resize((128, 128), Image.LANCZOS).save(png, format='PNG', optimize=True)
    data = base64.b64encode(png.getvalue()).decode()
    target.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="128" height="128" viewBox="0 0 128 128"><image width="128" height="128" '
        f'xlink:href="data:image/png;base64,{data}"/></svg>\n'
    )


IVORY = (0xF2, 0xEB, 0xDD, 255)
TRANSPARENT_AVATAR = 'assets/brand/current/openmettle-avatar-transparent.png'

# Brand files keep Open WebUI's names; the branding switch copies them over the stock ones. Small
# marks (tab icons, 16-96 px) use the tight head crop; the welcome and splash keep more space around
# the head. Manifest icons keep the sizes the manifests declare.
RENDERERS = {
    'mettle.webp': (TRANSPARENT_AVATAR, transparent(256, margin=0.04)),
    'brand/favicon.png': (TRANSPARENT_AVATAR, tile(256, 0.78)),
    'brand/favicon-96x96.png': (TRANSPARENT_AVATAR, transparent(96)),
    'brand/favicon.ico': (TRANSPARENT_AVATAR, ico),
    'brand/favicon.svg': (TRANSPARENT_AVATAR, svg),
    'brand/apple-touch-icon.png': (TRANSPARENT_AVATAR, tile(180, 0.78)),
    'brand/web-app-manifest-192x192.png': (TRANSPARENT_AVATAR, tile(192, 0.62)),
    'brand/web-app-manifest-512x512.png': (TRANSPARENT_AVATAR, tile(512, 0.62)),
    'brand/logo.png': (TRANSPARENT_AVATAR, tile(500, 0.62)),
    'brand/splash.png': (TRANSPARENT_AVATAR, transparent(256, margin=0.08)),
    'brand/splash-dark.png': (TRANSPARENT_AVATAR, transparent(256, margin=0.08)),
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
    provenance['tool'] = (
        f'scripts/openmettle/render_assets.py, Pillow {PIL.__version__}, Lanczos resampling; '
        'cropped to the artwork (alpha > 24) before resizing'
    )
    PROVENANCE.write_text(json.dumps(provenance, indent='\t') + '\n')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))

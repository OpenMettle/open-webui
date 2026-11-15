"""Render the OpenMettle web assets from the brand originals.

Usage: python scripts/openmettle/render_assets.py <OpenMettle/.github checkout>

Needs Pillow. The originals are checked against the sha256 recorded in
static/static/openmettle/provenance.json, and the file is rewritten with the
sha256 of every output, so a rerun shows in `git diff` whether anything changed.
"""

import hashlib
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


RENDERERS = {'mettle.webp': ('assets/brand/current/openmettle-avatar-transparent.png', welcome)}


def main(brand_repo: Path) -> None:
    provenance = json.loads(PROVENANCE.read_text())
    sources = {item['path']: item for item in provenance['sources']}
    outputs = []
    for name, (source_path, render) in RENDERERS.items():
        source_file = brand_repo / source_path
        if sha256(source_file) != sources[source_path]['sha256']:
            sys.exit(f'{source_path} differs from the original recorded in {PROVENANCE.name}')
        target = OUT / name
        render(Image.open(source_file).convert('RGBA'), target)
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

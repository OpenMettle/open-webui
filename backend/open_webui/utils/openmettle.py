"""OpenMettle branding switch.

OpenMettle is a fork of Open WebUI. With OPENMETTLE_BRANDING=true it shows OpenMettle's name and
icons where Open WebUI shows its own. It is off by default: Open WebUI's licence (LICENSE, clause 4)
allows replacing its branding only for deployments with at most 50 end users in any rolling 30 days,
with the copyright holder's written permission, or under an enterprise licence. Copyright and licence
notices stay in every case.
"""

import hashlib
import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

OPENMETTLE_NAME = 'OpenMettle'
UPSTREAM_NAME = 'Open WebUI'

# sha256 of the Open WebUI files in static/static that the switch replaces. A file that differs was
# supplied by the deployment (mounted or baked in), and the deployment's choice stands.
STOCK_BRAND_FILES = {
    'favicon.png': '5698a3e39513e7b6304ec96c309373ab3af0f70fe794293461de395a94deaa65',
    'favicon-96x96.png': 'c92e3b0db04b8851fb7d17eef5d50114f381ceffe0f85e05647aab77881fc880',
    'favicon.svg': 'a360f989dbb8f8e7e9a906baccb4648e9a90c460fbaab565247ea401554d0abb',
    'favicon.ico': 'cc302a33cae290eecb089eb0def7a8bc364ef022a725d2075a7037429c17f7c0',
    'apple-touch-icon.png': 'eb167855124c68083774d897355be1385c41e8b92963d57010518d822035fb39',
    'web-app-manifest-192x192.png': '4978545664d52450038beef47f16fd75929247a56319a377d4eae615c8c0a31b',
    'web-app-manifest-512x512.png': '96aff865f904bf549e6b2c7dda7ee12ea0cfc3b75eed756445d2f1503e5c2ee8',
    'logo.png': '0943914abd3a68644849f4bc6a54ad3a4b9ad2078bbc6cb7f131f4d6351ec9ce',
    'splash.png': '2c16a7bb24b082ba4c1e977274d7115e7debf988895624f40b66a906004d58e5',
    'splash-dark.png': 'f5ad056fd32797c77de97285cc3605cf7a8966cc006f28c72f57c12df8ca287c',
    'site.webmanifest': '1711da36108f4aaaf39301de61260d406e2a0dc25ec6881663de4f90c0086152',
}


def product_name(branding: bool) -> str:
    return OPENMETTLE_NAME if branding else UPSTREAM_NAME


def webui_name(custom_name: str | None, branding: bool) -> str:
    """The displayed name: the product's own, or a custom name followed by the product's in brackets."""
    product = product_name(branding)
    if not custom_name or custom_name == product:
        return product
    return f'{custom_name} ({product})'


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_brand_assets(
    source_dir: Path, static_dir: Path, stock_files: dict[str, str] = STOCK_BRAND_FILES
) -> list[str]:
    """Copy OpenMettle's icons over Open WebUI's in the served static folder.

    source_dir is the static folder the image ships (it holds openmettle/brand/); static_dir is
    the folder the backend serves at /static, already filled from source_dir. Returns the names
    replaced; files the deployment supplied itself are left alone.
    """
    brand_dir = source_dir / 'openmettle' / 'brand'
    replaced = []
    for name, stock in stock_files.items():
        brand_file = brand_dir / name
        if not brand_file.is_file():
            continue
        source_file = source_dir / name
        if source_file.is_file() and _sha256(source_file) != stock:
            log.info("OpenMettle branding: keeping the deployment's own %s", name)
            continue
        try:
            shutil.copyfile(brand_file, static_dir / name)
            replaced.append(name)
        except OSError as e:
            log.error('OpenMettle branding: could not replace %s: %s', name, e)
    return replaced

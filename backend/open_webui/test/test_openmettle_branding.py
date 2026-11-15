"""OpenMettle branding switch: the displayed name and the icons it puts in place of Open WebUI's.

Run from backend/ (needs only the standard library):
    python -m unittest open_webui.test.test_openmettle_branding
"""

import hashlib
import tempfile
import unittest
from pathlib import Path

from open_webui.utils.openmettle import STOCK_BRAND_FILES, apply_brand_assets, webui_name

REPO = Path(__file__).resolve().parents[3]
# The source tree's static folder, or the built one inside the image.
SHIPPED = next(
    (p for p in (REPO / 'static' / 'static', Path('/app/build/static')) if (p / 'openmettle').is_dir()),
    None,
)


class NameTests(unittest.TestCase):
    def test_off_keeps_open_webui_naming(self):
        self.assertEqual('Open WebUI', webui_name(None, False))
        self.assertEqual('Open WebUI', webui_name('Open WebUI', False))
        self.assertEqual('Family AI (Open WebUI)', webui_name('Family AI', False))

    def test_on_names_openmettle(self):
        self.assertEqual('OpenMettle', webui_name(None, True))
        self.assertEqual('OpenMettle', webui_name('', True))
        self.assertEqual('OpenMettle', webui_name('OpenMettle', True))
        self.assertEqual('Family AI (OpenMettle)', webui_name('Family AI', True))


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@unittest.skipIf(SHIPPED is None, 'no static folder with openmettle/ found')
class ShippedAssetTests(unittest.TestCase):
    def test_stock_hashes_match_open_webuis_files(self):
        # Fails after a rebase that changed an Open WebUI icon: update STOCK_BRAND_FILES.
        for name, digest in STOCK_BRAND_FILES.items():
            self.assertEqual(digest, hashlib.sha256((SHIPPED / name).read_bytes()).hexdigest(), name)

    def test_every_stock_file_has_an_openmettle_replacement(self):
        for name in STOCK_BRAND_FILES:
            self.assertTrue((SHIPPED / 'openmettle' / 'brand' / name).is_file(), name)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = Path(tmp.name) / 'build-static'
        self.served = Path(tmp.name) / 'served'
        self.served.mkdir()
        # A stock favicon (its recorded hash is the fixture's), a deployment's own logo, and a splash the
        # image does not ship at all.
        self.stock = write(self.source / 'favicon.png', b'open webui favicon')
        write(self.source / 'logo.png', b'deployment logo')
        for name in ('favicon.png', 'logo.png', 'splash.png'):
            write(self.source / 'openmettle' / 'brand' / name, f'openmettle {name}'.encode())
        for path in self.source.glob('*.png'):  # what config.py does before the switch runs
            write(self.served / path.name, path.read_bytes())

    def apply(self):
        stock = dict(STOCK_BRAND_FILES, **{'favicon.png': hashlib.sha256(self.stock.read_bytes()).hexdigest()})
        return apply_brand_assets(self.source, self.served, stock)

    def test_replaces_stock_icons_and_keeps_the_deployments_own(self):
        replaced = self.apply()
        self.assertEqual(['favicon.png', 'splash.png'], sorted(replaced))
        self.assertEqual(b'openmettle favicon.png', (self.served / 'favicon.png').read_bytes())
        self.assertEqual(b'openmettle splash.png', (self.served / 'splash.png').read_bytes())
        self.assertEqual(b'deployment logo', (self.served / 'logo.png').read_bytes())

    def test_names_without_a_replacement_are_left_alone(self):
        self.apply()
        self.assertFalse((self.served / 'favicon.ico').exists())

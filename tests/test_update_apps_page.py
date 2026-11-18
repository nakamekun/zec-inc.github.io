"""Offline fixture coverage for SITE-WHY-1 (stdlib unittest only)."""
from __future__ import annotations

import hashlib
import html
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_apps_page as gen
import validate_apps_pages as validator

FIXTURES = Path(__file__).parent / 'fixtures'


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


def legacy_overrides():
    overrides = load_fixture('app-details-why-compare.json')
    for value in overrides.values():
        for key in gen.OPTIONAL_DETAIL_FIELDS:
            value.pop(key, None)
        value['locales'] = {code: loc for code, loc in value.get('locales', {}).items() if code == 'ja'}
        for loc in value['locales'].values():
            for key in gen.OPTIONAL_DETAIL_FIELDS:
                loc.pop(key, None)
    return overrides


class AppPageTests(unittest.TestCase):
    def setUp(self):
        self.apps = load_fixture('apps-why-compare.json')
        self.overrides = load_fixture('app-details-why-compare.json')
        self.ctx = gen.BuildContext(strict=True)
        gen.APP_CATEGORY_CACHE.clear()
        gen.RELATED_BY_CATEGORY.clear()
        gen.CHANGED_PAGES.clear()

    def render(self, locale='en'):
        return gen.render_detail_page(self.apps[0], self.overrides, self.ctx, locale)

    def test_sections_order_localization_and_escaping(self):
        for locale in ('en', 'ja', 'es', 'de', 'fr'):
            with self.subTest(locale=locale):
                page = self.render(locale)
                strings = gen.ui_strings(locale)
                headings = ['why', 'features', 'usage', 'comparison', 'suitability', 'pricing', 'privacy', 'faq']
                positions = [page.index('>' + html.escape(strings[key]) + '</h2>') for key in headings]
                self.assertEqual(positions, sorted(positions))
                self.assertNotIn('>' + html.escape(strings['overview']) + '</h2>', page)
                self.assertLess(page.index('class="shots"'), positions[0])
                self.assertIn('<time datetime="2026-11-18">', page)
                self.assertIn('<table class="comparison-table"', page)
                for key in ('best_for', 'not_for'):
                    self.assertIn(html.escape(strings[key]) + '</h3>', page)
                if locale in gen.MANUAL_LOCALES:
                    self.assertIn(f'https://apps.apple.com/{locale}/app/', page)
        self.assertIn('2026年11月18日時点の情報', self.render('ja'))
        self.overrides['6780724192']['comparison']['rows'][0]['option'] = '<script>alert("x")</script>'
        self.assertIn('&lt;script&gt;', self.render())
        self.assertNotIn('<script>alert(', self.render())
        self.assertEqual(self.ctx.warnings, [])

    def test_no_new_fields_preserves_legacy_html(self):
        # Hashes were generated from the pre-change renderer using these same fixtures.
        overrides = legacy_overrides()
        expected = load_fixture('app-detail-legacy-sha256.json')
        for app in self.apps:
            for locale in gen.app_locales(app, overrides):
                page = gen.render_detail_page(app, overrides, self.ctx, locale)
                self.assertEqual(hashlib.sha256(page.encode()).hexdigest(), expected[app['slug'] + '/' + locale])
                self.assertNotIn('id="why-heading"', page)
                self.assertNotIn('class="comparison-table"', page)
                self.assertNotIn('id="suitability-heading"', page)

    def test_optional_fields_are_independent_and_not_inherited(self):
        full = self.overrides['6780724192']
        for key in gen.OPTIONAL_DETAIL_FIELDS:
            candidate = legacy_overrides()
            candidate['6780724192'][key] = full[key]
            content = gen.detail_content(self.apps[0], candidate, self.ctx)
            self.assertTrue(content[key])
            localized = gen.detail_content(self.apps[0], candidate, self.ctx, 'ja')
            self.assertFalse(localized[key])
            for other in gen.OPTIONAL_DETAIL_FIELDS - {key}:
                self.assertFalse(content[other])
            gen.render_detail_page(self.apps[0], candidate, self.ctx)

    def test_nested_validation(self):
        gen.validate_overrides(self.overrides, self.ctx)
        self.assertEqual(self.ctx.warnings, [])
        cases = [
            ('why', 'text'), ('why', [5]), ('best_for', {}), ('not_for', [False]),
            ('comparison', []),
            *[('comparison', {**self.overrides['6780724192']['comparison'], key: value}) for key, value in (
                ('intro', 5), ('summary', None), ('checked_on', 5), ('checked_on', '2026-02-30'),
                ('checked_on', '2026-1-01'), ('rows', {}), ('rows', ['bad']),
                ('rows', [{'option': 3, 'kind': 'unknown', 'good_at': [], 'trade_off': False}]),
            )],
        ]
        for key, value in cases:
            for locale in ('en', 'ja', 'es'):
                with self.subTest(key=key, value=value, locale=locale):
                    obj = {key: value}
                    ctx = gen.BuildContext()
                    gen.validate_overrides({'id': obj if locale == 'en' else {'locales': {locale: obj}}}, ctx)
                    self.assertTrue(ctx.warnings)
                    self.assertIn(key, ' '.join(ctx.warnings))

    def test_locales_require_content_and_light_locales_still_work(self):
        self.assertEqual(gen.app_locales(self.apps[1], self.overrides), ['en'])
        self.assertEqual(gen.app_locales(self.apps[2], self.overrides), ['en'])
        self.assertEqual(set(gen.app_locales(self.apps[0], self.overrides)), {'en', 'ja', 'es', 'de', 'fr'})
        self.apps[2]['l10n'] = {'ko': {'trackName': '공유 전 흐림', 'description': '사진을 공유하기 전에 내용을 확인하세요.'}}
        self.assertEqual(gen.app_locales(self.apps[2], self.overrides), ['en', 'ko'])
        self.assertIn('공유 전 흐림', gen.render_light_detail_page(self.apps[2], self.overrides, 'ko'))
        self.assertEqual(set(gen.site_locales(self.overrides)), {'ja', 'es', 'de', 'fr'})

    def test_generation_hreflang_sitemap_indexes_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            for name, relative in {
                'ROOT_DIR': '.', 'APPS_DIR': 'apps', 'APPS_PAGE': 'apps/index.html',
                'SITEMAP_XML': 'sitemap.xml', 'LLMS_TXT': 'llms.txt',
            }.items():
                stack.enter_context(patch.object(gen, name, root / relative))
            gen.APPS_DIR.mkdir()
            gen.APPS_PAGE.write_text((ROOT / 'apps/index.html').read_text())
            locales = ['en'] + gen.site_locales(self.overrides)
            gen.update_apps_index(self.apps, self.overrides)
            urls = gen.write_detail_pages(self.apps, self.overrides, self.ctx)
            urls += gen.write_category_pages(self.apps, self.overrides, self.ctx, locales)
            urls += gen.write_locale_indexes(self.apps, self.overrides, locales)
            gen.write_sitemap(urls)
            gen.write_llms(self.apps, self.overrides)
            for code in ('es', 'de', 'fr'):
                self.assertTrue((root / f'apps/ocr-copy/{code}/index.html').exists())
                self.assertFalse((root / f'apps/foot-size-check/{code}').exists())
                self.assertFalse((root / f'apps/blur-before-share/{code}').exists())
                self.assertFalse((root / f'apps/family/{code}').exists())
                for relative in (f'apps/{code}', f'apps/productivity/{code}'):
                    page = (root / relative / 'index.html').read_text()
                    self.assertIn(f'/apps/ocr-copy/{code}/', page)
                    self.assertNotIn('Foot Size Check', page)
                    self.assertNotIn('Blur Before Share', page)
                for relative in ('apps', 'apps/ocr-copy', 'apps/productivity'):
                    page = (root / relative / 'index.html').read_text()
                    self.assertIn(f'hreflang="{code}"', page)
                    self.assertIn(f'href="/{relative}/{code}/"', page)
                self.assertIn(f'https://zec-inc.jp/apps/ocr-copy/{code}/', gen.SITEMAP_XML.read_text())
                self.assertNotIn(f'https://zec-inc.jp/apps/foot-size-check/{code}/', gen.SITEMAP_XML.read_text())
            errors = []
            with patch.object(validator, 'SITEMAP_XML', gen.SITEMAP_XML):
                validator.validate_sitemap(set(urls), errors)
            self.assertEqual(errors, [])
            for path in root.rglob('*.html'):
                validator.validate_json_ld(path, validator.parse_page(path), errors)
            self.assertEqual(errors, [])
            llms = gen.LLMS_TXT.read_text()
            self.assertIn('Copy text from a photo. Copy printed text without retyping it.', llms)
            self.assertNotIn('This second sentence', llms)
            # Removed/empty translations must remove pages and alternate links too.
            self.overrides['6780724192']['locales'] = {}
            locales = ['en'] + gen.site_locales(self.overrides)
            gen.update_apps_index(self.apps, self.overrides)
            urls = gen.write_detail_pages(self.apps, self.overrides, self.ctx)
            urls += gen.write_category_pages(self.apps, self.overrides, self.ctx, locales)
            urls += gen.write_locale_indexes(self.apps, self.overrides, locales)
            gen.write_sitemap(urls)
            for code in ('es', 'de', 'fr'):
                self.assertFalse((root / f'apps/{code}').exists())
                self.assertFalse((root / f'apps/ocr-copy/{code}').exists())
                self.assertFalse((root / f'apps/productivity/{code}').exists())
                self.assertNotIn(f'hreflang="{code}"', gen.APPS_PAGE.read_text())
                self.assertNotIn(f'/ocr-copy/{code}/', gen.SITEMAP_XML.read_text())
            self.assertEqual(self.ctx.warnings, [])

    def test_llms_truncates_why_like_existing_summaries(self):
        self.overrides['6780724192']['why'] = ['A ' + 'long reason ' * 30 + '. Second sentence.']
        with tempfile.TemporaryDirectory() as directory, patch.object(gen, 'LLMS_TXT', Path(directory) / 'llms.txt'):
            gen.write_llms(self.apps, self.overrides)
            text = gen.LLMS_TXT.read_text()
            self.assertIn(gen.truncate_text('A ' + 'long reason ' * 30 + '.', 110), text)
            self.assertNotIn('Second sentence', text)


if __name__ == '__main__':
    unittest.main()

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SiteStructureTests(unittest.TestCase):
    def test_required_sections_and_assets_exist(self):
        html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        section_ids = (
            "overview",
            "demo",
            "architecture",
            "evidence",
            "boundaries",
            "roadmap",
            "feedback",
        )
        for section_id in section_ids:
            self.assertIn(f'id="{section_id}"', html)
        self.assertIn('id="language-toggle"', html)
        self.assertIn('src="assets/js/app.js"', html)
        self.assertIn('href="assets/css/site.css"', html)
        for asset in (
            "docs/assets/css/site.css",
            "docs/assets/js/app.js",
            "docs/assets/js/replay.js",
            "docs/assets/data/demo-data.json",
        ):
            self.assertTrue((ROOT / asset).is_file(), asset)

    def test_every_static_translation_key_has_two_language_entries(self):
        html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        app = (ROOT / "docs/assets/js/app.js").read_text(encoding="utf-8")
        keys = set(re.findall(r'data-i18n="([^"]+)"', html))
        self.assertGreater(len(keys), 10)
        for key in keys:
            self.assertGreaterEqual(app.count(f'"{key}"'), 2, key)

    def test_copy_has_no_organization_specific_wording(self):
        site_files = [
            ROOT / "docs/index.html",
            ROOT / "docs/assets/js/app.js",
        ]
        text = "\n".join(
            path.read_text(encoding="utf-8") for path in site_files
        )
        for forbidden in ("Huawei", "华为"):
            self.assertNotIn(forbidden, text)

    def test_visual_companion_output_is_ignored(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".superpowers/", lines)

    def test_css_contains_accessible_motion_and_svg_routes(self):
        css = (ROOT / "docs/assets/css/site.css").read_text(encoding="utf-8")
        for required in (
            "prefers-reduced-motion",
            ".network-svg",
            ".edge.route-a",
            ".edge.route-b",
            ".edge.fault",
            ":focus-visible",
            "@media (max-width: 760px)",
        ):
            self.assertIn(required, css)

    def test_app_contains_required_interactions_and_translation_keys(self):
        app = (ROOT / "docs/assets/js/app.js").read_text(encoding="utf-8")
        for required in (
            "renderReplay",
            "renderEvidence",
            "setLanguage",
            "showDataError",
            'localStorage.setItem("limer-language"',
            "document.documentElement.lang = language",
            'addEventListener("click"',
            'addEventListener("input"',
            'addEventListener("change"',
        ):
            self.assertIn(required, app)
        self.assertIn('"hero.title"', app)
        self.assertIn('"roadmap.standby.title"', app)
        self.assertIn('"feedback.telemetry"', app)
        self.assertIn('payload.meta.formal_run_count', app)
        self.assertIn('payload.meta.gate_pass_count', app)
        self.assertIn('payload.conditions.C3.gate_pass_count', app)

    def test_replay_svg_uses_the_approved_anchored_paths(self):
        app = (ROOT / "docs/assets/js/app.js").read_text(encoding="utf-8")
        paths = (
            'd="M59 42 H178 Q207 42 227 48"',
            'd="M59 218 H78 V103 Q78 92 90 92 H194 Q214 92 227 74"',
            'd="M491 42 H372 Q343 42 323 48"',
            'd="M491 218 H472 V103 Q472 92 460 92 H356 Q336 92 323 74"',
            'd="M59 42 H68 V157 Q68 168 80 168 H194 Q214 168 227 184"',
            'd="M59 218 H178 Q207 218 227 212"',
            'd="M491 42 H482 V157 Q482 168 470 168 H356 Q336 168 323 184"',
            'd="M491 218 H372 Q343 218 323 212"',
        )
        for path in paths:
            self.assertIn(path, app)

    def test_pages_workflow_uses_current_official_static_actions(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(
            encoding="utf-8"
        )
        for required in (
            "actions/checkout@v4",
            "actions/configure-pages@v5",
            "actions/upload-pages-artifact@v3",
            "actions/deploy-pages@v5",
            "path: docs",
            "pages: write",
            "id-token: write",
        ):
            self.assertIn(required, workflow)

    def test_readme_links_to_the_interactive_site(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Interactive project demo", readme)
        self.assertIn("https://sophie508.github.io/LIMER_draft/", readme)


if __name__ == "__main__":
    unittest.main()

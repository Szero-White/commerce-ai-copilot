"""Guard static UI assets without needing a hosted language model."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.config import ROOT


def test_modular_css_assets_are_served_in_order(tmp_path):
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    imports = re.findall(r"@import url\(['\"]\./styles/([^'\"]+)['\"]\);", css)
    assert imports == [
        "foundation.css",
        "overview.css",
        "assistant.css",
        "workflows.css",
        "responsive.css",
        "agent-support.css",
        "responsive-overrides.css",
    ]

    client = TestClient(create_app(data_path=tmp_path / "ui.db"))
    assert client.get("/assets/style.css").status_code == 200
    for name in imports:
        response = client.get(f"/assets/styles/{name}")
        assert response.status_code == 200, name
        assert response.headers["content-type"].startswith("text/css"), name


def test_ui_entrypoints_and_favicon_load_without_changing_api(tmp_path):
    client = TestClient(create_app(data_path=tmp_path / "ui.db"))
    html = client.get("/")
    assert html.status_code == 200
    assert '/assets/style.css' in html.text
    assert '/assets/app.js' in html.text
    assert '/assets/favicon.svg' in html.text

    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/favicon.svg").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"


# --- Static guards for the UI polish pass (no browser needed; the real-Chrome run covers rendering) ---------------------------
STYLES = ROOT / "web" / "styles"
# Glyph icons and decorative marks are sized individually; all other text must use the shared scale.
GLYPH_SELECTORS = {".send", ".brand-icon", ".nav-ico", ".orb-core", ".feature-icon", ".notice-icon",
                   ".preview-placeholder span"}


def _rules():
    for path in sorted(STYLES.glob("*.css")):
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
            yield path.name, " ".join(selector.split()), body


def test_text_sizes_use_the_shared_scale_or_are_glyph_icons():
    literal = []
    for name, selector, body in _rules():
        values = re.findall(r"font-size:\s*([^;]+)", body) + re.findall(r"font:\s*[0-9]+\s+([^/;\s]+)", body)
        for value in values:
            value = value.strip()
            if value.startswith(("var(--font-", "clamp(")) or selector in GLYPH_SELECTORS:
                continue
            literal.append((name, selector, value))
    assert not literal, literal


def test_typography_scale_has_no_tiny_or_fractional_sizes():
    foundation = (STYLES / "foundation.css").read_text(encoding="utf-8")
    sizes = [float(v) for v in re.findall(r"--font-[a-z0-9]+:\s*([0-9.]+)px", foundation)]
    assert sizes == [11, 12, 13, 14, 15, 17, 21, 24, 30]
    assert "--font-meta" not in foundation and "--font-label" not in foundation


def test_status_chips_never_wrap_and_panel_headers_let_titles_shrink():
    bodies = {}
    for _, selector, body in _rules():
        bodies.setdefault(selector, []).append(body)
    assert any("white-space: nowrap" in b and "flex: none" in b for b in bodies[".chip"])
    assert any("min-width: 0" in b for b in bodies[".panel-header > div"])


def test_css_cascade_has_no_important_or_has_hacks_beyond_the_hidden_utility():
    text = "\n".join(path.read_text(encoding="utf-8") for path in STYLES.glob("*.css"))
    assert text.count("!important") == 1 and re.search(r"\.hidden\s*\{[^}]*!important", text)
    assert ":has(" not in text


def test_navigation_collapses_for_tablets_and_the_phone_menu_is_compact():
    css = (STYLES / "responsive.css").read_text(encoding="utf-8")
    tablet = css.split("@media (max-width:900px)")[1].split("@media (max-width:700px)")[0]
    assert ".shell" in tablet and "display: block" in tablet and "repeat(3,minmax(0,1fr))" in tablet
    phone = css.split("@media (max-width:700px)")[1]
    assert "min-height: 60px" in phone and "flex-direction: column" in phone


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


# --- Multi-turn must not touch the accepted layout: only web/app.js may change -----------------------------------------------
import hashlib

ACCEPTED_LAYOUT = {   # sha256 of the files as accepted in real Chrome (line endings normalised); update ONLY for a deliberate UI change
    "index.html": "9ed76d04c84d1996c14c4bfd9f35b67f6aecf91ff0e2695c48e77b8ef7cdc9dd",
    "style.css": "8e7c357b181a5279af47d2b1ff1c89197942458f34421dc211013ccf347ec24d",
    "styles/agent-support.css": "79ff70fd664dca6d810b2be2f4bebeecf146891a9e0ad963edfa095669f131b6",
    "styles/assistant.css": "b2ffe31fb2090cf540aa1d73cd592b3612f0c29555292dd4fb22540db67b43be",
    "styles/foundation.css": "fb8f50b0bea31a0385ddf77afccffc3c64b332ddf283e523042cca8123033d49",
    "styles/overview.css": "7a9d8e29884bcb8421fcd9376e7eb8bdc3c64508db19ad5dc39d1f443f41db0d",
    "styles/responsive-overrides.css": "c44cdea023331fd06a4cfb81d3fe7c1250a6da462306b8b99fcc22150d517534",
    "styles/responsive.css": "0417bb50cb5c20e9febe187196e56380943b485651013b2dd63f3429e9d7cc80",
    "styles/workflows.css": "f19851d914244bd1c32b675fd6eb44122951aa7a97c52c60d8834aff58727b6d",
    "favicon.svg": "ae65b7e65c805f62a14a11b2835163294dbd1280823496bd606f51a15093b2fb",
}


def test_html_and_css_are_exactly_the_accepted_ones():
    for name, expected in ACCEPTED_LAYOUT.items():
        data = (ROOT / "web" / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == expected, f"{name} changed: multi-turn is a JavaScript-only change"


def test_chat_sends_back_the_previous_turn_context_and_forgets_it_on_errors():
    js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert "let lastTurnContext = null" in js
    assert "{ question: q, turn_context: lastTurnContext }" in js
    assert "lastTurnContext = d.turn_context || null" in js
    assert js.count("lastTurnContext = null") >= 2          # initial value and reset in the error handler
    assert "needs_clarification:" in js                      # the new mode has a Vietnamese label


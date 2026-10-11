"""Embed mode of the built site (?embed=acid): embed.js ships on every page, hides the chrome through one class, talks to
itspricedin.lol and nobody else, and is CSP-clean for Pages. Run: python3 -m pytest tests  (or python3 tests/test_embed.py).
The build itself (scripts/build-site.py) is run once into _site/, which is git-ignored."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "scripts" / "site"
OUT = ROOT / "_site"
HOST = "https://itspricedin.lol"


def built(_done=[]):
    if not _done:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build-site.py")], cwd=ROOT, check=True, capture_output=True)
        _done.append(True)
    return OUT


def test_embed_script_is_csp_clean_and_talks_only_to_itspricedin():
    js = (SITE / "embed.js").read_text(encoding="utf-8")
    assert "HOST = 'https://itspricedin.lol'" in js
    assert "postMessage({ type: 'page', path: path(), title: document.title }, HOST)" in js, "the page announces itself to the host origin only, never '*'"
    assert "e.origin !== HOST || e.source !== window.parent" in js, "nav messages count only from the host, only from the parent window"
    assert "m.type !== 'nav'" in js and "m.action === 'refresh'" in js and "m.action !== 'go'" in js
    assert "u.pathname.indexOf(root) !== 0" in js, "a go stays inside this site"
    assert "location.replace(flagged(" in js and "history.pushState = function" in js and "addEventListener('hashchange', announce)" in js
    assert "a.target = '_blank'; a.rel = 'noopener'" in js, "off-site links (github.com among them) leave the frame for a new tab"
    assert "q.get(FLAG) !== VALUE) return" in js and "classList.add('embed')" in js
    for bad in ("127.0.0.1", "localhost", "'*'", "eval(", "new Function", "innerHTML", "document.write", "document.cookie", "localStorage", "sessionStorage", "fetch("):
        assert bad not in js, bad
    code = js.split("*/", 1)[1]   # after the header comment
    assert code.count("https://") == 1, "one origin in the code"


def test_embed_styles_hide_the_chrome_through_the_html_class():
    css = (SITE / "style.css").read_text(encoding="utf-8")
    assert "html.embed .topbar, html.embed .foot, html.embed .skip { display: none; }" in css
    block = css.split("html.embed {", 1)[1].split("}", 1)[0]
    assert "--bg:" in block and "--gc: var(--magenta)" in block, "the acid tweak"
    assert "html.embed body { padding-inline: 0;" in css and "html.embed .frame { max-width: none; border: 0; }" in css


def test_every_built_page_loads_embed_js_in_head_before_the_first_paint():
    out = built()
    assert (out / "embed.js").read_text(encoding="utf-8") == (SITE / "embed.js").read_text(encoding="utf-8")
    pages = sorted(out.rglob("*.html"))
    assert len(pages) >= 30
    for page in pages:
        html = page.read_text(encoding="utf-8")
        head = html.split("</head>", 1)[0]
        m = re.search(r'<script src="([^"]*)embed\.js"></script>', head)
        assert m, page
        prefix = m.group(1)
        assert ('<link rel="stylesheet" href="%sstyle.css">' % prefix) in head and head.index("style.css") < head.index("embed.js"), page
        assert 'data-root="%s"' % prefix in html.split(">", 2)[1] + ">", (page, "embed.js derives the site root from data-root")
        assert "<script>" not in html, (page, "nothing inline: the site stays CSP-clean")
        if page.name != "404.html":
            assert prefix in ("", "../../"), (page, prefix)   # the index has no prefix; embed.js treats '' as './'
    assert re.search(r'<script src="https://anthonyherman\.github\.io/ai-security-corpus/embed\.js">', (out / "404.html").read_text(encoding="utf-8")), "404 is served at any depth, so its script is absolute"


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))

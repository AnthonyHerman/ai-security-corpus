#!/usr/bin/env python3
"""Build the static site for GitHub Pages into _site/.

Reuses the corpus parser from stats.py so the site, the README and the vault
always count the same links. Also publishes the corpus as data: _site/intel.json
(every link with its category, section and the date it was added) and
_site/intel-meta.json (count, HEAD commit and its date).

Usage: python3 scripts/build-site.py [--data-only]
"""
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stats  # noqa: E402

ROOT = stats.ROOT
OUT = ROOT / "_site"
SITE_URL = "https://anthonyherman.github.io/ai-security-corpus"
REPO_URL = "https://github.com/AnthonyHerman/ai-security-corpus"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def unescape_md(s):
    """Drop markdown backslash escapes ('privileged\\.' -> 'privileged.') so titles read as text."""
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|<>~])", r"\1", s)


def cap_desc(lead, names, cap=155):
    """'lead: a, b, c and more' kept under cap characters; every name if they fit."""
    out = lead
    for i, n in enumerate(names):
        sep = ": " if i == 0 else ", "
        if len(out) + len(sep) + len(n) + len(" and more") > cap:
            return out + (" and more." if i else ".")
        out += sep + n
    return out + "."


def last_change(path):
    """Date of the last commit touching path, for sitemap lastmod."""
    return subprocess.run(["git", "log", "-1", "--format=%cs", "--", path],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()


def load_corpus():
    """Full corpus as plain dicts: groups -> categories -> sections -> links."""
    readme = stats.README.read_text()
    toc = stats.parse_toc(readme)
    groups, seen = [], set()
    for gname, items in toc:
        color, emoji = stats.GROUPS[gname]
        g = {"name": gname, "slug": slug(gname), "color": color, "emoji": emoji, "categories": []}
        for cat, path, desc in items:
            c = {"name": cat, "label": sentence(cat), "slug": slug(cat), "path": path, "desc": desc, "sections": []}
            cur, on_page = None, set()
            for line in (ROOT / path).read_text().split("\n"):
                if line.startswith("## "):
                    cur = {"name": line[3:].strip(), "label": sentence(line[3:].strip()), "slug": slug(line[3:]), "links": []}
                    c["sections"].append(cur)
                    continue
                m = stats.LINK.match(line)
                if m and cur is not None:
                    title, url = unescape_md(m.group(1).strip()), m.group(2)
                    # a URL listed twice on one page is a slip, not a cross-reference: keep the first row
                    if url in on_page:
                        continue
                    on_page.add(url)
                    domain = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower()
                    cur["links"].append({"t": title, "u": url, "d": domain})
                    seen.add(url)
            c["sections"] = [s for s in c["sections"] if s["links"]]
            c["links"] = sum(len(s["links"]) for s in c["sections"])
            g["categories"].append(c)
        g["links"] = sum(c["links"] for c in g["categories"])
        groups.append(g)
    cats = [c for g in groups for c in g["categories"]]
    return {
        "site": SITE_URL, "repo": REPO_URL,
        "total": len(seen), "categories": len(cats), "sections": sum(len(c["sections"]) for c in cats),
        "sources": dict(stats.sources(stats.scan(toc)[2])),
        "growth": stats.growth(), "recent": stats.recent(12),
        "updated": stats.updated() if hasattr(stats, "updated") else None,
        "groups": groups,
    }


# ---------------------------------------------------------------- intel feed
def first_added():
    """URL -> YYYY-MM-DD (author date) of the commit that first added a line carrying that URL to any
    category file, in whatever form it had then (a '- [title](url)' row, a table cell, a bare URL: the
    same notion as the growth chart). One git call over the whole history, so it costs the same for 5
    links or 50,000, and a link that moved between files or had its title fixed keeps its first date."""
    out = subprocess.run(["git", "log", "--reverse", "--format=%x00%as", "-p", "--no-renames", "--", "*.md",
                          ":(exclude)vault", ":(exclude).claude"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    dates, date = {}, ""
    for line in out.split("\n"):
        if line.startswith("\x00"):
            date = line[1:].strip()
        elif line.startswith("+") and not line.startswith("+++ "):
            for url in stats.URL.findall(line):
                dates.setdefault(url, date)
    return dates


def first_commit(path, _cache={}):
    """Date of the first commit touching path: the fallback for a line git has not seen added
    (an uncommitted edit, a link that only ever lived in a table)."""
    if path not in _cache:
        log = subprocess.run(["git", "log", "--reverse", "--format=%as", "--", path],
                             cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
        _cache[path] = next((d.strip() for d in log if d.strip()), "")
    return _cache[path]


def load_intel(toc):
    """Every link as a flat row for machine consumers, shaped like itspricedin's pull-intel.py output
    plus `added`: the TOC category name, the '## ' section it sits under ('' above the first heading),
    the title as written (160 chars max), and the first URL occurrence corpus-wide wins."""
    added = first_added()
    items, seen = [], set()
    for _, cats in toc:
        for cat, path, _ in cats:
            section = ""
            for line in (ROOT / path).read_text(encoding="utf-8").split("\n"):
                if line.startswith("## "):
                    section = line[3:].strip()
                    continue
                m = stats.LINK.match(line)
                if not m or m.group(2) in seen:
                    continue
                url = m.group(2)
                seen.add(url)
                items.append({"title": m.group(1).strip()[:160], "url": url, "category": cat,
                              "section": section, "added": added.get(url) or first_commit(path)})
    return items


def intel_meta(items):
    """{count, generated_at, commit} from HEAD, so two builds of the same commit are byte-identical."""
    head = subprocess.run(["git", "log", "-1", "--format=%H %cI"], cwd=ROOT,
                          capture_output=True, text=True).stdout.split()
    sha, when = (head + ["", ""])[:2]
    return {"count": len(items), "generated_at": when, "commit": sha}


DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_intel(items, meta):
    """Fail the build rather than publish a feed a consumer cannot trust: every row has the five
    string fields, a real http(s) URL, a date, no URL twice, and the meta matches the rows."""
    seen = set()
    for i, row in enumerate(items):
        if set(row) != {"title", "url", "category", "section", "added"} or not all(isinstance(v, str) for v in row.values()):
            raise ValueError("intel row %d has the wrong shape: %r" % (i, row))
        if not row["title"] or not row["category"]:
            raise ValueError("intel row %d has an empty title or category: %r" % (i, row))
        if not re.match(r"^https?://\S+$", row["url"]) or row["url"] in seen:
            raise ValueError("intel row %d has a bad or repeated url: %r" % (i, row["url"]))
        if not DATE.match(row["added"]):
            raise ValueError("intel row %d has a bad added date: %r" % (i, row["added"]))
        seen.add(row["url"])
    if set(meta) != {"count", "generated_at", "commit"} or meta["count"] != len(items):
        raise ValueError("intel meta does not describe the rows: %r" % meta)
    if not re.match(r"^[0-9a-f]{40}$", meta["commit"]) or not re.match(r"^\d{4}-\d{2}-\d{2}T", meta["generated_at"]):
        raise ValueError("intel meta needs a full commit sha and an ISO timestamp: %r" % meta)


def write_intel():
    toc = stats.parse_toc(stats.README.read_text(encoding="utf-8"))
    items = load_intel(toc)
    meta = intel_meta(items)
    check_intel(items, meta)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "intel.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "intel-meta.json").write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")
    return items, meta


# ---------------------------------------------------------------- render
SITE_DIR = Path(__file__).resolve().parent / "site"
ASSETS = ROOT / "assets"
FONTS = ("https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700"
         "&family=Barlow+Semi+Condensed:wght@400;500&display=swap")
THEME = "#0b0820"
SITE_NAME = "AI Security Corpus"

# block-letter font (5 rows) for the ANSI hero
GLYPHS = {
    "A": [".###.", "#...#", "#####", "#...#", "#...#"],
    "I": ["###", ".#.", ".#.", ".#.", "###"],
    "S": [".####", "#....", ".###.", "....#", "####."],
    "E": ["#####", "#....", "####.", "#....", "#####"],
    "C": [".####", "#....", "#....", "#....", ".####"],
    "U": ["#...#", "#...#", "#...#", "#...#", ".###."],
    "R": ["####.", "#...#", "####.", "#..#.", "#...#"],
    "T": ["#####", "..#..", "..#..", "..#..", "..#.."],
    "Y": ["#...#", ".#.#.", "..#..", "..#..", "..#.."],
    "O": [".###.", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "####.", "#....", "#...."],
    "4": ["#..#.", "#..#.", "#####", "...#.", "...#."],
    "0": [".###.", "#..##", "#.#.#", "##..#", ".###."],
    " ": ["..", "..", "..", "..", ".."],
}


def block_rows(word):
    rows = ["" for _ in range(5)]
    for i, ch in enumerate(word):
        g = GLYPHS[ch]
        for r in range(5):
            rows[r] += g[r] + ("." if i < len(word) - 1 else "")
    return rows


def ansi_logo(lines):
    """Rows of block characters with a ░ drop shadow. Returns (colored_html, plain_text)."""
    grids = []
    for word in lines:
        rows = block_rows(word)
        w = len(rows[0]) + 1
        grid = [[" "] * w for _ in range(6)]
        for r in range(5):
            for c, ch in enumerate(rows[r]):
                if ch == "#":
                    grid[r][c] = "█"
        for r in range(5):
            for c in range(w - 1):
                if grid[r][c] == "█" and grid[r + 1][c + 1] == " ":
                    grid[r + 1][c + 1] = "░"
        grids.append(grid)
    width = max(len(g[0]) for g in grids)
    colored, plain = [], []
    for gi, grid in enumerate(grids):
        for r, row in enumerate(grid):
            s = "".join(row).ljust(width)
            plain.append(s)
            out = "".join('<span class="sh">%s</span>' % p if p.startswith("░") else p
                          for p in re.split(r"(░+)", s) if p)
            colored.append('<span class="row r%d">%s</span>' % (min(r, 4), out))
        if gi < len(grids) - 1:
            plain.append("")
            colored.append('<span class="row"> </span>')
    return "\n".join(colored), "\n".join(plain)


def esc(s):
    return html.escape(str(s or ""), quote=True)


def fmt(n):
    return "{:,}".format(n)


def sentence(s):
    """Title Case -> Sentence case, keeping acronyms and inner capitals (MCP, OAuth, IDE, arXiv, GitHub)."""
    def low(part):
        core = part.strip("()[]")
        if re.search(r"[A-Z]", core[1:]) or (len(core) >= 2 and core.isupper()) or re.match(r"^[A-Z]\.", core):
            return part
        return part.lower()
    out = []
    for i, w in enumerate(s.split(" ")):
        parts = w.split("-")
        out.append("-".join(p if (i == 0 and j == 0) else low(p) for j, p in enumerate(parts)))
    return " ".join(out)


def block_bar(value, vmax, width=36):
    """A ░▒▓█ bar: full cells in group color, a fading tail, dim ░ for the rest."""
    frac = value / vmax * width
    full = int(frac)
    rem = frac - full
    tail = "▓" if rem > 0.66 else ("▒" if rem > 0.33 else "░" if rem > 0 else "")
    rest = "░" * max(0, width - full - (1 if tail else 0))
    return '<span class="fill">%s%s</span><span class="rest">%s</span>' % ("█" * full, tail, rest)


CHART_COLORS = {"#161b22": "#1a1442", "#21262d": "#2b2360", "#30363d": "#3a2f80",
                "#e6edf3": "#ece8ff", "#8b949e": "#a39cd4", "#c9d1d9": "#ece8ff", "#6e7681": "#8a83b8"}


def svg_inline(name, title):
    """Embed a repo chart SVG re-skinned for the site: no background rect, site palette and faces,
    group labels in sentence case."""
    return reskin_svg((ASSETS / name).read_text(encoding="utf-8"), title).replace(">Unique URLs over time<", ">URLs tracked over time<")


def svg_categories(d):
    """Links per category, drawn by stats.svg_categories from the site's own counts (the README chart
    dedupes URLs within a category, so its numbers can differ by a link or two), labels in sentence case."""
    cats = [{"group": g["name"], "name": sentence(c["name"]), "links": c["links"]}
            for g in d["groups"] for c in g["categories"]]
    return reskin_svg(stats.svg_categories(cats, True), "Links per category, grouped").replace("1 categories", "1 category")


def reskin_svg(s, title):
    s = re.sub(r'<rect width="\d+" height="\d+" rx="12" fill="#0b0e14"/>', "", s, count=1)
    for a, b in CHART_COLORS.items():
        s = s.replace(a, b)
    s = re.sub(r'font-family="[^"]*monospace"', 'font-family="JetBrains Mono, ui-monospace, monospace"', s)
    s = re.sub(r'font-family="-apple-system[^"]*"', 'font-family="Barlow Semi Condensed, system-ui, sans-serif"', s)
    s = re.sub(r'(font-weight="700" fill="#[0-9a-f]{6}">)([A-Z][A-Z ]+)(</text>)',
               lambda m: m.group(1) + m.group(2).capitalize() + m.group(3), s)
    s = s.replace("<svg ", '<svg role="img" aria-label="%s" ' % esc(title), 1)
    return s


def cat_dir(group, cat):
    """Site path for a category page, e.g. agents/mcp/ or general/general-reading/."""
    parts = cat["path"].split("/")
    return (parts[0] + "/" + parts[1] if len(parts) == 3 else group["slug"] + "/" + cat["slug"]) + "/"


def gvar(slug):
    return "--gc: var(--c-%s)" % slug


def head_html(d, title, desc, prefix, url, jsonld, noindex=False):
    og = d["site"] + "/assets/social-preview.png"
    # an error page carries no canonical or og:url and asks not to be indexed
    canon = ('<meta name="robots" content="noindex">' if noindex else
             '<link rel="canonical" href="%s">\n<meta property="og:url" content="%s">' % (esc(url), esc(url)))
    return """<!doctype html>
<html lang="en" data-root="%s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<meta name="description" content="%s">
%s
<meta name="theme-color" content="%s">
<meta name="color-scheme" content="dark">
<meta property="og:type" content="website">
<meta property="og:site_name" content="%s">
<meta property="og:title" content="%s">
<meta property="og:description" content="%s">
<meta property="og:image" content="%s">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="640">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="%s">
<meta name="twitter:description" content="%s">
<meta name="twitter:image" content="%s">
<link rel="icon" href="%sassets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="%sstyle.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preload" as="style" href="%s" onload="this.onload=null;this.rel='stylesheet'">
<noscript><link rel="stylesheet" href="%s"></noscript>
<script type="application/ld+json">%s</script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
""" % (prefix, esc(title), esc(desc), canon, THEME, SITE_NAME, esc(title), esc(desc), esc(og),
       esc(title), esc(desc), esc(og), prefix, prefix, esc(FONTS), esc(FONTS), json.dumps(jsonld, separators=(",", ":")))


def search_html(d, prefix, label=None):
    label = label or "search %s links" % fmt(d["total"])
    return """<div class="search">
  <form class="prompt" role="search" action="%s" method="get">
    <label class="ps1" for="q" aria-hidden="true">&gt;</label>
    <input id="q" name="q" type="search" placeholder="%s" autocomplete="off" spellcheck="false" aria-controls="results" aria-label="Search the corpus by title or domain" aria-describedby="q-hint">
    <span class="caret" aria-hidden="true"></span>
    <kbd class="key" aria-hidden="true">/</kbd>
  </form>
  <span id="q-hint" class="visually-hidden">Results appear below as you type. Tab or the arrow keys move through them, Enter opens one, Escape closes the list.</span>
  <div id="q-status" class="visually-hidden" role="status" aria-live="polite"></div>
  <div id="results" class="results" role="region" aria-label="Search results" hidden></div>
  <noscript><p class="nojs">Search needs JavaScript. Every link is on the category pages, so your browser's find works there.</p></noscript>
</div>""" % (prefix or "./", label)


def root_crumb(prefix):
    return '<a href="%s" aria-label="Home"><span class="full">~/ai-security-corpus</span><span class="short" aria-hidden="true">~</span></a>' % (prefix or "./")


def topbar(d, prefix, crumbs, search=False, node=None, find=False):
    """BBS status line. `node` is 'n/29' on category pages (a position cue); `find` adds a link that
    focuses the hero prompt on the index, whose only search field lives in the hero."""
    crumb_html = ' <span class="sep">/</span> '.join(crumbs)
    mid = ('\n  <div class="search-slot">%s</div>' % search_html(d, prefix, "search")) if search else ""
    node_html = ('  <span class="node">node %s</span>\n' % esc(node)) if node else ""
    find_html = ('\n    <a class="find" href="#q"><kbd aria-hidden="true">/</kbd> search</a>') if find else ""
    return """<header class="topbar sticky">
%s  <nav class="path" aria-label="Breadcrumb">%s</nav>%s
  <span class="right">
    <span class="count">%s links</span>%s
    <a class="star" href="%s">star<span class="full"> on GitHub</span></a>
  </span>
</header>
""" % (node_html, crumb_html, mid, fmt(d["total"]), find_html, esc(d["repo"]))


def sec_heading(title, count=None, tag="h2", hid=None):
    c = ' <span class="count">%s</span>' % esc(count) if count else ""
    i = ' id="%s"' % hid if hid else ""
    return '<%s class="sec-h"%s><span class="t"><span class="glyph" aria-hidden="true">╔═</span>%s%s</span><span class="rule" aria-hidden="true"></span></%s>' % (
        tag, i, esc(title), c, tag)


def footer(d, hotkeys=False):
    hk = ('\n  <span><button type="button" class="hk" aria-pressed="true">hotkeys on</button></span>' if hotkeys else "")
    return """<footer class="foot">
  <span class="blocks" aria-hidden="true">▓▒░</span>
  <span><a href="%s">Source on GitHub</a></span>
  <span>Added, not endorsed</span>
  <span><a href="%s/blob/main/LICENSE" rel="license">CC BY 4.0</a></span>
  <span>Updated %s</span>%s
  <span class="end"><a href="%s/issues">Something missing or wrong? Open an issue</a></span>
  <span class="blocks" aria-hidden="true">░▒▓</span>
</footer>
""" % (esc(d["repo"]), esc(d["repo"]), esc(d["updated"]), hk, esc(d["repo"]))


def domain_counts(d):
    counts = {}
    for g in d["groups"]:
        for c in g["categories"]:
            for sec in c["sections"]:
                for l in sec["links"]:
                    counts[l["d"]] = counts.get(l["d"], 0) + 1
    return counts


def top_domains(d, n=5):
    return sorted(domain_counts(d).items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def other_domains(d):
    """How many distinct hosts sit in the donut's 'everything else' slice."""
    named = ("github.com", "gist.github.com", "x.com", "twitter.com", "youtube.com", "youtu.be")
    return sum(1 for k in domain_counts(d) if k not in named and not k.endswith("arxiv.org"))


def kv(rows):
    return "<dl>" + "".join("<dt>%s</dt><dd>%s</dd>" % r for r in rows) + "</dl>"


def render_index(d):
    logo_html, logo_plain = ansi_logo(["AI SECURITY", "CORPUS"])
    src = d["sources"]
    sysop = """<aside class="sysop" aria-label="Status">
  <p class="sysop-h"><span aria-hidden="true">╔═ </span>sysop</p>
  %s
  <p class="sysop-h"><span aria-hidden="true">╠═ </span>top domains</p>
  %s
  <p class="sysop-h"><span aria-hidden="true">╚═ </span>keys</p>
  %s
</aside>""" % (kv([("updated", esc(d["updated"])), ("categories", d["categories"]), ("sections", d["sections"])]),
               kv([(esc(k), fmt(v)) for k, v in top_domains(d)]),
               kv([("<kbd>1</kbd> to <kbd>8</kbd>", "jump to group"), ("<kbd>/</kbd>", "search")]))
    vmax = max(g["links"] for g in d["groups"])
    desc = cap_desc("%s links on AI security in %d categories" % (fmt(d["total"]), d["categories"]),
                    ["prompt injection", "jailbreaks", "agent and MCP security", "guardrails", "red teaming",
                     "supply chain", "papers", "benchmarks", "incidents", "tools"])
    jsonld = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": d["site"] + "/",
              "description": desc,
              "potentialAction": {"@type": "SearchAction", "target": d["site"] + "/?q={search_term_string}",
                                  "query-input": "required name=search_term_string"}}
    out = [head_html(d, SITE_NAME, desc, "", d["site"] + "/", jsonld)]
    out.append('<div class="frame">')
    out.append(topbar(d, "", [root_crumb("")], find=True))
    out.append("""<main id="main">
<section class="hero" aria-labelledby="site-title">
  <h1 class="logo-wrap" id="site-title">
    <pre class="logo-ghost m" aria-hidden="true">%s</pre>
    <pre class="logo-ghost c" aria-hidden="true">%s</pre>
    <pre class="logo" role="img" aria-label="AI Security Corpus">%s</pre>
  </h1>
  <p class="tagline"><b>One person's reading list that got out of hand.</b><br>
  <span class="y">No gatekeeping.</span> <span class="c">Added, not endorsed.</span>
  <span class="m">%s links</span> across %d categories and %d sections, sorted by what they are about.</p>
  %s
  %s
</section>
""" % (esc(logo_plain), esc(logo_plain), logo_html, fmt(d["total"]), d["categories"], d["sections"], search_html(d, ""), sysop))

    out.append("""<ul class="stats" aria-label="Corpus size">
  <li class="a"><span class="n">%s</span><span class="l">links</span></li>
  <li><span class="n">%d</span><span class="l">categories</span></li>
  <li><span class="n">%d</span><span class="l">sections</span></li>
  <li class="b"><span class="n">%s</span><span class="l">GitHub repos</span></li>
  <li class="c"><span class="n">%s</span><span class="l">arXiv papers</span></li>
  <li><span class="n">%s</span><span class="l">posts on X</span></li>
</ul>
""" % (fmt(d["total"]), d["categories"], d["sections"], fmt(src.get("GitHub", 0)), fmt(src.get("arXiv", 0)),
       fmt(src.get("X / Twitter", 0))))

    out.append('<section class="sec" id="menu" aria-labelledby="menu-h">')
    out.append(sec_heading("Main menu", "keys 1 to 8 jump", hid="menu-h"))
    out.append('<ol class="menu">')
    for i, g in enumerate(d["groups"], 1):
        out.append('<li class="entry" id="%s" data-hotkey="%d" style="%s">' % (g["slug"], i, gvar(g["slug"])))
        out.append('<h3 class="entry-head"><span class="key" aria-hidden="true">%d</span><span class="name">%s</span>'
                   '<span class="links">%s links</span></h3>' % (i, esc(g["name"]), fmt(g["links"])))
        out.append('<div class="bar" role="img" aria-label="%s of %s links">%s</div>' % (
            fmt(g["links"]), fmt(d["total"]), block_bar(g["links"], vmax)))
        out.append('<ul class="cats">')
        for c in g["categories"]:
            out.append('<li><a href="%s" title="%s">%s <span class="n">%d</span></a></li>' % (
                cat_dir(g, c), esc(c["desc"]), esc(sentence(c["name"])), c["links"]))
        out.append("</ul></li>")
    out.append("</ol></section>")

    if d["recent"]:
        dates = sorted({r[0] for r in d["recent"]}, reverse=True)
        one_date = len(dates) == 1
        out.append('<section class="sec" id="recent" aria-labelledby="recent-h">')
        out.append(sec_heading("Recently added", "%d links%s" % (len(d["recent"]), ", " + dates[0] if one_date else ""), hid="recent-h"))
        out.append('<ul class="recent">')
        for date, title, url in d["recent"]:
            dom = re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*$", r"\1", url))
            out.append('<li><a href="%s">%s</a><span class="date">%s</span></li>' % (
                esc(url), esc(title), esc(dom if one_date else date)))
        out.append("</ul></section>")

    out.append('<section class="sec" id="charts" aria-labelledby="charts-h">')
    out.append(sec_heading("The corpus in numbers", hid="charts-h"))
    out.append('<div class="charts">')
    out.append('<figure><div class="scroll" tabindex="0" aria-label="URLs tracked over time chart, scrolls sideways on small screens">%s</div>'
               '<figcaption>URLs tracked over time, one point per commit that changed the count. Counts links that were later merged or removed, so it runs a little above the %s on the menu.</figcaption></figure>'
               % (svg_inline("growth-dark.svg", "URLs tracked over time"), fmt(d["total"])))
    out.append('<figure>%s<figcaption>Share of links by host; everything else is %s other domains.</figcaption></figure>'
               % (svg_inline("sources-dark.svg", "Links by source: GitHub, arXiv, X, YouTube and everything else"), fmt(other_domains(d))))
    out.append('<figure class="wide"><div class="scroll" aria-label="Links per category chart">%s</div>%s'
               '<figcaption>Links per category, grouped.</figcaption></figure>' % (svg_categories(d), bar_list(d)))
    out.append("</div></section>")

    out.append('<section class="sec about" id="about" aria-labelledby="about-h">')
    out.append(sec_heading("About", hid="about-h"))
    out.append("""<p>Every link lives in a markdown file in <a href="%s">the repository</a>, one file per category, one heading per section. This site is generated from those files on every push. Nothing here is a recommendation: a link is in the corpus because it was worth reading once, not because it is right.</p>
<p>To add something, edit the category file and open a pull request, or open an issue with the URL. Titles are kept as the source wrote them. Licensed <a href="%s/blob/main/LICENSE">CC BY 4.0</a>.</p>
</section>
</main>""" % (esc(d["repo"]), esc(d["repo"])))
    out.append(footer(d, hotkeys=True))
    out.append('</div>\n<script src="script.js" defer></script>\n</body>\n</html>\n')
    return "\n".join(out)


def bar_list(d):
    """The category chart as HTML bars for narrow screens (the SVG needs 900px to read):
    one group heading and one name / count / bar row per category, scaled to the largest."""
    vmax = max(c["links"] for g in d["groups"] for c in g["categories"])
    out = ['<div class="barlist">']
    for g in d["groups"]:
        out.append('<div class="bl-g" style="%s"><p class="bl-h">%s <span>%s links</span></p>' % (
            gvar(g["slug"]), esc(g["name"]), fmt(g["links"])))
        for c in g["categories"]:
            out.append('<a class="bl-row" href="%s"><span class="bl-n">%s</span><span class="bl-v">%s</span>'
                       '<span class="bl-b" aria-hidden="true"><span style="width:%.1f%%"></span></span></a>' % (
                           cat_dir(g, c), esc(sentence(c["name"])), fmt(c["links"]), 100 * c["links"] / vmax))
        out.append("</div>")
    out.append("</div>")
    return "".join(out)


def cat_side(d, cat, prefix, prev_c, next_c):
    """Mono readout at the right of the category hero (wide screens): top hosts and the neighbouring lists."""
    counts = {}
    for s in cat["sections"]:
        for l in s["links"]:
            counts[l["d"]] = counts.get(l["d"], 0) + 1
    hosts = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
    (pg, pc), (ng, nc) = prev_c, next_c
    return """<aside class="cat-side" aria-label="Category readout">
  <p class="sysop-h"><span aria-hidden="true">╔═ </span>top hosts</p>
  %s
  <p class="sysop-h"><span aria-hidden="true">╚═ </span>nearby</p>
  %s
</aside>""" % (kv([(esc(k), fmt(v)) for k, v in hosts]),
               kv([("prev", '<a href="%s%s">%s</a>' % (prefix, cat_dir(pg, pc), esc(sentence(pc["name"])))),
                   ("next", '<a href="%s%s">%s</a>' % (prefix, cat_dir(ng, nc), esc(sentence(nc["name"]))))]))


def render_category(d, group, cat, prev_c, next_c, node=None):
    path = cat_dir(group, cat)
    prefix = "../" * path.count("/")
    url = d["site"] + "/" + path
    name = sentence(cat["name"])
    # section names the category blurb already uses ('Gateways, scanners ...' / 'Gateways') would read twice
    secnames = [sentence(s["name"]) for s in cat["sections"]
                if not re.search(r"\b%s\b" % re.escape(s["name"].lower()), cat["desc"].lower())]
    desc = cap_desc("%s. %s links in %d section%s" % (
        cat["desc"].rstrip("."), fmt(cat["links"]), len(cat["sections"]), "" if len(cat["sections"]) == 1 else "s"), secnames)
    title = "%s · %s" % (cat["name"], SITE_NAME)
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": cat["name"], "url": url,
              "description": cat["desc"], "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": d["site"] + "/"}}
    out = [head_html(d, title, desc, prefix, url, jsonld)]
    out.append('<div class="frame" style="%s">' % gvar(group["slug"]))
    out.append(topbar(d, prefix, [
        root_crumb(prefix),
        '<a class="grp" href="%s#%s">%s</a>' % (prefix, group["slug"], esc(group["name"].lower())),
        '<span aria-current="page">%s</span>' % esc(path.rstrip("/").split("/")[1]),
    ], search=True, node=node))
    edit = "%s/blob/main/%s" % (d["repo"], cat["path"])
    out.append("""<main id="main">
<section class="cat-hero">
  <p class="group"><span aria-hidden="true">╔═ </span><a href="%s#%s">%s</a></p>
  <h1>%s</h1>
  <p class="desc">%s</p>
  <div class="meta"><span><b>%s</b> links</span><span><b>%d</b> section%s</span><span>added, not endorsed</span><span><a href="%s">Edit this list on GitHub</a></span></div>
  %s
</section>
<div class="cat-body">
<nav class="rail" aria-label="Sections">
  <p class="rail-h">sections</p>
  <ol>""" % (prefix, group["slug"], esc(group["name"]), esc(name), esc(cat["desc"]), fmt(cat["links"]), len(cat["sections"]),
            "" if len(cat["sections"]) == 1 else "s", esc(edit), cat_side(d, cat, prefix, prev_c, next_c)))
    for s in cat["sections"]:
        out.append('<li><a href="#%s"><span class="t">%s</span><span class="n">%d</span></a></li>' % (
            s["slug"], esc(sentence(s["name"])), len(s["links"])))
    out.append("</ol></nav>\n<div class=\"cat-main\">")
    for s in cat["sections"]:
        out.append('<section class="sec section" id="%s" aria-labelledby="h-%s">' % (s["slug"], s["slug"]))
        out.append(sec_heading(sentence(s["name"]), "%d" % len(s["links"]), hid="h-" + s["slug"]))
        rows = ['<li><a href="%s">%s<i>%s</i></a></li>' % (esc(l["u"]), esc(l["t"]), esc(l.get("d", ""))) for l in s["links"]]
        out.append('<ul class="links">' + "".join(rows) + "</ul></section>")
    out.append("</div></div>")
    pn = ['<nav class="pn" aria-label="Neighbouring categories">']
    for label, item, cls in (("previous", prev_c, "prev"), ("next", next_c, "next")):
        g2, c2 = item
        pn.append('<a class="%s" rel="%s" href="%s%s">%s: %s<b>%s</b></a>' % (
            cls, cls, prefix, cat_dir(g2, c2), label, esc(g2["name"].lower()), esc(sentence(c2["name"]))))
    pn.append("</nav>\n</main>")
    out.append("\n".join(pn))
    out.append(footer(d))
    out.append('</div>\n<script src="%sscript.js" defer></script>\n</body>\n</html>\n' % prefix)
    return "\n".join(out)


def render_404(d):
    # GitHub Pages serves 404.html for any missing path at any depth, so its assets must be absolute
    # (SITE_URL). It therefore renders unstyled from a local file or another origin; change SITE_URL
    # in one place for a custom domain.
    prefix = d["site"] + "/"
    jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": "Not found", "isPartOf": d["site"] + "/"}
    out = [head_html(d, "Not found · " + SITE_NAME, "That page is not in the corpus.", prefix, None, jsonld, noindex=True)]
    out.append('<div class="frame">')
    out.append(topbar(d, prefix, [root_crumb(prefix), '<span aria-current="page">404</span>'], search=True))
    out.append("""<main id="main" class="lost">
  <h1>No such file</h1>
  <p>That path is not in the corpus. Category pages moved around as the list grew, so an old link may point somewhere that no longer exists.</p>
  <p><a href="%s">Back to the main menu</a>, or type <kbd>/</kbd> and search the %s links.</p>
</main>""" % (prefix, fmt(d["total"])))
    out.append(footer(d))
    out.append('</div>\n<script src="%sscript.js" defer></script>\n</body>\n</html>\n' % prefix)
    return "\n".join(out)


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#0b0820"/>
<rect x="4" y="6" width="4" height="4" fill="#e8ff3d"/><rect x="8" y="6" width="4" height="4" fill="#e8ff3d"/><rect x="12" y="6" width="4" height="4" fill="#e8ff3d"/>
<rect x="4" y="10" width="4" height="4" fill="#9bff6a"/><rect x="12" y="10" width="4" height="4" fill="#9bff6a"/>
<rect x="4" y="14" width="4" height="4" fill="#2ae8ff"/><rect x="8" y="14" width="4" height="4" fill="#2ae8ff"/><rect x="12" y="14" width="4" height="4" fill="#2ae8ff"/>
<rect x="4" y="18" width="4" height="4" fill="#9d8cff"/><rect x="12" y="18" width="4" height="4" fill="#9d8cff"/>
<rect x="4" y="22" width="4" height="4" fill="#ff2fb3"/><rect x="12" y="22" width="4" height="4" fill="#ff2fb3"/>
<rect x="20" y="6" width="4" height="4" fill="#e8ff3d"/><rect x="24" y="6" width="4" height="4" fill="#e8ff3d"/>
<rect x="20" y="10" width="4" height="4" fill="#9bff6a"/><rect x="20" y="14" width="4" height="4" fill="#2ae8ff"/>
<rect x="20" y="18" width="4" height="4" fill="#9d8cff"/><rect x="20" y="22" width="4" height="4" fill="#ff2fb3"/><rect x="24" y="22" width="4" height="4" fill="#ff2fb3"/>
</svg>
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_site(d):
    cats = [(g, c) for g in d["groups"] for c in g["categories"]]
    pages = []
    write(OUT / "index.html", render_index(d))
    pages.append(("", d["updated"]))
    for i, (g, c) in enumerate(cats):
        prev_c = cats[i - 1]
        next_c = cats[(i + 1) % len(cats)]
        path = cat_dir(g, c)
        write(OUT / path / "index.html", render_category(d, g, c, prev_c, next_c, "%d/%d" % (i + 1, len(cats))))
        pages.append((path, last_change(c["path"]) or d["updated"]))
    write(OUT / "404.html", render_404(d))
    write(OUT / "style.css", (SITE_DIR / "style.css").read_text(encoding="utf-8"))
    write(OUT / "script.js", (SITE_DIR / "script.js").read_text(encoding="utf-8"))
    (OUT / "assets").mkdir(exist_ok=True)
    for name in ("categories-dark.svg", "growth-dark.svg", "sources-dark.svg", "social-preview.png"):
        shutil.copyfile(ASSETS / name, OUT / "assets" / name)
    write(OUT / "assets" / "favicon.svg", FAVICON)
    write(OUT / ".nojekyll", "")
    write(OUT / "robots.txt", "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % d["site"])
    urls = "\n".join("  <url><loc>%s/%s</loc><lastmod>%s</lastmod></url>" % (d["site"], esc(p), mod) for p, mod in pages)
    write(OUT / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % urls)
    return len(pages) + 1


def main():
    corpus = load_corpus()
    if not corpus.get("updated"):
        paths = [c["path"] for g in corpus["groups"] for c in g["categories"]]
        corpus["updated"] = subprocess.run(["git", "log", "-1", "--format=%ad", "--date=short", "--", *paths],
                                           cwd=ROOT, capture_output=True, text=True).stdout.strip() or "unknown"
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "data" / "corpus.json").write_text(json.dumps(corpus, ensure_ascii=False, separators=(",", ":")))
    print(f"{corpus['total']:,} links · {corpus['categories']} categories · {corpus['sections']} sections -> {OUT/'data'/'corpus.json'}")
    meta = write_intel()[1]
    print(f"{meta['count']:,} intel rows @ {meta['commit'][:7]} -> {OUT/'intel.json'}, {OUT/'intel-meta.json'}")
    if "--data-only" in sys.argv:
        return
    n = render_site(corpus)
    print(f"{n} pages -> {OUT}")


if __name__ == "__main__":
    main()

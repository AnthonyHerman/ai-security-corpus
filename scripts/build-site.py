#!/usr/bin/env python3
"""Build the static site for Cloudflare (Workers static assets, see wrangler.jsonc) into _site/.

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
SITE_URL = "https://ai-security-corpus.online"
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
    """Every link as a flat row for machine consumers, with the date it was added: the TOC category name, the '## ' section it sits under ('' above the first heading),
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
SITE_NAME = "AI Security Corpus"
FONTS = ("newsreader.woff2", "newsreader-italic.woff2", "inter.woff2")  # self-hosted, see scripts/site/fonts
RECENT = 8


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


def cat_dir(group, cat):
    """Site path for a category page, e.g. agents/mcp/ or general/general-reading/."""
    parts = cat["path"].split("/")
    return (parts[0] + "/" + parts[1] if len(parts) == 3 else group["slug"] + "/" + cat["slug"]) + "/"


def short(name):
    """A category name without its trailing gloss: 'MCP (model context protocol)' -> 'MCP'."""
    return re.sub(r"\s*\([^)]*\)$", "", sentence(name))


def count(n):
    """The small figure after a name; 'links' is spoken, not shown."""
    return '<span class="n">%s<span class="visually-hidden"> links</span></span>' % fmt(n)


def host(url):
    return re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*$", r"\1", url)).lower()


def row(url, title, dom):
    return '<li><a href="%s">%s<i>%s</i></a></li>' % (esc(url), esc(title), esc(dom))


def head_html(d, title, desc, prefix, url, jsonld, noindex=False):
    og = d["site"] + "/assets/social-preview.png"
    # an error page carries no canonical or og:url and asks not to be indexed
    canon = ('<meta name="robots" content="noindex">' if noindex else
             '<link rel="canonical" href="%s">\n<meta property="og:url" content="%s">' % (esc(url), esc(url)))
    # the faces are preloaded so the first paint is already in them: no swap, no shifting headline
    fonts = "\n".join('<link rel="preload" as="font" type="font/woff2" href="%sfonts/%s" crossorigin>' % (prefix, f)
                      for f in FONTS)
    return """<!doctype html>
<html lang="en" data-root="%s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<meta name="description" content="%s">
%s
<meta name="theme-color" content="#f7f5f0" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141311" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
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
%s
<link rel="stylesheet" href="%sstyle.css">
<script type="application/ld+json">%s</script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
""" % (prefix, esc(title), esc(desc), canon, SITE_NAME, esc(title), esc(desc), esc(og),
       esc(title), esc(desc), esc(og), prefix, fonts, prefix, json.dumps(jsonld, separators=(",", ":")))


def search_html(prefix, placeholder="Search"):
    return """<div class="search">
  <form class="prompt" role="search" action="%s" method="get">
    <input id="q" name="q" type="search" placeholder="%s" autocomplete="off" spellcheck="false" aria-controls="results" aria-label="Search the corpus by title or domain" aria-describedby="q-hint">
    <kbd aria-hidden="true">/</kbd>
  </form>
  <span id="q-hint" class="visually-hidden">Results appear below as you type. Tab or the arrow keys move through them, Enter opens one, Escape closes the list.</span>
  <div id="q-status" class="visually-hidden" role="status" aria-live="polite"></div>
  <div id="results" class="results" role="region" aria-label="Search results" hidden></div>
  <noscript><p class="nojs">Search needs JavaScript.</p></noscript>
</div>""" % (prefix or "./", esc(placeholder))


def bar(d, prefix, home=True, here=None, search=False):
    """Top bar. The index shows only the GitHub link; category pages show the wordmark, the page name
    (faded in by script.js once the heading has scrolled away) and a compact search, and stick.
    Their GitHub link is the footer's 'Edit on GitHub'."""
    parts = []
    if home:
        parts.append('  <a class="home" href="%s">%s</a>' % (prefix or "./", SITE_NAME))
    if here:
        parts.append('  <span class="here" aria-hidden="true">%s</span>' % esc(here))
    if search:
        parts.append("  " + search_html(prefix))
    else:
        parts.append('  <a class="gh" href="%s">GitHub</a>' % esc(d["repo"]))
    return '<header class="bar%s">\n%s\n</header>\n' % (" sticky" if search else "", "\n".join(parts))


def footer(d, edit=None):
    e = '\n  <a href="%s">Edit on GitHub</a>' % esc(edit) if edit else ""
    return """<footer class="foot">
  <span>Added, not endorsed</span>
  <a href="%s/blob/main/LICENSE" rel="license">CC BY 4.0</a>%s
  <span class="end">Updated <time datetime="%s">%s</time></span>
</footer>
""" % (esc(d["repo"]), e, esc(d["updated"]), esc(d["updated"]))


def render_index(d):
    desc = cap_desc("%s links on AI security in %d categories" % (fmt(d["total"]), d["categories"]),
                    ["prompt injection", "jailbreaks", "agent and MCP security", "guardrails", "red teaming",
                     "supply chain", "papers", "benchmarks", "incidents", "tools"])
    jsonld = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": d["site"] + "/",
              "description": desc,
              "potentialAction": {"@type": "SearchAction", "target": d["site"] + "/?q={search_term_string}",
                                  "query-input": "required name=search_term_string"}}
    out = [head_html(d, SITE_NAME, desc, "", d["site"] + "/", jsonld)]
    out.append('<div class="frame">')
    out.append(bar(d, "", home=False))
    out.append("""<main id="main">
<section class="hero">
  <h1>AI Security <em>Corpus</em></h1>
  %s
</section>
<nav class="index" aria-label="Categories">""" % search_html("", "Search %s links" % fmt(d["total"])))
    for g in d["groups"]:
        out.append('<section class="grp" id="%s" aria-labelledby="g-%s">\n<h2 id="g-%s">%s</h2>\n<ul>' % (
            g["slug"], g["slug"], g["slug"], esc(g["name"])))
        for c in g["categories"]:
            out.append('<li><a href="%s" title="%s">%s%s</a></li>' % (
                cat_dir(g, c), esc(c["desc"]), esc(short(c["name"])), count(c["links"])))
        out.append("</ul>\n</section>")
    out.append("</nav>")
    if d["recent"]:
        out.append('<section class="recent" aria-labelledby="recent-h">\n<h2 id="recent-h">Recent</h2>\n<ul class="links">')
        out.extend(row(url, unescape_md(title), host(url)) for _, title, url in d["recent"][:RECENT])
        out.append("</ul>\n</section>")
    out.append("</main>")
    out.append(footer(d))
    out.append('</div>\n<script src="script.js" defer></script>\n</body>\n</html>\n')
    return "\n".join(out)


def render_category(d, group, cat, prev_c, next_c):
    path = cat_dir(group, cat)
    prefix = "../" * path.count("/")
    url = d["site"] + "/" + path
    # section names the category blurb already uses ('Gateways, scanners ...' / 'Gateways') would read twice
    secnames = [sentence(s["name"]) for s in cat["sections"]
                if not re.search(r"\b%s\b" % re.escape(s["name"].lower()), cat["desc"].lower())]
    desc = cap_desc("%s. %s links in %d section%s" % (
        cat["desc"].rstrip("."), fmt(cat["links"]), len(cat["sections"]), "" if len(cat["sections"]) == 1 else "s"), secnames)
    title = "%s · %s" % (cat["name"], SITE_NAME)
    jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": cat["name"], "url": url,
              "description": cat["desc"], "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": d["site"] + "/"}}
    out = [head_html(d, title, desc, prefix, url, jsonld)]
    out.append('<div class="frame">')
    out.append(bar(d, prefix, here=short(cat["name"]), search=True))
    out.append("""<main id="main">
<header class="cat-hero">
  <p class="group"><a href="%s#%s">%s</a></p>
  <h1>%s %s</h1>
  <p class="desc">%s</p>
</header>
<div class="cat-body">
<nav class="rail" aria-label="Sections">
<ol>""" % (prefix, group["slug"], esc(group["name"]), esc(short(cat["name"])), count(cat["links"]), esc(cat["desc"].rstrip("."))))
    for s in cat["sections"]:
        out.append('<li><a href="#%s"><span>%s</span>%s</a></li>' % (s["slug"], esc(sentence(s["name"])), count(len(s["links"]))))
    out.append('</ol>\n</nav>\n<div class="cat-main">')
    for s in cat["sections"]:
        out.append('<section class="section" id="%s" aria-labelledby="h-%s">\n<h2 id="h-%s">%s</h2>' % (
            s["slug"], s["slug"], s["slug"], esc(sentence(s["name"]))))
        out.append('<ul class="links">' + "".join(row(l["u"], l["t"], l.get("d", "")) for l in s["links"]) + "</ul>\n</section>")
    out.append("</div>\n</div>")
    (pg, pc), (ng, nc) = prev_c, next_c
    out.append("""<nav class="pn" aria-label="More categories">
  <a class="prev" rel="prev" href="%s%s"><svg width="18" height="10" viewBox="0 0 18 10" fill="none" stroke="currentColor" aria-hidden="true"><path d="M17.5 5H1M5 1 1 5l4 4"/></svg>%s</a>
  <a class="next" rel="next" href="%s%s">%s<svg width="18" height="10" viewBox="0 0 18 10" fill="none" stroke="currentColor" aria-hidden="true"><path d="M.5 5H17M13 1l4 4-4 4"/></svg></a>
</nav>
</main>""" % (prefix, cat_dir(pg, pc), esc(short(pc["name"])), prefix, cat_dir(ng, nc), esc(short(nc["name"]))))
    out.append(footer(d, "%s/blob/main/%s" % (d["repo"], cat["path"])))
    out.append('</div>\n<script src="%sscript.js" defer></script>\n</body>\n</html>\n' % prefix)
    return "\n".join(out)


def render_404(d):
    # Cloudflare serves 404.html (not_found_handling in wrangler.jsonc) for any missing path at any depth, so its assets must be absolute
    # (SITE_URL). It therefore renders unstyled from a local file or another origin; change SITE_URL
    # in one place for a custom domain.
    prefix = d["site"] + "/"
    jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": "Not found", "isPartOf": d["site"] + "/"}
    out = [head_html(d, "Not found · " + SITE_NAME, "That page is not in the corpus.", prefix, None, jsonld, noindex=True)]
    out.append('<div class="frame">')
    out.append(bar(d, prefix))
    out.append("""<main id="main" class="hero">
  <h1>Not <em>found</em></h1>
  %s
</main>""" % search_html(prefix, "Search %s links" % fmt(d["total"])))
    out.append(footer(d))
    out.append('</div>\n<script src="%sscript.js" defer></script>\n</body>\n</html>\n' % prefix)
    return "\n".join(out)


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#1a1814"/>
<rect x="7" y="9" width="14" height="2.4" rx="1.2" fill="#f7f5f0"/><rect x="7" y="15" width="18" height="2.4" rx="1.2" fill="#f7f5f0"/><rect x="7" y="21" width="11" height="2.4" rx="1.2" fill="#f7f5f0"/>
<circle cx="24.5" cy="9.2" r="3" fill="#ee8157"/>
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
        write(OUT / path / "index.html", render_category(d, g, c, prev_c, next_c))
        pages.append((path, last_change(c["path"]) or d["updated"]))
    write(OUT / "404.html", render_404(d))
    write(OUT / "style.css", (SITE_DIR / "style.css").read_text(encoding="utf-8"))
    write(OUT / "script.js", (SITE_DIR / "script.js").read_text(encoding="utf-8"))
    (OUT / "assets").mkdir(exist_ok=True)
    shutil.copyfile(ASSETS / "social-preview.png", OUT / "assets" / "social-preview.png")
    (OUT / "fonts").mkdir(exist_ok=True)
    for f in sorted((SITE_DIR / "fonts").iterdir()):
        shutil.copyfile(f, OUT / "fonts" / f.name)
    write(OUT / "assets" / "favicon.svg", FAVICON)
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

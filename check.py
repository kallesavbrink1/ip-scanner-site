#!/usr/bin/env python3
"""Checks the site: well-formed HTML, local links, hreflang reciprocity, sitemap coverage.
Usage: python3 check.py            (files in this folder)
       python3 check.py --live     (also fetches every page from GitHub Pages and expects 200)"""
import re, sys, os, glob, urllib.request
from html.parser import HTMLParser
from xml.dom import minidom

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = "https://kallesavbrink1.github.io/ip-scanner-site/"
LANGS = ["en", "es", "pt-BR", "de", "fr", "ja", "zh-Hans", "ko", "sv"]
problems = []


def fail(msg):
    problems.append(msg)
    print("FAIL", msg)


class Page(HTMLParser):
    VOID = {"meta", "link", "img", "br", "input", "hr"}

    def __init__(self):
        super().__init__()
        self.links, self.alts, self.stack, self.canonical, self.lang, self.title = [], {}, [], None, None, ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        for k in ("href", "src"):
            if k in a and tag != "link":
                self.links.append(a[k])
        if tag == "link":
            if a.get("rel") == "stylesheet":
                self.links.append(a["href"])
            if a.get("rel") == "canonical":
                self.canonical = a["href"]
            if a.get("rel") == "alternate" and "hreflang" in a:
                self.alts[a["hreflang"]] = a["href"]
        if tag == "title":
            self._in_title = True
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            fail(f"{self.file}: unexpected </{tag}> (open: {self.stack[-3:]})")
        else:
            self.stack.pop()

    def handle_data(self, data):
        if self._in_title:
            self.title += data


pages = {}
for path in sorted(glob.glob(os.path.join(ROOT, "**/*.html"), recursive=True)):
    rel = os.path.relpath(path, ROOT)
    p = Page()
    p.file = rel
    p.feed(open(path, encoding="utf-8").read())
    if p.stack:
        fail(f"{rel}: unclosed tags {p.stack}")
    if not p.title.strip():
        fail(f"{rel}: empty <title>")
    for link in p.links:
        if link.startswith(("http", "#", "mailto:")):
            continue
        target = os.path.normpath(os.path.join(os.path.dirname(path), link.split("#")[0]))
        if not os.path.exists(target):
            fail(f"{rel}: broken link {link}")
    pages[rel] = p

if len(pages) != 27:
    fail(f"expected 27 pages, found {len(pages)}")

# hreflang: every page lists all 9 languages plus x-default, and the targets point back.
url_of = lambda rel: BASE + re.sub(r"index\.html$", "", rel)
by_url = {url_of(r): p for r, p in pages.items()}
for rel, p in pages.items():
    if p.canonical != url_of(rel):
        fail(f"{rel}: canonical {p.canonical} should be {url_of(rel)}")
    if set(p.alts) != set(LANGS + ["x-default"]):
        fail(f"{rel}: hreflang set is {sorted(p.alts)}")
    for lang, href in p.alts.items():
        other = by_url.get(href)
        if other is None:
            fail(f"{rel}: hreflang {lang} points to unknown page {href}")
        elif other.alts != p.alts:
            fail(f"{rel}: hreflang set differs from {href}")
    if p.alts.get(p.lang) != p.canonical:
        fail(f"{rel}: lang={p.lang} does not match its own hreflang entry")

# sitemap lists exactly these URLs.
sm = minidom.parse(os.path.join(ROOT, "sitemap.xml"))
locs = {n.firstChild.data for n in sm.getElementsByTagName("loc")}
if locs != set(by_url):
    fail(f"sitemap differs: missing {sorted(set(by_url) - locs)}, extra {sorted(locs - set(by_url))}")

if "--live" in sys.argv:
    for u in sorted(by_url):
        try:
            code = urllib.request.urlopen(u, timeout=15).status
        except Exception as ex:
            code = ex
        if code != 200:
            fail(f"live {u}: {code}")

print(f"{len(pages)} pages checked, {len(problems)} problem(s)")
sys.exit(1 if problems else 0)

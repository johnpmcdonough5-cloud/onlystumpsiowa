#!/usr/bin/env python3
"""Publish the next queued blog post into this site.

Posts are written ahead of time and stored as JSON under blogbot/queue/<YYYY-MM>/.
Each day this picks one, renders it into the site's own chrome (cloned from an
existing post so the layout always matches), adds it to the blog index and
sitemap, and moves the queue file to blogbot/published/.

The month folder is a seasonality bucket, not a hard date: it prefers the
current month, and falls back to the oldest remaining month so nothing is
stranded and the site never goes quiet.

  python blogbot/publish.py              publish the next post
  python blogbot/publish.py --dry-run    show what would publish, write nothing
  python blogbot/publish.py --self-test  check template wiring with a canned post
  python blogbot/publish.py --status     how many posts are left, by month

No API key, no network, no dependencies beyond the standard library.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOT = ROOT / "blogbot"
CFG = json.loads((BOT / "config.json").read_text(encoding="utf-8"))
QUEUE = BOT / "queue"
DONE = BOT / "published"

CENTRAL = dt.timezone(dt.timedelta(hours=-5))  # Iowa; used for the date stamp only

REQUIRED = ("slug", "title", "meta_title", "meta_description",
            "category", "lede", "excerpt", "sections", "faqs")


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #

def month_dirs() -> list[pathlib.Path]:
    if not QUEUE.exists():
        return []
    return sorted(d for d in QUEUE.iterdir() if d.is_dir() and any(d.glob("*.json")))


def next_queued(today: dt.date) -> pathlib.Path | None:
    """Prefer this month's bucket; otherwise take the oldest one still waiting."""
    dirs = month_dirs()
    if not dirs:
        return None
    this_month = f"{today:%Y-%m}"
    preferred = [d for d in dirs if d.name == this_month]
    chosen = preferred[0] if preferred else dirs[0]
    return sorted(chosen.glob("*.json"))[0]


def validate(post: dict, where: pathlib.Path) -> None:
    missing = [k for k in REQUIRED if k not in post]
    if missing:
        raise SystemExit(f"{where.name}: missing field(s) {', '.join(missing)}")
    if not post["sections"] or not post["faqs"]:
        raise SystemExit(f"{where.name}: sections and faqs must not be empty")


def existing_slugs() -> set[str]:
    if CFG["layout"] == "dir":
        base = ROOT / CFG["blog_dir"]
        return {p.name for p in base.iterdir() if p.is_dir()} if base.exists() else set()
    return {p.stem for p in ROOT.glob("*.html")}


# --------------------------------------------------------------------------- #
# Rendering — clone the site's own chrome, swap the content
# --------------------------------------------------------------------------- #

def esc(s: str) -> str:
    return html.escape(s, quote=True)


def sub_once(pattern: str, repl: str, text: str, label: str) -> str:
    new, n = re.subn(pattern, lambda _: repl, text, count=1, flags=re.S)
    if n != 1:
        raise RuntimeError(f"Template anchor not found: {label}")
    return new


def build_body(post: dict) -> str:
    fmt = CFG["fmt"]
    out: list[str] = []
    if CFG.get("body_includes_header"):
        out.append(fmt["eyebrow"].format(text=esc(post["category"])))
        out.append(fmt["h1"].format(text=esc(post["title"])))
        out.append(fmt["meta"].format(text=CFG["_date_str"]))
    if fmt.get("img"):
        out.append(fmt["img"].format(text=esc(post["title"])))
    out.append(fmt["p"].format(text=esc(post["lede"])))
    for sec in post["sections"]:
        out.append(fmt["h2"].format(text=esc(sec["heading"])))
        for para in sec["paragraphs"]:
            out.append(fmt["p"].format(text=para if "<" in para else esc(para)))
    # Some templates carry a dedicated FAQ section; those get filled separately.
    if not CFG.get("faq_block_re"):
        out.append(fmt["h2"].format(text="Common questions"))
        for faq in post["faqs"]:
            out.append(fmt["h3"].format(text=esc(faq["q"])))
            out.append(fmt["p"].format(text=esc(faq["a"])))
    out.append(CFG["cta_html"])
    return "\n".join(out)


def render_faqs(src: str, post: dict) -> str:
    if not CFG.get("faq_block_re"):
        return src
    items = "\n".join(CFG["faq_item_fmt"].format(q=esc(f["q"]), a=esc(f["a"]))
                      for f in post["faqs"])
    src = sub_once(CFG["faq_block_re"], items, src, "faq block")
    if CFG.get("faq_schema"):
        schema = {
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": f["q"],
                            "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
                           for f in post["faqs"]],
        }
        src = sub_once(
            r'<script type="application/ld\+json">'
            r'(?:(?!</script>).)*?"FAQPage"(?:(?!</script>).)*?</script>',
            '<script type="application/ld+json">\n'
            + json.dumps(schema, indent=2) + '\n</script>',
            src, "faq schema")
    return src


def render(post: dict, url: str) -> str:
    src = (ROOT / CFG["reference_post"]).read_text(encoding="utf-8")

    # Capture the reference post's identity before rewriting. Replacing these two
    # strings globally catches every field keyed to the old post: schema url/@id,
    # BreadcrumbList name, twitter cards, related links.
    m = re.search(r'<link rel="canonical" href="([^"]*)"', src)
    ref_url = m.group(1) if m else None
    m = re.search(r'<nav class="breadcrumb".*?<span>(.*?)</span>', src, re.S)
    ref_crumb = m.group(1).strip() if m else None

    src = sub_once(r"<title>.*?</title>",
                   f"<title>{esc(post['meta_title'])}</title>", src, "title")
    src = sub_once(r'(<meta name="description" content=")[^"]*(")',
                   rf"\g<1>{esc(post['meta_description'])}\g<2>", src, "description")
    src = re.sub(r'(<link rel="canonical" href=")[^"]*(")', rf"\g<1>{url}\g<2>", src)
    src = re.sub(r'(<meta property="og:title" content=")[^"]*(")',
                 rf"\g<1>{esc(post['meta_title'])}\g<2>", src)
    src = re.sub(r'(<meta property="og:description" content=")[^"]*(")',
                 rf"\g<1>{esc(post['meta_description'])}\g<2>", src)
    src = re.sub(r'(<meta property="og:url" content=")[^"]*(")', rf"\g<1>{url}\g<2>", src)
    src = re.sub(r'(<meta property="article:published_time" content=")[^"]*(")',
                 rf"\g<1>{CFG['_iso']}\g<2>", src)
    src = re.sub(r'("date(?:Published|Modified)":\s*")[^"]*(")',
                 rf"\g<1>{CFG['_iso']}\g<2>", src)
    src = re.sub(r'(name="twitter:title" content=")[^"]*(")',
                 rf"\g<1>{esc(post['meta_title'])}\g<2>", src)
    src = re.sub(r'(name="twitter:description" content=")[^"]*(")',
                 rf"\g<1>{esc(post['meta_description'])}\g<2>", src)
    src = re.sub(r'("headline":\s*")[^"]*(")', rf"\g<1>{esc(post['title'])}\g<2>", src)
    if ref_url:
        src = src.replace(ref_url, url)
    if ref_crumb:
        src = src.replace(ref_crumb, esc(post["title"]))

    if not CFG.get("body_includes_header"):
        src = sub_once(r"<h1[^>]*>.*?</h1>", f"<h1>{esc(post['title'])}</h1>", src, "h1")
        if CFG.get("hero_lede_re"):
            src = sub_once(CFG["hero_lede_re"], f"<p>{esc(post['lede'])}</p>",
                           src, "hero lede")
        if CFG.get("hero_eyebrow_re"):
            src = sub_once(CFG["hero_eyebrow_re"],
                           CFG["fmt"]["eyebrow"].format(
                               text=f"{esc(post['category'])} &middot; {CFG['_date_str']}"),
                           src, "eyebrow")

    start, end = CFG["body_start"], CFG["body_end"]
    i = src.find(start)
    j = src.find(end, i + len(start)) if i >= 0 else -1
    if i < 0 or j < 0:
        raise RuntimeError("Body markers not found in reference post")
    src = src[: i + len(start)] + "\n" + build_body(post) + "\n" + src[j:]
    return render_faqs(src, post)


def add_card(post: dict, href: str) -> None:
    index_path = ROOT / CFG["index_file"]
    text = index_path.read_text(encoding="utf-8")
    card = CFG["card_html"].format(
        href=href, title=esc(post["title"]), excerpt=esc(post["excerpt"]),
        category=esc(post["category"]), date=CFG["_date_str"])
    m = re.search(CFG["card_anchor"], text)
    if not m:
        raise RuntimeError(f"Card anchor not found: {CFG['card_anchor']}")
    index_path.write_text(text[:m.end()] + "\n" + card + text[m.end():], encoding="utf-8")


def update_sitemap(url: str) -> None:
    path = ROOT / "sitemap.xml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if url in text:
        return
    default = "<url><loc>{url}</loc><lastmod>{iso}</lastmod><priority>0.6</priority></url>\n"
    entry = CFG.get("sitemap_entry", default).format(url=url, iso=CFG["_iso"])
    path.write_text(text.replace("</urlset>", entry + "</urlset>"), encoding="utf-8")


# --------------------------------------------------------------------------- #

STUB = {
    "slug": "selftest", "title": "Self-test: template wiring check",
    "meta_title": "Self-test | template check",
    "meta_description": "Self-test only. Nothing is written to disk.",
    "category": "Selftest", "lede": "Proves the generator renders into this layout.",
    "excerpt": "Self-test.",
    "sections": [{"heading": f"Section {i}", "paragraphs": [f"Body paragraph {i}."]}
                 for i in range(1, 5)],
    "faqs": [{"q": f"Question {i}?", "a": f"Answer {i}."} for i in range(1, 4)],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    today = dt.datetime.now(CENTRAL).date()
    CFG["_iso"] = today.isoformat()
    CFG["_date_str"] = f"{today:%B} {today.day}, {today.year}"
    name = CFG["site_name"]

    if args.status:
        total = 0
        for d in month_dirs():
            n = len(list(d.glob("*.json")))
            total += n
            print(f"  {d.name}: {n}")
        print(f"[{name}] {total} queued, {len(list(DONE.glob('*.json'))) if DONE.exists() else 0} published")
        return 0

    if args.self_test:
        post = dict(STUB)
        page = render(post, f"{CFG['domain']}/selftest/")
        for label, needle in [("title", post["meta_title"]), ("h1", post["title"]),
                              ("body", "Body paragraph 4."), ("faq", "Answer 3.")]:
            if needle not in page:
                print(f"FAIL [{name}] {label} not rendered")
                return 1
        card = re.search(CFG["card_anchor"],
                         (ROOT / CFG["index_file"]).read_text(encoding="utf-8"))
        queued = sum(len(list(d.glob('*.json'))) for d in month_dirs())
        print(f"PASS [{name}] render ok, {len(page)} bytes, "
              f"card anchor {'found' if card else 'MISSING'}, {queued} queued")
        return 0 if card else 1

    item = next_queued(today)
    if item is None:
        print(f"[{name}] Queue is empty — nothing published. Refill blogbot/queue/.")
        return 0

    post = json.loads(item.read_text(encoding="utf-8"))
    validate(post, item)

    slug = re.sub(r"[^a-z0-9-]", "", post["slug"].lower().replace(" ", "-"))
    if slug in existing_slugs():
        slug = f"{slug}-{today:%b%d}".lower()
    post["slug"] = slug

    if CFG["layout"] == "dir":
        rel = f"{CFG['blog_dir']}/{slug}/index.html"
        url = f"{CFG['domain']}/{CFG['blog_dir']}/{slug}/"
    else:
        rel = f"{slug}.html"
        url = f"{CFG['domain']}/{slug}.html"
    href = CFG["card_href_fmt"].format(slug=slug, blog_dir=CFG.get("blog_dir", ""))

    page = render(post, url)

    if args.dry_run:
        print(f"[{name}] would publish {item.relative_to(BOT)} -> {rel}\n"
              f"  {post['title']}\n  {post['meta_description']}")
        return 0

    out = ROOT / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    add_card(post, href)
    update_sitemap(url)

    DONE.mkdir(parents=True, exist_ok=True)
    item.rename(DONE / f"{CFG['_iso']}-{slug}.json")

    left = sum(len(list(d.glob("*.json"))) for d in month_dirs())
    print(f"[{name}] published {rel}\n  {post['title']}\n  {left} posts left in queue")
    if left <= 7:
        print(f"::warning::{name} blog queue is down to {left} posts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

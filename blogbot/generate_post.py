#!/usr/bin/env python3
"""Generate one SEO blog post for this site and splice it into the existing pages.

Reads blogbot/config.json, clones the chrome from a reference post so the new
page matches the site exactly, and updates the blog index + sitemap.

Run:  python blogbot/generate_post.py [--dry-run]
Needs: ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import pathlib
import re
import sys

import anthropic

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "blogbot" / "config.json").read_text(encoding="utf-8"))
SEASONAL = json.loads((ROOT / "blogbot" / "seasonal.json").read_text(encoding="utf-8"))

MODEL = "claude-opus-5"
CENTRAL = dt.timezone(dt.timedelta(hours=-5))  # Iowa is US Central; date only


# --------------------------------------------------------------------------- #
# Existing content
# --------------------------------------------------------------------------- #

def existing_posts() -> list[str]:
    """Titles of posts already published, so we never repeat a topic."""
    titles: list[str] = []
    index = ROOT / CFG["index_file"]
    if index.exists():
        titles = re.findall(r"<h[23][^>]*>(?:<a[^>]*>)?(.*?)(?:</a>)?</h[23]>",
                            index.read_text(encoding="utf-8"), re.S)
    return [html.unescape(re.sub(r"<[^>]+>", "", t)).strip() for t in titles]


def existing_slugs() -> set[str]:
    if CFG["layout"] == "dir":
        base = ROOT / CFG["blog_dir"]
        return {p.name for p in base.iterdir() if p.is_dir()} if base.exists() else set()
    return {p.stem for p in ROOT.glob("*.html")}


def pick_angle(today: dt.date) -> str:
    """Seasonal angle for this trade and month — real windows, not invented urgency."""
    angles = SEASONAL[CFG["seasonal_key"]]
    return angles[str(today.month)]


# --------------------------------------------------------------------------- #
# Claude
# --------------------------------------------------------------------------- #

def _text(resp) -> str:
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Model declined: {getattr(resp, 'stop_details', None)}")
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def research(client: anthropic.Anthropic, angle: str, today: dt.date) -> str:
    """Ground the post in what people are actually asking about right now."""
    prompt = (
        f"Today is {today:%B %d, %Y}. I write for {CFG['site_name']}, "
        f"a {CFG['trade']} company serving {CFG['service_area']}.\n\n"
        f"This month's angle: {angle}\n\n"
        "Search the web and report back, in plain notes:\n"
        "1. Current conditions in Iowa relevant to this trade right now — weather, "
        "recent storms, drought status, frost timing, whatever actually applies.\n"
        "2. Five questions Iowa homeowners are searching about this topic this month, "
        "phrased the way a homeowner would type them.\n"
        "3. Any real deadline or seasonal window that applies in the next 6 weeks.\n\n"
        "Facts only. If you cannot verify something, leave it out."
    )
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]

    for _ in range(4):
        resp = client.messages.create(
            model=MODEL, max_tokens=8000,
            output_config={"effort": "medium"},
            tools=tools, messages=messages,
        )
        if resp.stop_reason != "pause_turn":
            return _text(resp)
        messages = [messages[0], {"role": "assistant", "content": resp.content}]
    return _text(resp)


POST_SCHEMA = {
    "type": "object",
    "properties": {
        "slug": {"type": "string", "description": "kebab-case, 3-6 words, no year"},
        "title": {"type": "string", "description": "H1. A question or plain claim a homeowner would search."},
        "meta_title": {"type": "string", "description": "<title> tag, under 60 chars, ends with the brand"},
        "meta_description": {"type": "string", "description": "145-160 chars, plain, no hype"},
        "category": {"type": "string", "description": "One word or two, e.g. Pricing, Tips, Guides"},
        "lede": {"type": "string", "description": "One or two sentences under the H1."},
        "excerpt": {"type": "string", "description": "~110 chars for the blog index card"},
        "sections": {
            "type": "array",
            "minItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "paragraphs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heading", "paragraphs"],
                "additionalProperties": False,
            },
        },
        "faqs": {
            "type": "array",
            "minItems": 3,
            "items": {
                "type": "object",
                "properties": {"q": {"type": "string"}, "a": {"type": "string"}},
                "required": ["q", "a"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["slug", "title", "meta_title", "meta_description", "category",
                 "lede", "excerpt", "sections", "faqs"],
    "additionalProperties": False,
}

VOICE = """Write like the contractor wrote it, not an agency.

- Short declarative sentences. Grade 6-8 reading level.
- Concrete nouns and real numbers. Specificity is the proof of competence.
- Name the town. "Cedar Rapids" beats "the local area" for trust and for search.
- Lead with the homeowner's problem, not the company's credentials.
- Answer the search query directly in the first paragraph. That is what ranks.

Never write: "elevate", "unlock", "transform your outdoor living space",
"we're passionate about", "in today's world". No em-dash-heavy agency cadence.
No fake urgency — only real seasonal deadlines. No emoji.

Never invent specifics. Do not state license numbers, warranties, crew size,
years in business, awards, or customer counts unless they appear in the brand
facts below. Fabricated trust claims are the fastest way to burn a client."""


def write_post(client: anthropic.Anthropic, angle: str, notes: str,
               today: dt.date, avoid: list[str]) -> dict:
    facts = "\n".join(f"- {f}" for f in CFG["brand_facts"])
    prompt = (
        f"{VOICE}\n\n"
        f"## The business\n"
        f"{CFG['site_name']} — {CFG['trade']}, serving {CFG['service_area']}.\n"
        f"Towns to name naturally: {', '.join(CFG['towns'])}.\n"
        f"Phone: {CFG['phone']}\n\n"
        f"## Facts you may state (and nothing beyond these)\n{facts}\n\n"
        f"## Today\n{today:%B %d, %Y}. Seasonal angle: {angle}\n\n"
        f"## Current research\n{notes}\n\n"
        f"## Already published — pick a genuinely different topic\n"
        + ("\n".join(f"- {t}" for t in avoid) if avoid else "- (nothing yet)")
        + "\n\n## Your task\n"
        "Write one blog post that answers a question this month's customers are "
        "actually asking, and that could rank for it. Four to six sections, two to "
        "four paragraphs each. Then three to five FAQs — real questions, direct "
        "answers, no filler.\n\n"
        "Plain text in every field. No markdown, no HTML tags."
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=16000,
        output_config={"effort": "high",
                       "format": {"type": "json_schema", "schema": POST_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(_text(resp))


# --------------------------------------------------------------------------- #
# Rendering — clone the site's own chrome, swap the content
# --------------------------------------------------------------------------- #

def esc(s: str) -> str:
    return html.escape(s, quote=True)


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
            out.append(fmt["p"].format(text=esc(para)))
    # Some templates carry a dedicated FAQ section; those get filled separately.
    if not CFG.get("faq_block_re"):
        out.append(fmt["h2"].format(text="Common questions"))
        for faq in post["faqs"]:
            out.append(fmt["h3"].format(text=esc(faq["q"])))
            out.append(fmt["p"].format(text=esc(faq["a"])))
    out.append(CFG["cta_html"])
    return "\n".join(out)


def render_faqs(src: str, post: dict) -> str:
    """Fill a dedicated FAQ section and rebuild its FAQPage schema."""
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
        # tempered match so we stay inside the one script block
        src = sub_once(
            r'<script type="application/ld\+json">'
            r'(?:(?!</script>).)*?"FAQPage"(?:(?!</script>).)*?</script>',
            '<script type="application/ld+json">\n'
            + json.dumps(schema, indent=2) + '\n</script>',
            src, "faq schema")
    return src


def sub_once(pattern: str, repl: str, text: str, label: str) -> str:
    new, n = re.subn(pattern, lambda _: repl, text, count=1, flags=re.S)
    if n != 1:
        raise RuntimeError(f"Template anchor not found: {label}")
    return new


def render(post: dict, url: str) -> str:
    src = (ROOT / CFG["reference_post"]).read_text(encoding="utf-8")

    # Grab the reference post's own identity before we start rewriting. Replacing
    # these two strings globally catches every field keyed to the old post:
    # schema url/@id/item, BreadcrumbList name, twitter cards, related links.
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

    # Hero lives outside the article block on some templates.
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
        if CFG.get("breadcrumb_re"):
            src = re.sub(CFG["breadcrumb_re"], f"<span>{esc(post['title'])}</span>", src, count=1)

    start, end = CFG["body_start"], CFG["body_end"]
    i, j = src.find(start), src.find(end, src.find(start) + len(start))
    if i < 0 or j < 0:
        raise RuntimeError("Body markers not found in reference post")
    src = src[: i + len(start)] + "\n" + build_body(post) + "\n" + src[j:]
    return render_faqs(src, post)


def add_card(post: dict, href: str) -> None:
    index_path = ROOT / CFG["index_file"]
    text = index_path.read_text(encoding="utf-8")
    card = CFG["card_html"].format(
        href=href, title=esc(post["title"]), excerpt=esc(post["excerpt"]),
        category=esc(post["category"]), date=CFG["_date_str"],
    )
    m = re.search(CFG["card_anchor"], text)
    if not m:
        raise RuntimeError(f"Card anchor not found: {CFG['card_anchor']}")
    i = m.end()
    index_path.write_text(text[:i] + "\n" + card + text[i:], encoding="utf-8")


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

STUB_POST = {
    "slug": "selftest-template-check",
    "title": "Self-test: template wiring check",
    "meta_title": "Self-test | template check",
    "meta_description": "Self-test page. If you are reading this on the live site, delete it.",
    "category": "Selftest",
    "lede": "This page exists only to prove the generator renders into this site's layout.",
    "excerpt": "Self-test page — safe to delete.",
    "sections": [{"heading": f"Section {i}", "paragraphs": [f"Body paragraph {i}."]}
                 for i in range(1, 5)],
    "faqs": [{"q": f"Question {i}?", "a": f"Answer {i}."} for i in range(1, 4)],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="generate the post but write nothing to disk")
    ap.add_argument("--self-test", action="store_true",
                    help="render a canned post to verify template wiring; no API call")
    args = ap.parse_args()

    today = dt.datetime.now(CENTRAL).date()
    CFG["_iso"] = today.isoformat()
    CFG["_date_str"] = f"{today:%B} {today.day}, {today.year}"

    if args.self_test:
        post = dict(STUB_POST)
        page = render(post, f"{CFG['domain']}/selftest/")
        for label, needle in [("title", post["meta_title"]),
                              ("h1", post["title"]),
                              ("body", "Body paragraph 4."),
                              ("faq", "Answer 3.")]:
            if needle not in page:
                print(f"FAIL [{CFG['site_name']}] {label} not rendered")
                return 1
        if "Getting Your Iowa Lawn Ready" in page or "How Much Does a Retaining Wall" in page:
            print(f"FAIL [{CFG['site_name']}] reference post content leaked through")
            return 1
        card = re.search(CFG["card_anchor"],
                         (ROOT / CFG["index_file"]).read_text(encoding="utf-8"))
        print(f"PASS [{CFG['site_name']}] render ok, {len(page)} bytes, "
              f"card anchor {'found' if card else 'MISSING'}")
        return 0 if card else 1

    client = anthropic.Anthropic()
    angle = pick_angle(today)
    print(f"[{CFG['site_name']}] {today} — angle: {angle}", flush=True)

    notes = research(client, angle, today)
    post = write_post(client, angle, notes, today, existing_posts())

    slug = re.sub(r"[^a-z0-9-]", "", post["slug"].lower().replace(" ", "-"))
    taken = existing_slugs()
    if slug in taken:
        slug = f"{slug}-{today:%b%d}".lower()
    post["slug"] = slug

    if CFG["layout"] == "dir":
        rel = f"{CFG['blog_dir']}/{slug}/index.html"
        url = f"{CFG['domain']}/{CFG['blog_dir']}/{slug}/"
    else:
        rel = f"{slug}.html"
        url = f"{CFG['domain']}/{slug}.html"
    # href is relative to the blog index page, which differs per site
    href = CFG["card_href_fmt"].format(slug=slug, blog_dir=CFG.get("blog_dir", ""))

    page = render(post, url)

    if args.dry_run:
        print(f"--- would write {rel} ---\n{post['title']}\n{post['meta_description']}")
        return 0

    out = ROOT / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    add_card(post, href)
    update_sitemap(url)
    print(f"wrote {rel}\n  {post['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

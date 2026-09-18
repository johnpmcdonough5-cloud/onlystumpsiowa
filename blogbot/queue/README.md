# blogbot queue

`publish.py` takes the oldest post from `queue/<YYYY-MM>/` each morning, renders
it into `Blog/<slug>/index.html`, adds a card to `Blog/index.html`, updates
`sitemap.xml`, and moves the JSON file into `published/`.

**This directory was missing, so the scheduled workflow has run every day since
2026-08-14 and published nothing.** It exits cleanly with "Queue is empty", so
there is no failure notification — it just quietly does nothing.

## Refilling

Drop JSON files into a month directory. `publish.py` prefers the current month's
bucket and takes the alphabetically first file in it, so prefix the filename with
the intended date: `queue/2026-09/2026-09-22-my-slug.json`.

All nine top-level fields below are required — `validate()` exits if any is
missing, and `sections` and `faqs` must both be non-empty. Section objects use
`heading`, not `h2`.

```json
{
  "slug": "stump-grinding-cost-linn-county",
  "title": "What stump grinding costs in Linn County",
  "meta_title": "Stump Grinding Cost in Linn County | OnlyStumps",
  "meta_description": "What a stump costs to grind around Cedar Rapids and Marion, what moves the price, and the $200 minimum.",
  "category": "Costs",
  "lede": "Opening paragraph, rendered under the H1.",
  "excerpt": "One-sentence summary for the blog index card",
  "sections": [
    {"heading": "Section heading", "paragraphs": ["Body text.", "More body text."]}
  ],
  "faqs": [
    {"q": "A question someone actually asks", "a": "A direct answer."}
  ]
}
```

Keep `meta_title` to 60 characters or fewer and `meta_description` to 155.

Run `python blogbot/publish.py --status` to see what is queued, and
`--dry-run` to preview without writing.

## Before refilling — read this

The sister site (easterniowahydroseed.com) has 206 posts, roughly half of them
the same article with the town name swapped. That pattern is close to Google's
scaled-content-abuse policy and it is hard to undo once published.

Queue posts that answer a real question with real specifics. Two good posts a
month beats daily filler. If the queue is empty, the right response is often to
leave it empty rather than to generate volume.

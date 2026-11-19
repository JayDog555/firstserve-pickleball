# First Serve Pickleball

A small static directory of beginner-friendly pickleball open play and first-gear advice, starting in Southern California. Owned by Jay Oku.

The public site name is set in one place: `src/config.json` (`site_name`). Change it there and rebuild.

## Quick start

```bash
python3 build.py
python3 -m http.server 8080 --directory dist
```

Then open http://127.0.0.1:8080/

There are no runtime dependencies. The builder is a single Python 3 script.

## What gets built

Source lives in `src/`. The build writes HTML, CSS, `sitemap.xml`, and `robots.txt` into `dist/`.

| Source | Output |
| --- | --- |
| `src/pages/home.md` | `dist/index.html` |
| `src/pages/about.md` | `dist/about/index.html` |
| `src/pages/find-open-play.md` | `dist/guides/find-open-play/index.html` |
| `src/pages/first-paddle.md` | `dist/guides/first-paddle/index.html` |
| `src/cities/*.json` | `dist/cities/<slug>/index.html` plus a cities index |
| `src/partials/aikai.html` | inserted wherever `{{FEATURE:aikai}}` appears, if `features.aikai` is true |
| `src/static/styles.css` | `dist/styles.css` |

## How to add a city page

1. Copy `src/cities/_template.json` to `src/cities/<slug>.json`. Use a lowercase slug such as `irvine-ca` or `orange-county-ca`.
2. Fill in `slug`, `name`, `region`, and a short `intro`.
3. Add a venue **only after you verify it on an official city or county parks page, or the venue's own website**. Record the source URL and the date you checked (`YYYY-MM-DD`).
4. Leave a field blank, or say that it was not published, rather than guessing hours, fees, or court counts.
5. Do not copy listings from Pickleheads, CourtSource, Google Maps, or Facebook. OpenStreetMap data is allowed only with ODbL attribution.
6. Keep `"show_aikai_feature": true` unless this city page should omit the AIKAI feature. Most new pages should include it.
7. Run `python3 build.py`. The home page, cities index, and sitemap will pick up the new page.

If you have no verified venues yet, leave `"venues": []`. The city page will still build and will say that listings are being verified.

### Venue fields

- `name`, `address`
- `open_play_times`
- `beginner_friendly_notes`
- `fees`
- `source_url` (required for any published venue)
- `source_label` (optional, a short name for the official page)
- `last_checked` (date you read the official page)
- `court_info` (optional)
- `lights` (`true`, `false`, or `null` if the official page does not say)


## AIKAI feature block

Most new pages should include the reusable AIKAI feature. In Markdown, add this token on its own line, once per page:

```
{{FEATURE:aikai}}
```

The build replaces it with `src/partials/aikai.html`, which links to https://aikai.co and includes this disclosure:

> Disclosure: First Serve Pickleball is owned by the family behind AIKAI Pickleball.

Turn the block on or off for the whole site in `src/config.json`:

```json
"features": {
  "aikai": true
}
```

When `features.aikai` is `false`, the token is removed and city-page features are hidden. For city pages, also set `"show_aikai_feature": true` in the city JSON (the template defaults to true). The About page has a fuller FTC ownership disclosure instead of the product feature block.

## Affiliate links


Edit `src/links.json`. Each key matches a `{{AFFILIATE:key}}` token in the Markdown pages.

```json
{
  "selkirk": { "name": "Selkirk", "url": "" },
  "amazon": { "name": "Amazon", "url": "" }
}
```

Leave `url` empty until Jay approves the affiliate accounts. The build then prints the product name as plain text. When a URL is present, the build turns the token into a sponsored, nofollow link.

## Site name and other config

`src/config.json` holds the site name, owner, tagline, default description, and the `features.aikai` flag.

`base_url` (no trailing slash) is the public origin. Canonical tags, `sitemap.xml`, and `robots.txt` use it. `base_path` is the subpath when the site is not at the host root. The build prefixes internal root-relative links (nav, footer, in-page links, and the stylesheet) with it, and leaves external links alone. The published site uses:

```json
"base_url": "https://jaydog555.github.io/firstserve-pickleball",
"base_path": "/firstserve-pickleball"
```

For a custom domain served at the host root, set `base_url` to that origin and set `base_path` to `""`. Root-relative links then stay `/about/`, `/cities/`, and `/styles.css`.

## Editorial rules

- No tracking scripts.
- Every published venue needs an official source and a last-checked date.
- The About page includes FTC disclosures for AIKAI ownership and for affiliate links.
- Most new pages should include `{{FEATURE:aikai}}` (one block per page).
- Avoid em dashes in public copy.

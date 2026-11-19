#!/usr/bin/env python3
"""Build the First Serve Pickleball static site from src/ into dist/."""

from __future__ import annotations

import json
import posixpath
import re
import shutil
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"

TODAY = date.today().isoformat()

# Matches href/src attributes whose value is root-relative (starts with /).
_ROOT_ATTR_RE = re.compile(
    r"""(?P<attr>\b(?:href|src))=(?P<q>["'])(?P<url>/[^"']*)(?P=q)""",
    re.IGNORECASE,
)


def site_base_path(config: dict) -> str:
    """Subpath prefix with no trailing slash, or '' when served at the host root."""
    return (config.get("base_path") or "").strip().rstrip("/")


def prefix_root_relative(url: str, base_path: str) -> str:
    """Prefix an internal root-relative URL with base_path.

    External URLs, protocol-relative URLs, anchors, mailto/tel, and
    page-relative paths are unchanged. An empty base_path leaves
    root-relative URLs alone so a custom domain at the host root works.
    """
    if not url or not base_path:
        return url
    if not url.startswith("/") or url.startswith("//"):
        return url
    if url == base_path or url.startswith(base_path + "/"):
        return url
    return base_path + url


def prefix_root_relative_attrs(html: str, base_path: str) -> str:
    """Prefix internal root-relative href and src attributes."""
    if not base_path:
        return html

    def repl(match: re.Match) -> str:
        url = match.group("url")
        if url.startswith("//"):
            return match.group(0)
        prefixed = prefix_root_relative(url, base_path)
        if prefixed == url:
            return match.group(0)
        return f"{match.group('attr')}={match.group('q')}{prefixed}{match.group('q')}"

    return _ROOT_ATTR_RE.sub(repl, html)


def resolve_markdown_url(url: str, page_permalink: str, base_path: str) -> str:
    """Turn an internal Markdown link into a base_path-prefixed root path.

    Absolute http(s) links, protocol-relative URLs, and anchors are unchanged.
    """
    raw = url.strip()
    if not raw or raw.startswith(("#", "mailto:", "tel:")):
        return url
    if raw.startswith("//") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw):
        return url
    path, suffix = raw, ""
    split = re.match(r"^([^?#]*)([?#].*)$", raw)
    if split:
        path, suffix = split.group(1), split.group(2)
    if path.startswith("/"):
        resolved = path
    else:
        directory = page_permalink if page_permalink.endswith("/") else "/"
        if not directory.startswith("/"):
            directory = "/" + directory
        joined = posixpath.normpath(directory + path)
        if joined != "/" and (path.endswith("/") or path == "" or path.endswith(".")):
            if not joined.endswith("/"):
                joined += "/"
        if not joined.startswith("/"):
            joined = "/" + joined
        resolved = joined
    return prefix_root_relative(resolved, base_path) + suffix


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, parts[2].lstrip("\n")


def replace_affiliates(text: str, links: dict) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        info = links.get(key, {})
        name = info.get("name") or key
        url = (info.get("url") or "").strip()
        if url:
            return (
                f'<a href="{escape(url, quote=True)}" rel="sponsored nofollow">'
                f"{escape(name)}</a>"
            )
        return escape(name)

    return re.sub(r"\{\{AFFILIATE:([a-z0-9_-]+)\}\}", repl, text)


def inline_format(
    text: str, page_permalink: str = "/", base_path: str = ""
) -> str:
    placeholders: list[str] = []

    def stash(html: str) -> str:
        placeholders.append(html)
        return f"\x00PH{len(placeholders) - 1}\x00"

    def links(match: re.Match) -> str:
        label, url = match.group(1), match.group(2)
        url = resolve_markdown_url(url, page_permalink, base_path)
        return stash(
            f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'
        )

    # Affiliate tags were already turned into escaped names or HTML.
    # Protect any HTML already inserted by affiliate replacement.
    text = re.sub(r"<a\s[^>]+>.*?</a>", lambda m: stash(m.group(0)), text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", links, text)
    text = escape(text)
    text = re.sub(r"\x00PH(\d+)\x00", lambda m: f"\x00PH{m.group(1)}\x00", text)
    # escape() will have turned NULs? No, NUL isn't escaped. But the PH markers
    # got escaped if they were inside... they're not, they're raw. Wait: after
    # stash, we have \x00PHn\x00, then escape() leaves them, good.
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\x00PH(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)
    return text


def render_markdown(
    text: str, page_permalink: str = "/", base_path: str = ""
) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    i = 0
    n = len(lines)

    def fmt(value: str) -> str:
        return inline_format(value, page_permalink, base_path)

    def flush_paragraph(buf: list[str]) -> None:
        if buf:
            para = " ".join(s.strip() for s in buf)
            blocks.append(f"<p>{fmt(para)}</p>")
            buf.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped == "{{city_list}}" or re.match(r"^\{\{FEATURE:[a-z0-9_-]+\}\}$", stripped):
            blocks.append(stripped)
            i += 1
            continue
        if stripped == "---":
            blocks.append("<hr>")
            i += 1
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append(
                f"<h{level}>{fmt(heading.group(2))}</h{level}>"
            )
            i += 1
            continue
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i].strip() or ""):
                items.append(
                    "<li>" + fmt(re.sub(r"^[-*]\s+", "", lines[i].strip())) + "</li>"
                )
                i += 1
            blocks.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip() or ""):
                items.append(
                    "<li>" + fmt(re.sub(r"^\d+\.\s+", "", lines[i].strip())) + "</li>"
                )
                i += 1
            blocks.append("<ol>\n" + "\n".join(items) + "\n</ol>")
            continue
        para: list[str] = [stripped]
        i += 1
        while i < n and lines[i].strip() and not re.match(r"^(#{1,3}\s+|[-*]\s+|\d+\.\s+|---$|\{\{city_list\}\}|\{\{FEATURE:[a-z0-9_-]+\}\})", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        flush_paragraph(para)

    return "\n".join(blocks)


def css_href_for(base_path: str = "") -> str:
    return prefix_root_relative("/styles.css", base_path)


def href_for(to_permalink: str, base_path: str = "") -> str:
    # Root-relative, then prefixed, so nav and footer work on a subpath
    # and stay root-relative when base_path is empty (custom domain).
    path = to_permalink if to_permalink.startswith("/") else f"/{to_permalink}"
    return prefix_root_relative(path, base_path)


def city_list_html(cities: list[dict], base_path: str = "") -> str:
    if not cities:
        return "<p>No city pages have been added yet.</p>"
    items = []
    for city in cities:
        slug = city["slug"]
        href = href_for(f"/cities/{slug}/", base_path)
        count = len([v for v in city.get("venues", []) if v.get("name")])
        if count:
            summary = f"{count} verified venue{'s' if count != 1 else ''}"
        else:
            summary = "No verified venues yet"
        items.append(
            "<li class='city-card'>"
            f"<a href='{escape(href, quote=True)}'>{escape(city['name'])}</a>"
            f"<p>{escape(city.get('region') or '')}. {escape(summary)}</p>"
            "</li>"
        )
    return "<ul class='city-list'>\n" + "\n".join(items) + "\n</ul>"


def lights_label(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No lighting listed"
    return "Not stated on the official pages we checked"



def city_national_nav(config: dict) -> str:
    base_path = site_base_path(config)
    links = [
        (href_for("/cities/", base_path), "All US cities"),
        (href_for("/guides/find-open-play/", base_path), "How to find open play"),
        (href_for("/guides/first-paddle/", base_path), "First paddle guide"),
    ]
    items = "".join(
        f'<a href="{escape(href, quote=True)}">{escape(label)}</a>'
        for href, label in links
    )
    return f'<nav class="city-back" aria-label="National pages">{items}</nav>'


def load_rollout() -> dict:
    path = SRC / "rollout.json"
    if not path.exists():
        return {"regions": []}
    return load_json(path)


def render_cities_hub(cities: list[dict], rollout: dict, base_path: str) -> str:
    live_by_slug = {city["slug"]: city for city in cities}
    parts = [
        "<article class='prose'>",
        "<h1>Cities across the United States</h1>",
        "<p class='lede'>Beginner pickleball open play near you, anywhere in the US.</p>",
        "<p>We add a city page only after venues are verified on official parks or venue "
        "websites. Orange County, CA is our first live city. Other cities on the rollout "
        "list are marked coming soon and are not linked until a page exists.</p>",
        "</article>",
    ]
    for region in rollout.get("regions") or []:
        parts.append(
            f"<section class='rollout-region'><h2>{escape(region.get('name') or '')}</h2>"
        )
        for group in region.get("groups") or []:
            parts.append(f"<h3>{escape(group.get('state') or '')}</h3>")
            parts.append("<ul class='rollout-list'>")
            for item in group.get("cities") or []:
                slug = item.get("slug")
                name = item.get("name") or slug or ""
                if slug and slug in live_by_slug:
                    href = href_for(f"/cities/{slug}/", base_path)
                    city = live_by_slug[slug]
                    count = len([v for v in city.get("venues", []) if v.get("name")])
                    if count:
                        summary = f"{count} verified venue{'s' if count != 1 else ''}"
                    else:
                        summary = "Live"
                    parts.append(
                        "<li class='city-card'>"
                        f"<a href='{escape(href, quote=True)}'>{escape(name)}</a>"
                        f"<p>{escape(summary)}</p>"
                        "</li>"
                    )
                else:
                    parts.append(
                        "<li class='coming-soon'>"
                        f"<span class='coming-soon-name'>{escape(name)}</span>"
                        "<span class='coming-soon-status'>Coming soon</span>"
                        "</li>"
                    )
            parts.append("</ul>")
        parts.append("</section>")
    return "\n".join(parts)


def render_city_page(city: dict, config: dict) -> str:
    venues = [v for v in city.get("venues", []) if v.get("name")]
    parts = [
        f"<article class='prose'>",
        f"<h1>{escape(city['name'])}</h1>",
    ]
    if city.get("region"):
        parts.append(f"<p class='lede'>{escape(city['region'])}</p>")
    if city.get("intro"):
        parts.append(f"<p>{escape(city['intro'])}</p>")
    parts.append("</article>")
    parts.append(city_national_nav(config))
    if city.get("show_aikai_feature"):
        block = render_feature_block("aikai", config)
        if block:
            parts.append(block)

    if not venues:
        parts.append(
            "<div class='empty-listings'><p>No venues have been verified "
            "for this area yet. We only add a court after checking an official "
            "city or county parks page, or the venue's own website. Check back "
            "soon, or see the README for how to add a verified listing.</p></div>"
        )
        return "\n".join(parts)

    parts.append("<div class='notice'><p>Always confirm hours, fees, and reserved-court rules on the official source link. Last checked dates are on each card.</p></div>")
    for venue in venues:
        rows = []

        def row(term: str, value: str) -> None:
            if value:
                rows.append(f"<dt>{escape(term)}</dt><dd>{escape(value)}</dd>")

        row("Address", venue.get("address", ""))
        row("Courts", venue.get("court_info", ""))
        if "lights" in venue:
            row("Lights", lights_label(venue.get("lights")))
        row("Open play", venue.get("open_play_times", ""))
        row("Fees", venue.get("fees", ""))
        row("Beginner notes", venue.get("beginner_friendly_notes", ""))
        source = venue.get("source_url", "")
        label = venue.get("source_label") or source
        checked = venue.get("last_checked", "")
        source_html = ""
        if source:
            source_html = (
                f'<a href="{escape(source, quote=True)}" rel="noopener noreferrer">'
                f"{escape(label)}</a>"
            )
            if checked:
                source_html += f" (last checked {escape(checked)})"
        block = [
            "<article class='venue'>",
            f"<h2>{escape(venue['name'])}</h2>",
        ]
        if venue.get("address"):
            block.append(f"<p class='address'>{escape(venue['address'])}</p>")
        block.append("<dl>")
        # address already in subtitle; skip repeating in dl if we used subtitle
        # rebuild rows without address
        rows = [r for r in rows if not r.startswith("<dt>Address</dt>")]
        if source_html:
            rows.append(f"<dt>Source</dt><dd>{source_html}</dd>")
        block.append("\n".join(rows))
        block.append("</dl></article>")
        parts.append("\n".join(block))
    return "\n".join(parts)



def feature_enabled(config: dict, name: str) -> bool:
    features = config.get("features") or {}
    return bool(features.get(name))


def render_feature_block(name: str, config: dict) -> str:
    if not feature_enabled(config, name):
        return ""
    path = SRC / "partials" / f"{name}.html"
    if not path.exists():
        raise FileNotFoundError(f"Missing feature partial: {path}")
    html = path.read_text(encoding="utf-8").strip()
    html = html.replace("{{site_name}}", escape(config["site_name"]))
    html = prefix_root_relative_attrs(html, site_base_path(config))
    return html


def replace_feature_tokens(html: str, config: dict) -> str:
    def repl(match: re.Match) -> str:
        return render_feature_block(match.group(1), config)

    html = re.sub(
        r"<p>\s*\{\{FEATURE:([a-z0-9_-]+)\}\}\s*</p>",
        repl,
        html,
    )
    html = re.sub(r"\{\{FEATURE:([a-z0-9_-]+)\}\}", repl, html)
    return html


def apply_template(template: str, context: dict) -> str:
    out = template
    for key, value in context.items():
        out = out.replace("{{" + key + "}}", str(value))
    leftover = re.findall(r"\{\{[a-z0-9_]+\}\}", out)
    if leftover:
        raise RuntimeError(f"Unreplaced template tokens: {leftover}")
    return out


def nav_current(permalink: str, target: str) -> str:
    if permalink.rstrip("/") == target.rstrip("/"):
        return ' aria-current="page"'
    if target == "/cities/" and permalink.startswith("/cities/"):
        return ' aria-current="page"'
    return ""


def write_page(
    template: str,
    config: dict,
    *,
    permalink: str,
    title: str,
    meta_description: str,
    body: str,
    cities: list[dict],
) -> Path:
    if permalink == "/":
        out_path = DIST / "index.html"
    else:
        out_path = DIST / permalink.strip("/") / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    site_name = config["site_name"]
    doc_title = f"{title} | {site_name}" if title != site_name else site_name
    base = (config.get("base_url") or "").rstrip("/")
    base_path = site_base_path(config)
    canonical_tag = ""
    if base:
        url = base + (permalink if permalink != "/" else "/")
        canonical_tag = f'<link rel="canonical" href="{escape(url, quote=True)}">'

    context = {
        "doc_title": escape(doc_title),
        "meta_description": escape(meta_description),
        "owner": escape(config["owner"]),
        "canonical_tag": canonical_tag,
        "css_href": css_href_for(base_path),
        "site_name": escape(site_name),
        "tagline": escape(config.get("tagline") or ""),
        "home_href": href_for("/", base_path),
        "cities_index_href": href_for("/cities/", base_path),
        "open_play_href": href_for("/guides/find-open-play/", base_path),
        "paddle_href": href_for("/guides/first-paddle/", base_path),
        "coaches_href": href_for("/coaches/", base_path),
        "about_href": href_for("/about/", base_path),
        "aria_home": nav_current(permalink, "/"),
        "aria_cities": nav_current(permalink, "/cities/"),
        "aria_open_play": nav_current(permalink, "/guides/find-open-play/"),
        "aria_paddle": nav_current(permalink, "/guides/first-paddle/"),
        "aria_coaches": nav_current(permalink, "/coaches/"),
        "aria_about": nav_current(permalink, "/about/"),
        "content": body,
        "year": str(date.today().year),
    }
    html = apply_template(template, context)
    html = prefix_root_relative_attrs(html, base_path)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def write_sitemap(config: dict, permalinks: list[str]) -> None:
    base = (config.get("base_url") or "").rstrip("/")
    origin = base if base else ""
    urls = []
    for permalink in permalinks:
        loc_path = permalink if permalink != "/" else "/"
        loc = f"{origin}{loc_path}" if origin else loc_path
        urls.append(
            "  <url>\n"
            f"    <loc>{escape(loc)}</loc>\n"
            f"    <lastmod>{TODAY}</lastmod>\n"
            "  </url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    (DIST / "sitemap.xml").write_text(xml, encoding="utf-8")


def write_robots(config: dict) -> None:
    base = (config.get("base_url") or "").rstrip("/")
    sitemap = f"{base}/sitemap.xml" if base else "/sitemap.xml"
    text = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {sitemap}\n"
    )
    (DIST / "robots.txt").write_text(text, encoding="utf-8")


def load_cities() -> list[dict]:
    cities = []
    for path in sorted((SRC / "cities").glob("*.json")):
        if path.name.startswith("_"):
            continue
        data = load_json(path)
        if not data.get("slug"):
            data["slug"] = path.stem
        cities.append(data)
    return cities


def main() -> None:
    config = load_json(SRC / "config.json")
    links = load_json(SRC / "links.json")
    template = (SRC / "templates" / "base.html").read_text(encoding="utf-8")
    cities = load_cities()
    base_path = site_base_path(config)

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    shutil.copy2(SRC / "static" / "styles.css", DIST / "styles.css")

    permalinks: list[str] = []

    for md_path in sorted((SRC / "pages").glob("*.md")):
        meta, body = parse_front_matter(md_path.read_text(encoding="utf-8"))
        permalink = meta.get("permalink") or "/"
        body = body.replace("{{site_name}}", config["site_name"])
        body = body.replace("{{owner}}", config["owner"])
        body = body.replace(
            "{{COACH_DISCOUNT}}",
            config.get("coach_discount") or "10% off for your students",
        )
        body = body.replace(
            "{{COACH_COMMISSION}}",
            config.get("coach_commission") or "a 20% commission on every sale",
        )
        body = body.replace(
            "{{REWARD_PADDLE}}",
            config.get("reward_paddle") or "a free AIKAI Carbon 11.0 paddle",
        )
        body = replace_affiliates(body, links)
        html_body = render_markdown(body, permalink, base_path)
        if "{{city_list}}" in html_body:
            html_body = html_body.replace(
                "{{city_list}}", city_list_html(cities, base_path)
            )
        html_body = replace_feature_tokens(html_body, config)
        # Widen home so the city grid and guide cards can use the full wrap.
        if md_path.stem == "home":
            wrapped = html_body
        else:
            wrapped = f"<article class='prose'>\n{html_body}\n</article>"
        write_page(
            template,
            config,
            permalink=permalink,
            title=meta.get("title") or config["site_name"],
            meta_description=meta.get("meta_description")
            or config.get("description")
            or "",
            body=wrapped,
            cities=cities,
        )
        permalinks.append(permalink)

    rollout = load_rollout()
    cities_index_body = render_cities_hub(cities, rollout, base_path)
    write_page(
        template,
        config,
        permalink="/cities/",
        title="Cities across the United States",
        meta_description="Find beginner pickleball open play near you, anywhere in the US. Orange County, CA is live, with more cities coming soon.",
        body=cities_index_body,
        cities=cities,
    )
    permalinks.append("/cities/")

    for city in cities:
        permalink = f"/cities/{city['slug']}/"
        body = render_city_page(city, config)
        write_page(
            template,
            config,
            permalink=permalink,
            title=f"{city['name']} pickleball open play",
            meta_description=(
                f"Beginner-friendly pickleball open play in {city['name']}, "
                "verified on official parks or venue websites."
            ),
            body=body,
            cities=cities,
        )
        permalinks.append(permalink)

    write_sitemap(config, permalinks)
    write_robots(config)

    built = sorted(p.relative_to(DIST).as_posix() for p in DIST.rglob("*") if p.is_file())
    print(f"Built {len(built)} files into {DIST}:")
    for item in built:
        print(f"  {item}")


if __name__ == "__main__":
    main()

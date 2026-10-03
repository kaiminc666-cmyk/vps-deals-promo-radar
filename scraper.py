# ::ILANG [TYPE:source][ROLE:scraper][BOUNDARY:official public sources only; no invented deal data]
"""Fetch strictly verified offers from official public provider pages."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / ".ilang" / "site.ilang"
OUT = ROOT / "data" / "offers.json"
UA = "vps-deals/1.0 (+https://github.com/)"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Redirect targets have not been approved by this crawl's robots check.
        return None


def read_config() -> dict[str, Any]:
    text = CONFIG.read_text(encoding="utf-8")
    state = re.search(r"::STATE\{@SITE,([^}]+)\}", text)
    if not state:
        raise ValueError("Missing @SITE state in .ilang/site.ilang")
    site = dict(part.split(":", 1) for part in state.group(1).split(",") if ":" in part)
    block = re.search(r"::MODULE\{PROVIDERS[^\n]*\}\s*\n(.*?)(?=\n::MODULE|\Z)", text, re.S)
    if not block:
        raise ValueError("Missing PROVIDERS module in .ilang/site.ilang")
    providers = []
    for line in block.group(1).splitlines():
        if not line.strip() or "|" not in line:
            continue
        fields = [x.strip() for x in line.split("|")]
        if len(fields) != 4:
            continue
        name, website, source, affiliate = fields
        if not source.startswith("https://") or not website.startswith("https://"):
            continue
        providers.append({"name": name, "website": website, "source": source, "affiliate": affiliate})
    return {"site": site, "providers": providers}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def allowed_by_robots(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        req = urllib.request.Request(robots_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as res:
            rp.parse(res.read(256_000).decode("utf-8", "replace").splitlines())
    except (urllib.error.URLError, TimeoutError, OSError):
        # An unavailable robots file is not treated as permission to crawl.
        return False
    return rp.can_fetch(UA, url)


def fetch(url: str) -> tuple[str, str] | None:
    if not allowed_by_robots(url):
        print(f"SKIP robots/disallowed: {url}")
        return None
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/ld+json;q=0.9,*/*;q=0.5"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=25) as res:
            final_url = res.geturl()
            content_type = res.headers.get_content_type()
            raw = res.read(3_000_000).decode("utf-8", "replace")
            return raw, content_type if final_url.startswith("https://") else ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"SKIP fetch failed: {url}: {exc}")
        return None


def walk_offers(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from walk_offers(item)
    elif isinstance(value, dict):
        kind = value.get("@type", [])
        kinds = kind if isinstance(kind, list) else [kind]
        if "Offer" in kinds or "AggregateOffer" in kinds:
            yield value
        for key, item in value.items():
            if key in {"offers", "@graph"} or isinstance(item, (dict, list)):
                yield from walk_offers(item)


def extract_offers(raw: str, content_type: str, provider: dict[str, str], fetched_at: str) -> list[dict[str, Any]]:
    if "html" not in content_type and "json" not in content_type:
        return []
    records: list[dict[str, Any]] = []
    for match in re.finditer(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", raw, re.I | re.S):
        try:
            obj = json.loads(match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for offer in walk_offers(obj):
            price = offer.get("price")
            currency = offer.get("priceCurrency")
            if isinstance(price, dict):
                currency = currency or price.get("priceCurrency")
                price = price.get("price")
            # Reject ranges, non-numeric values, negative values, and missing currency.
            if not currency or not isinstance(price, (int, float, str)) or isinstance(price, bool):
                continue
            price_text = str(price).strip()
            if not re.fullmatch(r"\d+(?:\.\d{1,4})?", price_text) or float(price_text) < 0:
                continue
            item = offer.get("itemOffered") or offer.get("name")
            title = item.get("name") if isinstance(item, dict) else item
            title = str(title or "").strip()
            if not title or len(title) > 140:
                continue
            valid_until = str(offer.get("priceValidUntil") or "").strip()
            if valid_until:
                try:
                    if datetime.fromisoformat(valid_until[:10]).date() < datetime.now(timezone.utc).date():
                        continue
                except ValueError:
                    continue
            target = str(offer.get("url") or provider["source"])
            if target.startswith("/"):
                target = urllib.parse.urljoin(provider["source"], target)
            if not target.startswith("https://") or urllib.parse.urlsplit(target).netloc != urllib.parse.urlsplit(provider["website"]).netloc:
                target = provider["source"]
            records.append({"provider": provider["name"], "title": title, "price": price_text,
                "currency": str(currency).upper(), "offer_url": target, "valid_until": valid_until,
                "source_url": provider["source"], "fetched_at": fetched_at,
                "affiliate_url": provider.get("affiliate") or ""})
    # Omit conflicting prices for the same plan instead of choosing one.
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    conflicts = set()
    for item in records:
        key = (item["provider"].casefold(), item["title"].casefold(), item["currency"])
        if key in unique and (unique[key]["price"], unique[key]["valid_until"]) != (item["price"], item["valid_until"]):
            conflicts.add(key)
        unique.setdefault(key, item)
    return [item for key, item in unique.items() if key not in conflicts]


def main() -> None:
    cfg = read_config()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    offers: list[dict[str, Any]] = []
    for provider in cfg["providers"]:
        response = fetch(provider["source"])
        if response:
            raw, content_type = response
            found = extract_offers(raw, content_type, provider, now)
            offers.extend(found)
            print(f"{provider['name']}: verified offers={len(found)}")
        time.sleep(1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": now, "offers": offers}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(offers)} verified offer(s) to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

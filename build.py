# ::ILANG [TYPE:source][ROLE:static-site-builder][CONFIG:.ilang/site.ilang is authoritative]
"""Build the deterministic static VPS deals site from I-Lang config and verified data."""
from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site"


def config():
    text = (ROOT / ".ilang" / "site.ilang").read_text(encoding="utf-8")
    m = re.search(r"::STATE\{@SITE,([^}]+)\}", text)
    if not m:
        raise ValueError("Missing @SITE in .ilang/site.ilang")
    site = dict(part.split(":", 1) for part in m.group(1).split(",") if ":" in part)
    providers = []
    block = re.search(r"::MODULE\{PROVIDERS[^\n]*\}\s*\n(.*?)(?=\n::MODULE|\Z)", text, re.S)
    if not block:
        raise ValueError("Missing PROVIDERS module")
    for line in block.group(1).splitlines():
        if "|" not in line:
            continue
        fields = [x.strip() for x in line.split("|")]
        if len(fields) == 4 and fields[0] and fields[1].startswith("https://") and fields[2].startswith("https://"):
            providers.append({"name": fields[0], "website": fields[1], "source": fields[2], "affiliate": fields[3]})
    return site, providers


def esc(v):
    return html.escape(str(v or ""), quote=True)


def load_offers():
    p = ROOT / "data" / "offers.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        offers = data.get("offers", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    today = datetime.now(timezone.utc).date().isoformat()
    return [o for o in offers if o.get("title") and o.get("source_url") and o.get("offer_url")
            and (not o.get("valid_until") or o["valid_until"] >= today)
            and o.get("price") is not None and o.get("currency")]


def page(site, title, description, content, canonical="", jsonld=None):
    brand = esc(site.get("brand", "VPS deals"))
    canonical_tag = f'<link rel="canonical" href="{esc(canonical)}">' if canonical else ""
    safe_json = json.dumps(jsonld, ensure_ascii=False).replace("<", "\\u003c")
    structured = f'<script type="application/ld+json">{safe_json}</script>' if jsonld else ""
    from string import Template
    return Template((ROOT / "templates/page.html").read_text(encoding="utf-8")).substitute(
        title=esc(title), description=esc(description), canonical_tag=canonical_tag,
        brand=brand, canonical=esc(canonical), structured=structured, content=content,
        og_image=esc(urljoin(site.get("base_url", "").rstrip("/") + "/", "assets/og.svg")))


def offer_card(o, slug):
    price = f'{esc(o["currency"])} {esc(o["price"])}'
    valid = f'<span>Valid until {esc(o["valid_until"])}</span>' if o.get("valid_until") else ""
    link = o.get("affiliate_url") or o["offer_url"]
    return f'''<article class="card"><div class="eyebrow">{esc(o["provider"])}</div><h3><a href="/deals/{esc(slug)}.html">{esc(o["title"])}</a></h3><p class="price">{price}</p><p class="muted">Source-listed price. Billing period, upfront payment and renewal terms must be checked with the provider.</p><div class="cardfoot"><a class="button" href="{esc(link)}" rel="nofollow sponsored noopener">View offer ↗</a><a class="source" href="{esc(o["source_url"])}">Source</a>{valid}</div></article>'''


def main():
    site, providers = config()
    brand = site.get("brand", "vps-deals")
    base = site.get("base_url", "").rstrip("/")
    configured = {(p["name"], p["source"]) for p in providers}
    offers = [o for o in load_offers() if (o.get("provider"), o.get("source_url")) in configured]
    if OUT.exists():
        if OUT.resolve() != ROOT.resolve() / "site" or OUT.is_symlink():
            raise ValueError("Unsafe output path")
        shutil.rmtree(OUT)
    last_fetch = max((o["fetched_at"] for o in offers), default="")
    by_provider = {p["name"]: [] for p in providers}
    for i, o in enumerate(offers):
        by_provider.setdefault(o["provider"], []).append(o)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(exist_ok=True)
    (OUT / "deals").mkdir(exist_ok=True)
    (OUT / "assets" / "style.css").write_text(STYLE, encoding="utf-8")
    (OUT / "assets" / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    (OUT / "assets" / "og.svg").write_text(OG, encoding="utf-8")
    cat_items = [{"@type": "ListItem", "position": i + 1, "url": f"{base}/providers/{slugify(p['name'])}.html" if base else f"/providers/{slugify(p['name'])}.html"} for i, p in enumerate(providers)]
    offer_items = [{"@type": "ListItem", "position": i + 1, "url": f"{base}/deals/{slugify(o['provider']+'-'+o['title'])}.html" if base else f"/deals/{slugify(o['provider']+'-'+o['title'])}.html"} for i, o in enumerate(offers)]
    cards = "".join(offer_card(o, slugify(o["provider"] + "-" + o["title"])) for o in offers)
    if not cards:
        cards = '<div class="empty"><span class="pulse"></span><div><strong>No source-listed prices yet</strong><p>Provider pages are listed below. A deal appears here only after an official source exposes a clear plan and current price.</p></div></div>'
    provider_cards = "".join(f'<a class="provider" href="/providers/{slugify(p["name"])}.html"><span>{esc(p["name"])}</span><small>{len(by_provider.get(p["name"], []))} source-listed prices</small><b>↗</b></a>' for p in providers)
    home_content = f'''<section class="hero"><div class="kicker">Independent VPS price watch</div><h1>Find a VPS plan.<br><em>See the source.</em></h1><p>Official-source VPS offers, checked on a schedule. We show only prices we can verify and link every listing to its source.</p><div class="stats"><div><b>{len(offers)}</b><span>source-listed prices</span></div><div><b>{len(providers)}</b><span>providers tracked</span></div><div><b>6h</b><span>check cadence</span></div></div></section>
<section class="section"><div class="sectionhead"><div><div class="kicker">Live list</div><h2>Source-listed VPS prices</h2></div><a class="textlink" href="/compare.html">Compare providers →</a></div><div class="grid">{cards}</div></section>
<section class="section"><div class="sectionhead"><div><div class="kicker">Official sources</div><h2>Providers we track</h2></div></div><div class="providergrid">{provider_cards}</div></section>
<section class="note"><span class="noteicon">i</span><p><strong>How we handle prices</strong><br>Setup, renewal, and crossed-out prices are easy to confuse. We extract named prices from official structured data. A listed price alone does not establish a discount or include all billing conditions; use the source link to check them.</p></section>'''
    write(OUT / "index.html", page(site, f"VPS Deals & Price Watch | {brand}", "Browse VPS hosting plans and current offers from official provider pages. Prices are shown only when verifiable.", home_content, base + "/" if base else "", {"@context":"https://schema.org","@type":"ItemList","itemListElement":offer_items}))

    provider_urls = []
    for p in providers:
        slug = slugify(p["name"])
        pu = f"{base}/providers/{slug}.html" if base else ""
        provider_urls.append((f"/providers/{slug}.html", max((o["fetched_at"] for o in by_provider.get(p["name"], [])), default="")))
        items = by_provider.get(p["name"], [])
        pcards = "".join(offer_card(o, slugify(o["provider"] + "-" + o["title"])) for o in items)
        if not pcards:
            pcards = '<div class="empty"><div><strong>No verified current price</strong><p>We have not confirmed a clear current offer on this official source. Check the provider directly for current plans.</p></div></div>'
        desc = f"Official VPS hosting source and source-listed prices from {p['name']}. No unsource-listed prices are shown."
        product = None
        if items:
            product = {"@context":"https://schema.org","@type":"Service","name":f"{p['name']} VPS hosting","url":p["website"],"offers":[{"@type":"Offer","name":o["title"],"price":o["price"],"priceCurrency":o["currency"],"url":o["offer_url"],**({"priceValidUntil":o["valid_until"]} if o.get("valid_until") else {})} for o in items]}
        content = f'<div class="crumb"><a href="/">Home</a> / Providers</div><section class="providerhero"><div class="kicker">Provider source</div><h1>{esc(p["name"])}</h1><p>Offers appear only when the official page provides a verifiable current price.</p><a class="button" href="{esc(p["source"])}" rel="noopener">Open official offer page ↗</a></section><section class="section"><div class="grid">{pcards}</div></section>'
        write(OUT / "providers" / f"{slug}.html", page(site, f"{p['name']} VPS Plans & Offers | {brand}", desc, content, pu, product))

    for i, o in enumerate(offers):
        slug = slugify(o["provider"] + "-" + o["title"])
        p = next((x for x in providers if x["name"] == o["provider"]), None)
        canonical = f"{base}/deals/{slug}.html" if base else ""
        valid = f'<p><b>Offer validity:</b> {esc(o["valid_until"])}</p>' if o.get("valid_until") else ""
        affiliate = o.get("affiliate_url") or o["offer_url"]
        content = f'<div class="crumb"><a href="/">Home</a> / Offers</div><article class="detail"><div class="kicker">Official-source offer</div><h1>{esc(o["provider"])} {esc(o["title"])}</h1><div class="bigprice">{esc(o["currency"])} {esc(o["price"])}</div><p>This price was read from the official page’s structured data at the time shown below. Billing period, required upfront payment, eligibility and renewal price have not been independently verified. Confirm these terms with the provider before comparing or purchasing.</p>{valid}<p><a class="button" href="{esc(affiliate)}" rel="nofollow sponsored noopener">Check official offer ↗</a></p><p class="source">Last checked {esc(o["fetched_at"])}</p><p class="source">Source: <a href="{esc(o["source_url"])}">{esc(o["source_url"])}</a></p></article>'
        product = {"@context":"https://schema.org","@type":"Offer","name":o["title"],"price":o["price"],"priceCurrency":o["currency"],"url":o["offer_url"],**({"priceValidUntil":o["valid_until"]} if o.get("valid_until") else {})}
        write(OUT / "deals" / f"{slug}.html", page(site, f"{o['provider']} {o['title']} | VPS offer | {brand}", f"Verified {o['currency']} {o['price']} offer from {o['provider']}. Check current provider terms.", content, canonical, product))

    compare = "".join(f'<tr><td><a href="/providers/{slugify(p["name"])}.html">{esc(p["name"])}</a></td><td>{len(by_provider.get(p["name"], []))}</td><td><a href="{esc(p["source"])}">Official source ↗</a></td></tr>' for p in providers)
    compare_content = f'<div class="crumb"><a href="/">Home</a> / Compare</div><section class="providerhero"><div class="kicker">Provider index</div><h1>Compare tracked sources</h1><p>Counts include only offers with a source-listed price. They are not rankings or recommendations.</p></section><div class="tablewrap"><table><thead><tr><th>Provider</th><th>Verified offers</th><th>Source</th></tr></thead><tbody>{compare}</tbody></table></div>'
    write(OUT / "compare.html", page(site, f"Compare VPS Providers | {brand}", "Compare tracked VPS providers by current source-listed prices and official source pages.", compare_content, base + "/compare.html" if base else "", {"@context":"https://schema.org","@type":"ItemList","itemListElement":cat_items}))

    pages = [("", last_fetch), ("compare.html", last_fetch)] + provider_urls + [(f"/deals/{slugify(o['provider']+'-'+o['title'])}.html", o["fetched_at"][:10]) for o in offers]
    if base:
        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{esc(base + '/' + path.lstrip('/'))}</loc>{("<lastmod>" + esc(lastmod) + "</lastmod>") if lastmod else ""}</url>" for path, lastmod in pages) + "</urlset>\n"
        (OUT / "sitemap.xml").write_text(sitemap, encoding="utf-8")
        (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    else:
        (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!-- Set base_url in .ilang/site.ilang to the exact assigned production URL to publish sitemap URLs. -->\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>\n', encoding="utf-8")
        (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    print(f"Built {len(offers)} source-listed prices and {len(providers)} provider pages into {OUT}")


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-") or "item"


STYLE = '''@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root{--ink:#13232d;--muted:#667985;--line:#dce5e5;--paper:#f6f8f5;--white:#fff;--lime:#c4ef70;--green:#123e35;--orange:#f1764c}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 'DM Sans',sans-serif}a{color:inherit}.top{height:72px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 max(calc((100vw - 1140px)/2),24px);background:rgba(246,248,245,.92)}.brand{text-decoration:none;font:700 18px 'Space Grotesk',sans-serif;letter-spacing:-.6px}.brand span{color:var(--muted);font:400 12px 'DM Mono',monospace;margin-left:8px}.top nav{display:flex;gap:28px;font-size:13px}.top nav a{text-decoration:none;color:var(--muted)}main{max-width:1140px;margin:auto;padding:0 24px}.hero{margin:66px 0 60px;background:var(--green);color:white;border-radius:18px;padding:62px 7%;position:relative;overflow:hidden}.hero:after{content:'';position:absolute;width:390px;height:390px;border:1px solid #ffffff22;border-radius:50%;right:-85px;top:-210px;box-shadow:0 0 0 38px #ffffff09,0 0 0 78px #ffffff08}.kicker{font:500 10px 'DM Mono',monospace;text-transform:uppercase;letter-spacing:1.8px;color:#778b81}.hero .kicker{color:var(--lime)}h1,h2,h3{font-family:'Space Grotesk',sans-serif;line-height:1.08;letter-spacing:-1.7px}h1{font-size:clamp(42px,7vw,72px);margin:20px 0 18px;max-width:780px}h1 em{font-style:normal;color:var(--lime)}.hero>p{color:#d2dfd9;max-width:540px;font-size:17px}.stats{display:flex;gap:48px;margin-top:44px}.stats div{display:grid}.stats b{font:600 25px 'Space Grotesk',sans-serif;color:var(--lime)}.stats span{font:10px 'DM Mono',monospace;color:#bbcbc3;text-transform:uppercase;letter-spacing:.8px}.section{margin:58px 0}.sectionhead{display:flex;justify-content:space-between;align-items:end;margin-bottom:22px}.sectionhead h2{margin:7px 0 0;font-size:30px}.textlink{font-size:13px;text-decoration:none;color:var(--green);font-weight:700}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(265px,1fr));gap:15px}.card{background:var(--white);border:1px solid var(--line);border-radius:12px;padding:22px;display:flex;flex-direction:column;min-height:220px}.eyebrow{font:10px 'DM Mono',monospace;text-transform:uppercase;letter-spacing:1.1px;color:#6d827b}.card h3{font-size:21px;margin:12px 0}.card h3 a{text-decoration:none}.price,.bigprice{font:600 29px 'Space Grotesk',sans-serif;margin:0;color:var(--green)}.muted,.source{font-size:12px;color:var(--muted)}.cardfoot{margin-top:auto;padding-top:20px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}.button{display:inline-block;background:var(--lime);color:#18392e;border:0;border-radius:5px;padding:10px 14px;text-decoration:none;font-weight:700;font-size:12px}.source{font-size:11px}.cardfoot span{font:10px 'DM Mono',monospace;color:var(--muted)}.providergrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}.provider{display:grid;grid-template-columns:1fr auto;text-decoration:none;background:white;border:1px solid var(--line);border-radius:9px;padding:16px}.provider span{font-weight:700}.provider small{grid-column:1;color:var(--muted);font:10px 'DM Mono',monospace;margin-top:7px}.provider b{grid-column:2;grid-row:1/3;color:#87988f}.empty{grid-column:1/-1;background:#fff;border:1px dashed #a8bbb1;border-radius:12px;padding:24px;display:flex;align-items:center;gap:17px}.empty p{margin:5px 0 0;color:var(--muted);font-size:13px}.pulse{width:10px;height:10px;border-radius:50%;background:#8eb65a;box-shadow:0 0 0 5px #8eb65a22}.note{display:flex;gap:14px;background:#edf1e9;padding:20px;border-radius:10px;margin:60px 0}.note p{margin:0;font-size:13px}.noteicon{font:700 14px 'DM Mono',monospace;background:var(--green);color:var(--lime);width:25px;height:25px;display:grid;place-items:center;border-radius:50%;flex:none}.providerhero{padding:60px 0 34px}.providerhero h1{font-size:clamp(40px,6vw,62px);margin:12px 0}.providerhero p{color:var(--muted);max-width:540px}.crumb{font:11px 'DM Mono',monospace;color:var(--muted);padding-top:30px}.detail{background:white;border:1px solid var(--line);border-radius:14px;padding:clamp(25px,5vw,54px);margin:24px 0 70px}.detail h1{font-size:clamp(34px,5vw,56px)}.detail p{max-width:700px;color:var(--muted)}.bigprice{font-size:42px;margin:20px 0}.tablewrap{overflow:auto;background:white;border:1px solid var(--line);border-radius:10px;margin:0 0 80px}table{width:100%;border-collapse:collapse;text-align:left}th,td{padding:15px 18px;border-bottom:1px solid var(--line);font-size:13px}th{font:10px 'DM Mono',monospace;text-transform:uppercase;color:var(--muted)}footer{max-width:1140px;margin:45px auto 0;padding:30px 24px 60px;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}footer p{margin:5px 0}footer a{color:var(--green)}@media(max-width:600px){.top{padding:0 18px}.top nav{gap:14px}main{padding:0 17px}.hero{margin:34px 0 44px;padding:38px 24px}.stats{gap:20px}.stats b{font-size:21px}.brand span{display:none}}
'''
FAVICON = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#123e35"/><path d="M17 17h30v8H25v7h18v8H25v7h22v8H17z" fill="#c4ef70"/></svg>'''
OG = '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#123e35"/><circle cx="1070" cy="40" r="300" fill="none" stroke="#ffffff" stroke-opacity=".12" stroke-width="2"/><circle cx="1070" cy="40" r="230" fill="none" stroke="#ffffff" stroke-opacity=".12" stroke-width="2"/><text x="86" y="155" fill="#c4ef70" font-family="monospace" font-size="24" letter-spacing="5">INDEPENDENT VPS PRICE WATCH</text><text x="82" y="320" fill="#ffffff" font-family="sans-serif" font-size="92" font-weight="700">VPS deals.</text><text x="82" y="430" fill="#c4ef70" font-family="sans-serif" font-size="72" font-weight="600">See the source.</text><text x="88" y="525" fill="#d2dfd9" font-family="monospace" font-size="22">OFFICIAL SOURCES · VERIFIED PRICES · NO GUESSES</text></svg>'''


if __name__ == "__main__":
    main()

"""Scrape the public Siemens Dynamo page into the app's reference data.

Produces:
  data/partners.json      real Dynamo partner startups (name, description from
                          the page, collaboration models, focus areas, and —
                          with --fetch-sites — a text excerpt of their own site)
  data/siemens_dynamo.md  what Siemens Dynamo is looking for: program pitch,
                          focus areas, collaboration models, eligibility.
                          Ingested as 'siemens' chunks so partner-fit scoring
                          is grounded in the OFFICIAL program criteria.

Robustness strategy: the live parse targets the page's current DOM
(accordions + focus-area tiles), and results are MERGED over an embedded
fallback snapshot (taken from the same page), so the output is never empty
if Siemens redesigns their site.

Usage:
  python -m scripts.scrape_dynamo                # parse page only
  python -m scripts.scrape_dynamo --fetch-sites  # also crawl each partner site
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DYNAMO_URL = ("https://www.siemens.com/en-us/company/"
              "siemens-software-for-startups/siemens-dynamo/")
UA = "Mozilla/5.0 (partner-scout research bot; recruiter assignment)"

# --- fallback snapshot of the Dynamo page (2026-07) ------------------------
FALLBACK_PARTNERS: dict[str, dict] = {
    "instrumental": {"name": "Instrumental", "url": "https://instrumental.com/",
        "models": ["Ecosystem Partners"],
        "description": "Manufacturing AI and Data Platform for brands and "
        "manufacturers of electronics: optimizes assembly, operations and "
        "quality control. Integrates with Siemens Teamcenter Quality "
        "(closed-loop quality); sold on Siemens Digital Exchange."},
    "boardera": {"name": "Boardera", "url": "https://www.boardera.ca/",
        "models": ["Ecosystem Partners"],
        "description": "E-commerce tooling for PCB manufacturers and EMS "
        "assemblers; available via Siemens PCB Flow platform."},
    "cybellum": {"name": "Cybellum", "url": "https://cybellum.com/",
        "models": ["Ecosystem Partners"],
        "description": "Product Security Platform (SBOM, vulnerability "
        "management, compliance) for device manufacturers; combined offering "
        "with Siemens Polarion ALM. Acquired by LG Electronics."},
    "cybord": {"name": "Cybord", "url": "https://cybord.ai/",
        "models": ["Portfolio Partners", "Research Partners"],
        "description": "Visual-AI electronic components analytics ensuring "
        "quality, authenticity and traceability of 100% of components; part "
        "of Siemens Opcenter offering for the electronics market."},
    "portcast": {"name": "Portcast", "url": "https://www.portcast.io/",
        "models": ["Portfolio Partners"],
        "description": "Predictive visibility and demand forecasting for "
        "international transportation (ML + GenAI over carrier/vessel/port "
        "data); partner of Siemens Digital Logistics, on Xcelerator "
        "Marketplace."},
    "realtimerobotics": {"name": "Realtime Robotics", "url": "https://rtr.ai/",
        "models": ["Portfolio Partners"],
        "description": "Software for programming robotic arms: automated "
        "motion planning and execution; seamless Siemens Process Simulate "
        "plug-in."},
    "retrocausal": {"name": "Retrocausal", "url": "https://retrocausal.ai/",
        "models": ["Research Partners"],
        "description": "AI-powered assembly copilots (ML + computer vision) "
        "guiding and analyzing manual assembly; integrated with Siemens "
        "Process Simulate Human and Opcenter Execution via funded research."},
    "skillreal": {"name": "SkillReal", "url": "https://www.skillreal.com/",
        "models": ["Research Partners", "Portfolio Partners"],
        "description": "AR-based digital-twin alignment for manufacturers, "
        "shortening ramp to serial production; BIRD-funded joint research; "
        "Siemens portfolio partner since 2023."},
    "inspekto": {"name": "Inspekto",
        "url": "https://www.siemens.com/global/en/products/automation/"
               "topic-areas/artificial-intelligence-in-industry/"
               "ai-on-shopfloor/ai-based-machine-vision/inspekto.html",
        "models": ["Investment Opportunities"],
        "description": "Out-of-the-box AI visual quality inspection, no vision "
        "expertise needed; joined Dynamo 2020, acquired by Siemens Digital "
        "Industries in 2024; integrates with Siemens Industrial Edge."},
    "iotech": {"name": "ioTech", "url": None,
        "models": ["Investment Opportunities"],
        "description": "Multi-material additive manufacturing at high "
        "resolution and speed; introduced by Dynamo to ASM Assembly Systems, "
        "leading to technology collaboration and capital investment."},
    "percepto": {"name": "Percepto", "url": "https://percepto.co/",
        "models": ["Startups as Suppliers"],
        "description": "Fully automated drone inspection and monitoring of "
        "vital infrastructure; used by Siemens Energy to monitor power "
        "plants since 2022."},
    "razorlabs": {"name": "Razor Labs", "url": "https://www.razor-labs.com/",
        "models": ["Startups as Suppliers"],
        "description": "AI solutions for industrial manufacturing (DataMind "
        "AI predictive maintenance); selected by Siemens Energy for a pilot "
        "at its O&M site in Israel."},
    "teamviewer": {"name": "Teamviewer", "url": "https://www.teamviewer.com/",
        "models": [], "description": "Remote connectivity and AR workflows."},
    "scopear": {"name": "ScopeAR", "url": "https://www.scopear.com/",
        "models": [], "description": "AR work instructions and remote "
        "assistance for industrial workers."},
    "goodlyinnovation": {"name": "Goodly Innovation",
        "url": "https://www.goodly-innovations.com/",
        "models": [], "description": "AR-supported workflow optimization for "
        "pharma/biotech operations (Siemens LivingLab collaboration)."},
    "artiminds": {"name": "Artiminds", "url": "https://www.artiminds.com/",
        "models": [], "description": "Robot programming and force-controlled "
        "automation software."},
}

FALLBACK_FOCUS_AREAS = {
    "Artificial Intelligence & Computer Vision":
        ["Instrumental", "Inspekto", "Cybord", "Retrocausal", "Razor Labs"],
    "AR/VR & Industrial Metaverse":
        ["Teamviewer", "SkillReal", "ScopeAR", "Goodly Innovation"],
    "Climate tech": [],
    "Digital Twin & Simulation": ["SkillReal", "Cybellum"],
    "Robotics & Automation": ["Realtime Robotics", "Artiminds", "Percepto"],
    "Supply Chain & Logistics": ["Portcast", "Boardera", "Cybord"],
}

PROGRAM_PITCH = (
    "Siemens Dynamo is Siemens' open innovation program. It helps startups "
    "bring new products to market by introducing them to Siemens units, "
    "customers, and partners. The program is keen to work with companies "
    "focusing on Industry 4.0 and digital transformation.")

MODEL_INTROS = {
    "Ecosystem Partners": "The most common collaboration model: startups with "
        "a complementary offering to the Siemens portfolio, often integrating "
        "with one or more Siemens products.",
    "Portfolio Partners": "A more advanced model: the startup offering is "
        "added to Siemens' price book and offered by Siemens' direct and "
        "indirect sales channels.",
    "Research Partners": "Joint research projects, funded by external "
        "research institutions or in some cases directly by Siemens.",
    "Investment Opportunities": "Dynamo does not include an investment "
        "element, but in a few cases the partnership led to equity "
        "discussions and agreements with Siemens or its partners.",
    "Startups as Suppliers": "Sometimes the preferred path is supplier "
        "relations with one of Siemens AG's domains (Digital Industries, "
        "Smart Infrastructure, Mobility, Energy and more).",
}

ELIGIBILITY = (
    "Open to innovative startups and established businesses in Industry 4.0 "
    "and digital transformation; technologies aligned with Siemens' "
    "interests, particularly industrial automation, digitalization and smart "
    "factories; typically companies that secured funding and identified "
    "their first repeatable, scalable use case which they want to scale with "
    "Siemens; no geographic restrictions. Engagement: scouting or "
    "application -> evaluation against Siemens requirements, portfolio and "
    "needs -> validation with business units -> technology pilot -> a "
    "Siemens business unit uses, partners with, includes in portfolio, or "
    "invests in the startup.")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _clean_url(href: str | None) -> str | None:
    if not href or href.startswith("mailto:"):
        return None
    if "safelinks.protection.outlook.com" in href:
        inner = parse_qs(urlparse(href).query).get("url", [None])[0]
        href = inner or None
    if href and "hubspotlinks" in href:      # tracking link, not a real site
        return None
    return href


def parse_live_page() -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Best-effort parse of the current Dynamo page DOM."""
    r = httpx.get(DYNAMO_URL, follow_redirects=True, timeout=20,
                  headers={"User-Agent": UA})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    partners: dict[str, dict] = {}
    # collaboration-model accordions: title button + partner h3>a blocks
    for acc in soup.select(".de-accordion"):
        title_el = acc.select_one(".de-accordion__title")
        body = acc.select_one(".de-accordion__body")
        if not title_el or not body:
            continue
        model = title_el.get_text(strip=True)
        if model not in MODEL_INTROS:        # skip FAQ accordions
            continue
        for h3 in body.select(".multitextblock h3"):
            a = h3.find("a", href=True)
            name = h3.get_text(strip=True)
            if not name:
                continue
            col = h3.find_parent("div")
            p = col.find("p") if col else None
            desc = " ".join(p.get_text(" ").split()) if p else ""
            key = _norm(name)
            entry = partners.setdefault(key, {
                "name": name, "url": _clean_url(a["href"] if a else None),
                "models": [], "description": desc})
            if model not in entry["models"]:
                entry["models"].append(model)
            if desc and len(desc) > len(entry["description"]):
                entry["description"] = desc

    # focus-area tiles: category h3 + linked startup names
    focus: dict[str, list[str]] = {}
    for wrapper in soup.select(".three-column-tile .tile-flex-wrapper"):
        h3 = wrapper.find("h3")
        if not h3:
            continue
        cat = h3.get_text(strip=True)
        names = [li.get_text(strip=True) for li in wrapper.select("li")]
        if cat in FALLBACK_FOCUS_AREAS or names:
            focus[cat] = names
            for n in names:
                key = _norm(n)
                partners.setdefault(key, {
                    "name": n, "url": None, "models": [], "description": ""})
    return partners, focus


def fetch_site_excerpt(url: str) -> str:
    try:
        r = httpx.get(url, follow_redirects=True, timeout=15,
                      headers={"User-Agent": UA})
        r.raise_for_status()
        s = BeautifulSoup(r.text, "html.parser")
        for t in s(["script", "style", "noscript", "svg", "nav", "footer"]):
            t.decompose()
        return " ".join(s.get_text(" ").split())[:1200]
    except httpx.HTTPError as e:
        print(f"  ! could not fetch {url}: {e}")
        return ""


def main(fetch_sites: bool) -> None:
    now = datetime.now(timezone.utc).isoformat()

    # 1. live parse, merged over the fallback snapshot ----------------------
    try:
        live_partners, live_focus = parse_live_page()
        print(f"live parse: {len(live_partners)} partners, "
              f"{len(live_focus)} focus areas")
    except Exception as e:
        print(f"live parse failed ({e}) — using fallback snapshot only")
        live_partners, live_focus = {}, {}

    partners: dict[str, dict] = {}
    for key, fb in FALLBACK_PARTNERS.items():
        partners[key] = dict(fb)
    for key, lv in live_partners.items():
        base = partners.setdefault(key, {"name": lv["name"], "url": None,
                                         "models": [], "description": ""})
        base["url"] = lv.get("url") or base.get("url")
        base["models"] = sorted(set(base["models"]) | set(lv.get("models", [])))
        if len(lv.get("description", "")) > len(base["description"]):
            base["description"] = lv["description"]

    focus = live_focus or FALLBACK_FOCUS_AREAS
    name_to_areas: dict[str, list[str]] = {}
    for area, names in focus.items():
        for n in names:
            name_to_areas.setdefault(_norm(n), []).append(area)

    # 2. optional: crawl each partner's own site ----------------------------
    for key, p in partners.items():
        p["focus_areas"] = name_to_areas.get(key, [])
        if fetch_sites and p.get("url"):
            print(f"fetching {p['name']} site...")
            p["site_excerpt"] = fetch_site_excerpt(p["url"])
            time.sleep(0.5)

    # 3. write partners.json (description = full embeddable text) -----------
    out = []
    for p in sorted(partners.values(), key=lambda x: x["name"].lower()):
        text = p["description"]
        if p.get("models"):
            text += f" Collaboration with Siemens: {', '.join(p['models'])}."
        if p.get("focus_areas"):
            text += f" Dynamo focus areas: {', '.join(p['focus_areas'])}."
        if p.get("site_excerpt"):
            text += f" From their website: {p['site_excerpt']}"
        out.append({"name": p["name"], "description": text.strip(),
                    "url": p.get("url"), "models": p.get("models", []),
                    "focus_areas": p.get("focus_areas", []),
                    "source": DYNAMO_URL, "scraped_at": now})
    (DATA_DIR / "partners.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote data/partners.json ({len(out)} partners)")

    # 4. write siemens_dynamo.md — the official 'what Siemens looks for' ----
    md = ["# Siemens Dynamo — what Siemens looks for (scraped from the "
          f"official page)\n\nSource: {DYNAMO_URL} (scraped {now})\n",
          "## Siemens Dynamo program\n" + PROGRAM_PITCH,
          "## Dynamo focus areas\nSiemens Dynamo scouts and partners with "
          "startups in these areas: " + "; ".join(focus.keys()) + ". "
          "Example partners per area: " + " | ".join(
              f"{a}: {', '.join(n) if n else '(open)'}"
              for a, n in focus.items())]
    for model, intro in MODEL_INTROS.items():
        names = [p["name"] for p in out if model in p.get("models", [])]
        md.append(f"## Collaboration model: {model}\n{intro}"
                  + (f" Examples: {', '.join(names)}." if names else ""))
    md.append("## Eligibility and engagement process\n" + ELIGIBILITY)
    (DATA_DIR / "siemens_dynamo.md").write_text("\n\n".join(md) + "\n",
                                                encoding="utf-8")
    print("wrote data/siemens_dynamo.md")
    print("re-run the app (or scripts.seed) — checksum detection will "
          "re-embed only the changed docs")


if __name__ == "__main__":
    main(fetch_sites="--fetch-sites" in sys.argv)

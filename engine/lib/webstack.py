"""Website technographics (paid tools rejected — this is stdlib, one homepage GET).

OBSERVED stack (what's actually installed on the site) vs jd_mining's STATED stack (what
job ads say). Precision rule (same lesson as jd_mining's "outreach" trap): NEVER match tool
names — a blog post saying "we integrated Intercom" must not fire. Match vendor CDN domains /
script paths that only appear when the snippet is really installed.
"""
from __future__ import annotations

import re
from collections import OrderedDict

from .http import fetch_full
from .identity import registrable_domain

# name: (category, domain-anchored regex). Curated GTM-relevant subset, not all of Wappalyzer.
FINGERPRINTS = {
    # Analytics
    "Google Tag Manager": ("Analytics", r"googletagmanager\.com/gtm\.js"),
    "Segment": ("Analytics", r"cdn\.segment\.com/analytics"),
    "Amplitude": ("Analytics", r"cdn\.amplitude\.com|api\.amplitude\.com"),
    "Mixpanel": ("Analytics", r"cdn\.mxpnl\.com"),
    "PostHog": ("Analytics", r"[a-z0-9.-]*posthog\.com/(?:static|array)|posthog-init\.js"),
    "Heap": ("Analytics", r"cdn\.heapanalytics\.com"),
    "Hotjar": ("Analytics", r"static\.hotjar\.com"),
    "FullStory": ("Analytics", r"edge\.fullstory\.com"),
    "Plausible": ("Analytics", r"plausible\.io/js"),
    # Marketing / CRM
    "HubSpot": ("Marketing", r"js\.hs-scripts\.com|js\.hsforms\.net|js\.hs-analytics\.net"),
    "Marketo": ("Marketing", r"munchkin\.marketo\.net"),
    "Klaviyo": ("Marketing", r"static\.klaviyo\.com"),
    "Pardot": ("Marketing", r"pi\.pardot\.com"),
    "LinkedIn Insight": ("Marketing", r"snap\.licdn\.com"),
    "Meta Pixel": ("Marketing", r"connect\.facebook\.net/[^\"']*/fbevents"),
    "Clearbit": ("Marketing", r"tag\.clearbitscripts\.com"),
    "Customer.io": ("Marketing", r"track\.customer\.io"),
    "Braze": ("Marketing", r"appboycdn|sdk\.[a-z0-9-]+\.braze\.com"),
    # ABM / intent — de-anonymizing site traffic = a sophisticated outbound buyer (the spice)
    "6sense": ("ABM/Intent", r"j\.6sc\.co"),
    "Demandbase": ("ABM/Intent", r"tag\.demandbase\.com"),
    "Mutiny": ("ABM/Intent", r"mutinycdn\.com"),
    "Qualified": ("ABM/Intent", r"js\.qualified\.com"),
    "Koala": ("ABM/Intent", r"cdn\.getkoala\.com"),
    "RB2B": ("ABM/Intent", r"reb2b\.com|b2bjsstore"),
    "Vector": ("ABM/Intent", r"cdn\.vector\.co"),
    "Warmly": ("ABM/Intent", r"warmly\.ai"),
    "Leadfeeder": ("ABM/Intent", r"sc\.lfeeder\.com"),
    "Albacross": ("ABM/Intent", r"serve\.albacross\.com|albacross\.com/track"),
    "Factors.ai": ("ABM/Intent", r"app\.factors\.ai|cdn\.factors\.ai"),
    "Snitcher": ("ABM/Intent", r"snitcher\.com"),
    # CDP / data
    "RudderStack": ("CDP", r"cdn\.rudderlabs\.com|cdn\.rudderstack\.com"),
    "Tealium": ("CDP", r"tags\.tiqcdn\.com"),
    "mParticle": ("CDP", r"jssdkcdns\.mparticle\.com"),
    # Consent / privacy — compliance posture (relevant when you SELL compliance)
    "OneTrust": ("Consent", r"cdn\.cookielaw\.org|otSDKStub\.js"),
    "Cookiebot": ("Consent", r"consent\.cookiebot\.com"),
    "Osano": ("Consent", r"cmp\.osano\.com"),
    "Termly": ("Consent", r"app\.termly\.io"),
    # Product-led / experimentation
    "Pendo": ("Product", r"cdn\.pendo\.io"),
    "LaunchDarkly": ("Product", r"[a-z]+\.launchdarkly\.com"),
    "Statsig": ("Product", r"featuregates\.org|[a-z]+\.statsig\.com"),
    "LogRocket": ("Product", r"cdn\.logrocket\.io|cdn\.lr-ingest\.io"),
    "Sprig": ("Product", r"cdn\.sprig\.com"),
    "Appcues": ("Product", r"[a-z]+\.appcues\.com"),
    "Chameleon": ("Product", r"fast\.trychameleon\.com"),
    # Support / Chat
    "Intercom": ("Support/Chat", r"widget\.intercom\.io|js\.intercomcdn\.com"),
    "Drift": ("Support/Chat", r"js\.driftt\.com"),
    "Zendesk": ("Support/Chat", r"static\.zdassets\.com"),
    "Crisp": ("Support/Chat", r"client\.crisp\.chat"),
    "Tidio": ("Support/Chat", r"code\.tidio\.co"),
    "LiveChat": ("Support/Chat", r"cdn\.livechatinc\.com"),
    "Gorgias": ("Support/Chat", r"config\.gorgias\.chat"),
    "Ada": ("Support/Chat", r"static\.ada\.support"),
    # Scheduling / Demo
    "Calendly": ("Scheduling", r"assets\.calendly\.com"),
    "Chili Piper": ("Scheduling", r"js\.chilipiper\.com"),
    "Navattic": ("Scheduling", r"js\.navattic\.com"),
    "Storylane": ("Scheduling", r"js\.storylane\.io"),
    "Cal.com": ("Scheduling", r"app\.cal\.com|cal\.com/embed"),
    "RevenueHero": ("Scheduling", r"revenuehero\.io"),
    # CMS / Framework
    "Webflow": ("CMS", r"assets\.website-files\.com|data-wf-domain"),
    "WordPress": ("CMS", r"/wp-content/"),
    "Shopify": ("CMS", r"cdn\.shopify\.com"),
    "Contentful": ("CMS", r"ctfassets\.net"),
    "Sanity": ("CMS", r"cdn\.sanity\.io"),
    "Framer": ("CMS", r"framerusercontent\.com"),
    "Next.js": ("Framework", r"/_next/static/"),
    "Nuxt": ("Framework", r"/_nuxt/"),
    "Gatsby": ("Framework", r'id="___gatsby"'),
    # A/B
    "Optimizely": ("A/B", r"cdn\.optimizely\.com"),
    "VWO": ("A/B", r"visualwebsiteoptimizer\.com|dev\.visualwebsiteoptimizer"),
    # Payments
    "Stripe": ("Payments", r"js\.stripe\.com"),
}

# name: (category, header_name, regex_or_None). None → header presence suffices.
HEADER_FPS = {
    "Cloudflare": ("Infra", "cf-ray", None),
    "Vercel": ("Infra", "x-vercel-id", None),
    "Netlify": ("Infra", "x-nf-request-id", None),
    "Fastly": ("Infra", "x-served-by", r"fastly|cache-"),
    "CloudFront": ("Infra", "x-amz-cf-id", None),
    "Fly.io": ("Infra", "fly-request-id", None),
}

def _lits(rx: str) -> list[str]:
    """A prefilter literal per top-level alternative — prefilter passes if ANY is present.
    (Must cover every alt, or a match in a later alt gets wrongly skipped.)"""
    out = []
    for alt in rx.split("|"):
        m = re.search(r"[a-z0-9]{4,}", alt, re.I)
        if m:
            out.append(m.group(0).lower())
    return out


_FP = [(n, c, re.compile(r, re.I), _lits(r)) for n, (c, r) in FINGERPRINTS.items()]


def detect(html: str, headers: dict) -> list[dict]:
    """Pure, offline-testable. Returns [{tool, category, evidence}]."""
    out, seen = [], set()
    low = (html or "").lower()
    for name, cat, rx, lits in _FP:
        if lits and not any(l in low for l in lits):
            continue
        m = rx.search(html or "")
        if m and name not in seen:
            seen.add(name)
            out.append({"tool": name, "category": cat, "evidence": m.group(0)[:60]})
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    for name, (cat, hname, hre) in HEADER_FPS.items():
        v = headers.get(hname)
        if v is not None and (hre is None or re.search(hre, str(v), re.I)) and name not in seen:
            seen.add(name)
            out.append({"tool": name, "category": cat, "evidence": f"header {hname}"})
    return out


def collect(domain: str) -> dict:
    reg = registrable_domain(domain)
    code, body, headers = fetch_full(f"https://{reg}", maxbytes=300_000)
    if code == 0:
        return {"source": "webstack", "status": "error", "error": "site fetch failed",
                "note": "Homepage fetch failed — not confirmed empty."}
    hits = detect(body.decode("utf-8", "replace"), headers)
    if not hits:
        return {"source": "webstack", "status": "empty",
                "note": "No known technographic fingerprints on the homepage."}
    by_cat: "OrderedDict[str, list]" = OrderedDict()
    for h in hits:
        by_cat.setdefault(h["category"], []).append(h["tool"])
    return {
        "source": "webstack", "status": "active", "count": len(hits),
        "by_category": by_cat,
        "signals": [{"title": f"{cat}: {', '.join(tools)}"} for cat, tools in by_cat.items()],
        "detections": hits,
        "note": "Observed on the live site (fingerprinted script/header evidence, "
                "domain-anchored). Point-in-time, not a last-quarter event.",
    }

"""JD mining — extract tech stack + stated priorities from job descriptions we already
fetch (zero new API calls). Precision is the whole game: the naive approach counts
"customer outreach" as the tool Outreach. So:

  - Curated lexicon; unambiguous tools (Snowflake, Kubernetes) can bare-match.
  - AMBIGUOUS tokens (Outreach, Segment, Gong, Claude...) only count inside a
    skill-context window ("experience with X", "our stack", "proficiency in X").
  - Per-tool negative patterns kill known traps ("go-to-market", "customer segment").
  - The company's own name is never counted as part of its stack.
  - Every tool/priority carries the job it came from (provenance for citations).
"""
from __future__ import annotations

import re
from collections import OrderedDict

from .identity import norm_company

# Skill-context cues — an ambiguous tool only counts if one appears nearby.
_CUE = re.compile(
    r"\b(experience[d]?|proficien\w+|expertise|expert|familiar\w*|skill\w*|knowledge|"
    r"hands[- ]?on|fluen\w+|working|worked|work with|using|use of|built|build\w*|"
    r"stack|technolog\w+|tool\w*|platform\w*|framework\w*|language\w*|background|"
    r"understanding|competenc\w+|comfortable|adept|versed)\b", re.I)

# "Go" the language: a bare, common token. Count it only when a fellow language / infra
# term sits nearby (comma-lists like "Python, Go, Java"), and never in go-to-market etc.
_GO = re.compile(r"(?<![A-Za-z0-9])Go(?![A-Za-z0-9])")
_GO_CTX = re.compile(
    r"\b(golang|python|java|rust|ruby|scala|kotlin|elixir|erlang|rails|django|node|"
    r"c\+\+|language|backend|micro-?service|distributed system|goroutine|programming)\b", re.I)
_GO_NEG = re.compile(
    r"go[- ]to[- ]market|go[- ]live|go[- ]getter|good to go|on the go|go deep|let'?s go|"
    r"go public|go[- ]forward|ready to go|willing to go", re.I)


def _has_go(text: str, low: str) -> bool:
    if "go" not in low:
        return False
    for m in _GO.finditer(text):
        w = low[max(0, m.start() - 45): m.end() + 45]
        if _GO_NEG.search(w):
            continue
        if _GO_CTX.search(w):
            return True
    return False


# Stated-priority sentences ("you'll lead our EU expansion", "help us scale ...").
_PRIORITY = re.compile(
    r"\b(?:you(?:'ll| will| would| get to)|we(?:'re| are| will)|help(?:ing)?(?: us)?)\s+"
    r"(lead|own|build|drive|scale|launch|expand|grow|shape|define|establish|accelerate|"
    r"deliver|develop|spearhead|pioneer|redefine|reimagine|transform)\b[^.\n;]{8,150}",
    re.I)

# (name, category, ambiguous, [aliases], neg_pattern_or_None)
_LEXICON = [
    # Languages / frameworks
    ("Python", "Languages", False, ["Python"], None),
    ("TypeScript", "Languages", False, ["TypeScript"], None),
    ("JavaScript", "Languages", False, ["JavaScript"], None),
    # "Go" (the language) is handled specially below — bare token needs flanking-language
    # context, which the generic skill-cue matcher can't provide precisely.
    ("Ruby", "Languages", False, ["Ruby on Rails", "Ruby"], None),
    ("Rust", "Languages", False, ["Rust"], None),
    ("Java", "Languages", False, ["Java"], None),
    ("Kotlin", "Languages", False, ["Kotlin"], None),
    ("Scala", "Languages", False, ["Scala"], None),
    ("Elixir", "Languages", False, ["Elixir"], None),
    ("C++", "Languages", False, [r"C\+\+"], None),
    (".NET", "Languages", False, [r"\.NET", "C#"], None),
    ("React", "Languages", True, ["React", "React.js"], r"react to|reaction|reactive"),
    ("Next.js", "Languages", False, ["Next.js"], None),
    ("Node.js", "Languages", False, ["Node.js", "NodeJS"], None),
    ("Django", "Languages", False, ["Django"], None),
    ("Rails", "Languages", True, ["Rails"], r"guard\s?rails|off the rails"),
    ("GraphQL", "Languages", False, ["GraphQL"], None),
    # Data stores + tooling
    ("PostgreSQL", "Data", False, ["PostgreSQL", "Postgres"], None),
    ("MySQL", "Data", False, ["MySQL"], None),
    ("MongoDB", "Data", False, ["MongoDB"], None),
    ("Redis", "Data", False, ["Redis"], None),
    ("Elasticsearch", "Data", False, ["Elasticsearch"], None),
    ("Snowflake", "Data", False, ["Snowflake"], None),
    ("BigQuery", "Data", False, ["BigQuery"], None),
    ("Redshift", "Data", False, ["Redshift"], None),
    ("Databricks", "Data", False, ["Databricks"], None),
    ("dbt", "Data", False, ["dbt"], None),
    ("Airflow", "Data", False, ["Airflow"], None),
    ("Kafka", "Data", False, ["Kafka"], None),
    ("Spark", "Data", True, ["Spark"], r"sparked|sparks? (?:joy|interest)"),
    ("Fivetran", "Data", False, ["Fivetran"], None),
    ("Segment", "Data", True, ["Segment"], r"(?:customer|market|audience|user|revenue|enterprise)\s+segment"),
    ("Looker", "Data", False, ["Looker"], None),
    ("Tableau", "Data", False, ["Tableau"], None),
    ("Amplitude", "Data", True, ["Amplitude"], None),
    ("Mixpanel", "Data", False, ["Mixpanel"], None),
    # Cloud / infra
    ("AWS", "Cloud/Infra", False, ["AWS", "Amazon Web Services"], None),
    ("GCP", "Cloud/Infra", False, ["GCP", "Google Cloud"], None),
    ("Azure", "Cloud/Infra", False, ["Azure"], None),
    ("Kubernetes", "Cloud/Infra", False, ["Kubernetes", "k8s"], None),
    ("Docker", "Cloud/Infra", False, ["Docker"], None),
    ("Terraform", "Cloud/Infra", False, ["Terraform"], None),
    ("Datadog", "Cloud/Infra", False, ["Datadog"], None),
    ("Prometheus", "Cloud/Infra", False, ["Prometheus"], None),
    ("Grafana", "Cloud/Infra", False, ["Grafana"], None),
    # AI / ML
    ("OpenAI", "AI/ML", False, ["OpenAI"], None),
    ("Anthropic", "AI/ML", False, ["Anthropic"], None),
    ("Claude", "AI/ML", True, ["Claude"], None),
    ("LangChain", "AI/ML", False, ["LangChain"], None),
    ("Hugging Face", "AI/ML", False, ["Hugging Face", "HuggingFace"], None),
    ("PyTorch", "AI/ML", False, ["PyTorch"], None),
    ("TensorFlow", "AI/ML", False, ["TensorFlow"], None),
    ("Pinecone", "AI/ML", True, ["Pinecone"], None),
    ("LLM", "AI/ML", False, ["LLMs", "LLM"], None),
    # GTM / CRM / marketing
    ("Salesforce", "GTM/CRM", False, ["Salesforce", "SFDC"], None),
    ("HubSpot", "GTM/CRM", False, ["HubSpot"], None),
    ("Marketo", "GTM/CRM", False, ["Marketo"], None),
    ("Outreach", "GTM/CRM", True, ["Outreach"], None),
    ("Salesloft", "GTM/CRM", False, ["Salesloft", "SalesLoft"], None),
    ("Gong", "GTM/CRM", True, ["Gong"], None),
    ("Apollo", "GTM/CRM", True, ["Apollo"], r"Apollo (?:mission|program|11|GraphQL)"),
    ("Clay", "GTM/CRM", True, ["Clay"], None),
    ("ZoomInfo", "GTM/CRM", False, ["ZoomInfo"], None),
    ("Klaviyo", "GTM/CRM", False, ["Klaviyo"], None),
    ("Census", "GTM/CRM", True, ["Census"], r"census (?:data|bureau|tract)"),
    ("Hightouch", "GTM/CRM", False, ["Hightouch"], None),
    # Product / design
    ("Figma", "Product/Design", False, ["Figma"], None),
    ("Jira", "Product/Design", False, ["Jira"], None),
    ("Asana", "Product/Design", False, ["Asana"], None),
    ("Webflow", "Product/Design", False, ["Webflow"], None),
    ("Contentful", "Product/Design", False, ["Contentful"], None),
    ("Notion", "Product/Design", True, ["Notion"], r"notion (?:of|that)"),
    ("Linear", "Product/Design", True, ["Linear"], r"linear (?:algebra|regression|equation|function|scale|combination)"),
]


def _compile(alias: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", re.I)


_TOOLS = []
for name, cat, amb, aliases, neg in _LEXICON:
    _TOOLS.append({
        "name": name, "category": cat, "ambiguous": amb,
        "aliases": [_compile(a) for a in aliases],
        "literals": [a.lower() for a in aliases],
        "neg": re.compile(neg, re.I) if neg else None,
    })

_CATEGORY_ORDER = ["Languages", "Data", "Cloud/Infra", "AI/ML", "GTM/CRM", "Product/Design"]


def _tool_in_jd(tool: dict, text: str, low: str) -> bool:
    if not any(lit in low for lit in tool["literals"]):  # cheap prefilter
        return False
    for rx in tool["aliases"]:
        for m in rx.finditer(text):
            window = text[max(0, m.start() - 60): m.end() + 40]
            if tool["neg"] and tool["neg"].search(window):
                continue
            if not tool["ambiguous"] or _CUE.search(window):
                return True
    return False


def _clean_phrase(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" -–—•*:;,")
    if len(s) > 130:  # trim to a word boundary instead of cutting mid-word
        s = s[:130].rsplit(" ", 1)[0].rstrip(" ,") + "…"
    return s


def mine(jobs: list[dict], brand: str | None = None) -> dict:
    """Return {tech_stack, tech_by_category, priorities}. Each item carries provenance."""
    self_tokens = set(norm_company(brand or "").split())
    tech: "OrderedDict[str, dict]" = OrderedDict()
    priorities: list[dict] = []
    seen_pri: set = set()

    for j in jobs:
        text = j.get("text") or ""
        if not text:
            continue
        low = text.lower()
        title, url = j.get("title"), j.get("url")
        for tool in _TOOLS:
            if tool["name"].lower() in self_tokens:  # don't list the company's own name
                continue
            if _tool_in_jd(tool, text, low):
                rec = tech.setdefault(tool["name"], {"category": tool["category"], "jobs": OrderedDict()})
                rec["jobs"].setdefault(title, url)
        if "go" not in self_tokens and _has_go(text, low):  # bare "Go" special case
            tech.setdefault("Go", {"category": "Languages", "jobs": OrderedDict()})["jobs"].setdefault(title, url)
        for m in _PRIORITY.finditer(text):
            phrase = _clean_phrase(m.group(0))
            k = phrase.lower()[:60]
            if len(phrase) > 20 and k not in seen_pri:
                seen_pri.add(k)
                priorities.append({"text": phrase, "job": title, "url": url})

    stack = sorted(
        [{"tool": n, "category": d["category"], "job_count": len(d["jobs"]),
          "example_job": next(iter(d["jobs"]), None),
          "example_url": next(iter(d["jobs"].values()), None)} for n, d in tech.items()],
        key=lambda x: (-x["job_count"], x["tool"]))

    by_cat: "OrderedDict[str, list]" = OrderedDict()
    for cat in _CATEGORY_ORDER:
        tools = [t["tool"] for t in stack if t["category"] == cat]
        if tools:
            by_cat[cat] = tools

    return {"tech_stack": stack, "tech_by_category": by_cat, "priorities": priorities[:6]}

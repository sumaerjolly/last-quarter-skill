# Issues Audit: Current Implementation

**Date:** 2026-07-02
**Sources:** self-audit + independent adversarial review agent (verified findings by
executing lib code + live API calls). Merged and ranked.

---

## The root cause (reviewer's synthesis)

**Every entity-resolution step is a lexical guess with no verification against the one
ground truth the user supplied — the domain.** CIK lookup, ATS board resolution, and
GitHub org matching all guess by name/slug, even though each API returns a field that
would confirm or refuse the match (SEC title/ticker, Greenhouse `company_name` + job
URLs, GitHub org `blog` field). Fix this class once before adding 9 more sources.

## CRITICAL — wrong-entity / fabrication-grade (fix before anything else)

1. **Funding headlines silently deleted for common-word names** (`news.py`
   `_common_word_usage`): the `[%$]\s*\d` alternative never references the company name,
   so ANY money headline is dropped — *"Increase raises $25M Series B"* → deleted, report
   says "no in-window news." The #1 ABM trigger, discarded. (Verified by execution.)
2. **EDGAR prefix-match routes private cos to unrelated public filers** (`edgar.py`):
   `mercury.com` → **MERCURY SYSTEMS (MRCY)**, `Wave` → Wave Life Sciences, `Linear` →
   Linear Minerals. Wrong company's 8-Ks, primary-sourced and fully cited = maximally
   convincing wrong report. No domain/ticker cross-check. (Verified live.)
3. **GitHub org matched by slug, zero identity check** (`github.py`): `orgs/notion` is
   **"Trove"**, an unrelated org — its releases would be reported as Notion launches.
   Fix is one field: `/orgs/{org}.blog` vs input domain. (Verified live.)

## MAJOR

4. **GDELT bypasses the common-word filter** and the note then claims "filtered… (0
   dropped)" — floods exactly when the name is most ambiguous; items never date-bucketed.
5. **Transport failures indistinguishable from "no signal"** (`http.py` swallows all →
   `(0, b"")`): DNS outage/rate-limit renders as confident "private / no org / thin news
   is normal" narratives. Footer `⚠ error` is effectively unreachable. The trust device
   lies under failure.
6. **Blog "feed exists but quiet quarter" misreported** as "no feed — likely JS shell,
   add Firecrawl" (wrong recommended action; true signal "blog silent 90d" unsayable).
7. **ATS board ownership never verified** — slug squatting on any of 3 ATS namespaces
   yields another employer's hiring data with exact counts. Greenhouse returns
   `company_name` per job; currently discarded.
8. **EDGAR citations point at a list page, not the filing** — accession number parsed but
   unused; direct archive URL never built.
9. **Blog date extraction: first date-ish match wins** (nav banners, related-post cards,
   other entries' dates on changelog pages) + `_HTML_FALLBACK_CAP=20` makes `count` an
   unflagged floor. Plus the known **CMS-migration date reset** (AirOps: 20 posts stamped
   2026-06-28) has no "many-posts-share-one-date" low-confidence flag.
10. **Footer miscounts with `--no-github`** (prints `github ✗` + `2/4` while listing 5)
    and hardcodes order/count-keys — breaks silently at 14 sources.
11. **Hardcoded 28-name common-word list** — "Bolt/Plaid/Anchor/…" outside the set get
    `noisy: false` = affirmative false confidence. Needs a computed signal (fraction of
    headlines failing entity check), not a lookup table.
12. **Google News citation URLs are opaque redirect blobs** (`CBMi…`) that rot; and
    `unknown`-dated news items ship as in-window claims.
13. **Zero automated tests** — six paid-for bug-fixes (CIK collision, Lever `[]`, date
    formats…) are one refactor from regressing. Need pytest + recorded fixtures.

## MINOR (tracked, not urgent)

- "~7 seconds" is best-case; timeouts accumulate serially; `lookup_cik` (~1MB) runs
  before the pool. GitHub unauth = 60 req/hr, engine burns ~10-12/run; 403 reads as "no
  org matched." Greenhouse dept null (fix rides along with JD-mining's `?content=true`).
  Dead prior-window code + SKILL.md still references trend bucketing. UTF-8 re-encode
  mangling; Atom first-`<link>` regardless of rel; `_POST_LINK` misses absolute/subdomain/
  dated permalinks. Local `date.today()` vs UTC bucketing edge. Personal email in UA.
  Duplicate job titles rendered. SKILL.md engine-first flow never subagent-tested.

## Proposed sequencing (merges with free-source expansion)

1. **Trust batch (small, highest stakes):** fix #1 regex; domain-verify the three entity
   resolvers (#2, #3, #7 — same pattern); `error`≠`empty` statuses honest in footer (#5,
   #10); GDELT through the filter (#4); blog empty-vs-quiet (#6); EDGAR archive URLs (#8).
2. **Test harness:** pytest + fixtures locking every fix above + the six historical ones.
3. **Registry refactor** (already agreed) — fixes footer hardcoding structurally.
4. **Then** Tier-1 free sources (+ JD mining & podcasts, both verified) on the clean base.

## Open Questions

1. Ship a hotfix commit for #1–#3 immediately, or batch with the trust cluster?
2. Common-word detection approach: entity-check-failure ratio vs dictionary lookup?
3. Google News URL resolution: decode redirect (fragile) vs cite outlet+date+title only?

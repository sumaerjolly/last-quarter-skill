"""Source registry — data-driven fan-out so adding a source is one line + a collector.

Each Source declares: key, tier, a run(ctx) callable, and an applies(ctx) predicate.
The orchestrator iterates SOURCES; the footer uses SOURCE_ORDER. No more hardcoded
task dicts / footer special-cases scattered across the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import blog, careers, edgar, github, hackernews, news, status


@dataclass
class Ctx:
    domain: str
    name: str
    window: dict
    cik_info: dict | None = None
    orgs: list = field(default_factory=list)
    keywords: str | None = None
    use_gdelt: bool = True
    use_github: bool = True


@dataclass
class Source:
    key: str
    tier: str  # "free" | "paid"
    run: Callable[[Ctx], dict]
    applies: Callable[[Ctx], bool] = lambda ctx: True


SOURCES: list[Source] = [
    Source("careers", "free", lambda c: careers.collect(c.domain, c.name, c.window)),
    Source("news", "free",
           lambda c: news.collect(c.name, c.window, use_gdelt=c.use_gdelt, keywords=c.keywords)),
    Source("blog", "free", lambda c: blog.collect(c.domain, c.window)),
    Source("status", "free", lambda c: status.collect(c.domain, c.window)),
    Source("hackernews", "free", lambda c: hackernews.collect(c.name, c.domain, c.window)),
    Source("edgar", "free", lambda c: edgar.collect(c.name, c.window, c.cik_info)),
    Source("github", "free", lambda c: github.collect(c.orgs, c.window, c.domain),
           applies=lambda c: c.use_github),
]

SOURCE_ORDER = [s.key for s in SOURCES]

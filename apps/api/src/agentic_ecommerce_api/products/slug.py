"""Minimal slug helper.

Lowercases, replaces any run of non-alphanumeric chars with a single
hyphen, and trims hyphens at the ends. Good enough for ASCII names; if
the catalog needs accents / non-Latin scripts, swap in `python-slugify`.
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    return _NON_ALNUM.sub("-", value.lower().strip()).strip("-")

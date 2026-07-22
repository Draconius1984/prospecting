"""Data model for a single prospect record and the CSV schema."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Dict, List

# Column order used for every CSV the tool reads or writes.
CSV_FIELDS: List[str] = [
    "practice_name",
    "contact_name",   # person's full name
    "title",          # job title / role
    "company",        # employer / practice (alias of practice_name for people)
    "suburb",
    "region",
    "email",
    "email_type",     # generic | personal | unknown
    "email_status",   # verified | accept_all | probable | unverified | invalid
    "email_pattern",  # inferred pattern, e.g. {first}.{last}
    "phone",
    "website",
    "linkedin",
    "source_url",
    "services",
    "seniority",      # owner | director | manager | senior | staff
    "confidence",     # high | medium | low
    "status",         # new | crawled | validated | enriched | flagged
    "mx_ok",          # "", "yes", "no", "unknown"
    "notes",
]


@dataclass
class Prospect:
    """A single contact record — a practice (generic inbox) or a named person."""

    practice_name: str = ""
    contact_name: str = ""
    title: str = ""
    company: str = ""
    suburb: str = ""
    region: str = ""
    email: str = ""
    email_type: str = ""
    email_status: str = ""
    email_pattern: str = ""
    phone: str = ""
    website: str = ""
    linkedin: str = ""
    source_url: str = ""
    services: str = ""
    seniority: str = ""
    confidence: str = ""
    status: str = "new"
    mx_ok: str = ""
    notes: str = ""

    def key(self) -> str:
        """Deduplication key: email if present, else practice+website."""
        e = (self.email or "").strip().lower()
        if e:
            return e
        return f"{(self.practice_name or '').strip().lower()}|{(self.website or '').strip().lower()}"

    def to_row(self) -> Dict[str, str]:
        d = asdict(self)
        return {k: ("" if d.get(k) is None else str(d.get(k))) for k in CSV_FIELDS}

    @classmethod
    def from_row(cls, row: Dict[str, str]) -> "Prospect":
        # Only apply columns actually present in the row so that fields absent
        # from the CSV keep their dataclass defaults (e.g. status="new").
        known = {
            k: (row.get(k) or "").strip()
            for k in CSV_FIELDS
            if k in cls.__dataclass_fields__ and k in row
        }
        return cls(**known)

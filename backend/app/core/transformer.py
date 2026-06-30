"""
CandidateTransformer Core Engine
=================================
Merges multi-source candidate data into one canonical profile.
Priority: ATS JSON > CSV > GitHub > LinkedIn > Resume > Recruiter Notes
Confidence scoring prevents bad data from silently overwriting good data.
"""

from __future__ import annotations
import re
import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Literal
from datetime import datetime, timezone

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Enums & Constants
# ──────────────────────────────────────────────

class SourceType(str, Enum):
    CSV = "recruiter_csv"
    ATS = "ats_json"
    GITHUB = "github"
    LINKEDIN = "linkedin"
    RESUME = "resume"
    NOTES = "recruiter_notes"


# Higher = more authoritative
SOURCE_PRIORITY: dict[SourceType, int] = {
    SourceType.ATS: 100,
    SourceType.CSV: 90,
    SourceType.RESUME: 70,
    SourceType.LINKEDIN: 60,
    SourceType.GITHUB: 50,
    SourceType.NOTES: 30,
}

# ATS field-name → our canonical field-name
ATS_FIELD_MAP = {
    "full_name": "name",
    "candidate_name": "name",
    "contact_email": "email",
    "email_address": "email",
    "mobile": "phone",
    "phone_number": "phone",
    "employer": "current_company",
    "company": "current_company",
    "organization": "current_company",
    "job_title": "title",
    "position": "title",
    "role": "title",
    "location": "location",
    "city": "location",
    "skills_list": "skills",
    "tech_stack": "skills",
    "profile_summary": "summary",
    "about": "summary",
    "linkedin_url": "linkedin",
    "github_url": "github",
    "portfolio": "website",
    "years_experience": "years_of_experience",
    "experience_years": "years_of_experience",
}


# ──────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────

@dataclass
class FieldValue:
    """A single field value with full provenance."""
    value: Any
    source: SourceType
    confidence: float          # 0.0 – 1.0
    raw_value: Any = None      # exactly what came in
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "source": self.source.value,
            "confidence": round(self.confidence, 3),
            "raw_value": self.raw_value,
            "extracted_at": self.extracted_at,
        }


class ProjectionError(ValueError):
    """Raised when a projected field cannot be resolved or is required but missing."""


class FieldSpec(BaseModel):
    path: str
    from_: str = Field(alias="from")
    type: str = "string"
    required: bool = False
    normalize: Optional[str] = None

    class Config:
        populate_by_name = True


class OutputConfig(BaseModel):
    fields: list[FieldSpec]
    include_confidence: bool = True
    include_provenance: bool = True
    on_missing: Literal["null", "omit", "error"] = "null"


@dataclass
class CanonicalProfile:
    """The single trustworthy output profile."""
    candidate_id: str = ""
    name: Optional[FieldValue] = None
    email: Optional[FieldValue] = None
    phone: Optional[FieldValue] = None
    current_company: Optional[FieldValue] = None
    title: Optional[FieldValue] = None
    location: Optional[FieldValue] = None
    summary: Optional[FieldValue] = None
    skills: Optional[FieldValue] = None
    years_of_experience: Optional[FieldValue] = None
    linkedin: Optional[FieldValue] = None
    github: Optional[FieldValue] = None
    website: Optional[FieldValue] = None
    education: Optional[FieldValue] = None
    languages: Optional[FieldValue] = None   # programming languages (GitHub)
    top_repos: Optional[FieldValue] = None
    conflicts: list[dict] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self, config: OutputConfig | dict | None = None) -> dict:
        out: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "created_at": self.created_at,
            "sources_used": self.sources_used,
            "overall_confidence": round(self.overall_confidence, 3),
            "conflicts": self.conflicts,
            "fields": project_profile(self, config),
        }
        return out


# ──────────────────────────────────────────────
# Normalisation Utilities
# ──────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\-\.\(\) ]{6,17}\d)(?!\d)")
_YEAR_RE  = re.compile(r"\b(19|20)\d{2}\b")


def normalize_name(raw: str) -> tuple[str, float]:
    """Title-case, strip noise. Returns (cleaned, confidence)."""
    if not raw or not raw.strip():
        return "", 0.0
    cleaned = re.sub(r"[^a-zA-Z\s\-\']", "", raw).strip().title()
    parts = cleaned.split()
    if len(parts) < 2:
        return cleaned, 0.5        # single name → lower confidence
    return cleaned, 0.9


def normalize_email(raw: str) -> tuple[str, float]:
    if not raw:
        return "", 0.0
    m = _EMAIL_RE.search(str(raw))
    if not m:
        return "", 0.0
    email = m.group(0).lower()
    # Penalise obviously temp domains
    if any(d in email for d in ["tempmail", "mailinator", "guerrilla"]):
        return email, 0.4
    return email, 0.95


def normalize_phone(raw: str) -> tuple[str, float]:
    if not raw:
        return "", 0.0
    m = _PHONE_RE.search(str(raw))
    if not m:
        return "", 0.0
    digits = re.sub(r"\D", "", m.group(0))
    if len(digits) < 7:
        return "", 0.0
    # Numbers with a country code (11-15 digits) are the most complete/unambiguous
    if 11 <= len(digits) <= 15:
        return f"+{digits}", 0.95
    # Bare 10-digit numbers are usable but missing country code context
    if len(digits) == 10:
        return f"+{digits}", 0.75
    if len(digits) > 15:
        return f"+{digits}", 0.5
    return digits, 0.6


def normalize_skills(raw: Any) -> tuple[list[str], float]:
    if not raw:
        return [], 0.0
    if isinstance(raw, list):
        skills = [str(s).strip() for s in raw if s]
    else:
        skills = [s.strip() for s in re.split(r"[,;|\n]", str(raw)) if s.strip()]
    # Remove duplicates case-insensitively
    seen: set[str] = set()
    unique: list[str] = []
    for s in skills:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique, min(0.5 + len(unique) * 0.05, 0.95)


def extract_years_of_experience(text: str) -> tuple[Optional[int], float]:
    """Heuristic: find phrases like '5 years experience'."""
    if not text:
        return None, 0.0
    patterns = [
        r"(\d+)\+?\s+years?\s+of\s+(?:professional\s+)?experience",
        r"(\d+)\+?\s+years?\s+(?:in|of|working)",
        r"experience\s+(?:of\s+)?(\d+)\+?\s+years?",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            yrs = int(m.group(1))
            if 0 < yrs < 60:
                return yrs, 0.7
    return None, 0.0


# ──────────────────────────────────────────────
# Source Parsers
# ──────────────────────────────────────────────

class SourceParser:
    """Base class for all source parsers."""

    @staticmethod
    def _make_fv(value: Any, source: SourceType, confidence: float,
                 raw: Any = None) -> Optional[FieldValue]:
        if value is None or value == "" or value == [] or value == {}:
            return None
        return FieldValue(value=value, source=source, confidence=confidence, raw_value=raw)


class CSVParser(SourceParser):
    """Recruiter CSV export → partial CanonicalProfile."""

    def parse(self, row: dict) -> CanonicalProfile:
        p = CanonicalProfile()
        src = SourceType.CSV

        raw_name = row.get("name") or row.get("full_name") or ""
        name, nc = normalize_name(raw_name)
        p.name = self._make_fv(name, src, nc, raw_name)

        raw_email = row.get("email") or row.get("email_address") or ""
        email, ec = normalize_email(raw_email)
        p.email = self._make_fv(email, src, ec, raw_email)

        raw_phone = row.get("phone") or row.get("mobile") or ""
        phone, pc = normalize_phone(raw_phone)
        p.phone = self._make_fv(phone, src, pc, raw_phone)

        raw_co = (row.get("current_company") or row.get("company") or "").strip()
        p.current_company = self._make_fv(raw_co, src, 0.85, raw_co) if raw_co else None

        raw_title = (row.get("title") or row.get("job_title") or "").strip()
        p.title = self._make_fv(raw_title, src, 0.85, raw_title) if raw_title else None

        return p


class ATSParser(SourceParser):
    """ATS JSON blob — field names may differ; we remap them."""

    def parse(self, blob: dict) -> CanonicalProfile:
        p = CanonicalProfile()
        src = SourceType.ATS

        # Remap ATS-specific keys to canonical keys
        remapped: dict[str, Any] = {}
        for k, v in blob.items():
            canon_key = ATS_FIELD_MAP.get(k.lower(), k.lower())
            remapped[canon_key] = v

        raw_name = remapped.get("name", "")
        name, nc = normalize_name(str(raw_name))
        p.name = self._make_fv(name, src, nc, raw_name)

        raw_email = remapped.get("email", "")
        email, ec = normalize_email(str(raw_email))
        p.email = self._make_fv(email, src, ec, raw_email)

        raw_phone = remapped.get("phone", "")
        phone, pc = normalize_phone(str(raw_phone))
        p.phone = self._make_fv(phone, src, pc, raw_phone)

        raw_co = str(remapped.get("current_company", "") or "").strip()
        p.current_company = self._make_fv(raw_co, src, 0.9, raw_co) if raw_co else None

        raw_title = str(remapped.get("title", "") or "").strip()
        p.title = self._make_fv(raw_title, src, 0.9, raw_title) if raw_title else None

        raw_loc = str(remapped.get("location", "") or "").strip()
        p.location = self._make_fv(raw_loc, src, 0.85, raw_loc) if raw_loc else None

        raw_summary = str(remapped.get("summary", "") or "").strip()
        p.summary = self._make_fv(raw_summary, src, 0.8, raw_summary) if raw_summary else None

        raw_skills = remapped.get("skills")
        if raw_skills:
            skills, sc = normalize_skills(raw_skills)
            p.skills = self._make_fv(skills, src, sc, raw_skills)

        raw_yoe = remapped.get("years_of_experience")
        if raw_yoe is not None:
            try:
                yoe = int(raw_yoe)
                p.years_of_experience = self._make_fv(yoe, src, 0.85, raw_yoe)
            except (ValueError, TypeError):
                pass

        raw_linkedin = str(remapped.get("linkedin", "") or "").strip()
        p.linkedin = self._make_fv(raw_linkedin, src, 0.9, raw_linkedin) if raw_linkedin else None

        raw_github = str(remapped.get("github", "") or "").strip()
        p.github = self._make_fv(raw_github, src, 0.9, raw_github) if raw_github else None

        return p


class GitHubParser(SourceParser):
    """GitHub API response → partial CanonicalProfile."""

    def parse(self, data: dict) -> CanonicalProfile:
        p = CanonicalProfile()
        src = SourceType.GITHUB

        raw_name = data.get("name") or ""
        name, nc = normalize_name(raw_name)
        p.name = self._make_fv(name, src, nc * 0.8, raw_name)   # GH name less reliable

        raw_email = data.get("email") or ""
        email, ec = normalize_email(raw_email)
        p.email = self._make_fv(email, src, ec * 0.7, raw_email)   # often hidden

        raw_co = (data.get("company") or "").strip().lstrip("@")
        p.current_company = self._make_fv(raw_co, src, 0.6, raw_co) if raw_co else None

        raw_loc = (data.get("location") or "").strip()
        p.location = self._make_fv(raw_loc, src, 0.65, raw_loc) if raw_loc else None

        raw_bio = (data.get("bio") or "").strip()
        p.summary = self._make_fv(raw_bio, src, 0.5, raw_bio) if raw_bio else None

        gh_url = f"https://github.com/{data.get('login', '')}" if data.get("login") else ""
        p.github = self._make_fv(gh_url, src, 0.99, gh_url) if gh_url else None

        # Languages & repos from repos list
        repos: list[dict] = data.get("repos", [])
        if repos:
            lang_count: dict[str, int] = {}
            for r in repos:
                lang = r.get("language")
                if lang:
                    lang_count[lang] = lang_count.get(lang, 0) + 1
            if lang_count:
                sorted_langs = sorted(lang_count, key=lambda x: -lang_count[x])
                p.languages = self._make_fv(sorted_langs, src, 0.85, lang_count)

            top = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:5]
            repo_list = [{"name": r.get("name"), "stars": r.get("stargazers_count", 0),
                          "description": r.get("description", "")} for r in top]
            p.top_repos = self._make_fv(repo_list, src, 0.9, None)

            # Skills from languages
            if lang_count:
                skills, sc = normalize_skills(list(lang_count.keys()))
                p.skills = self._make_fv(skills, src, sc * 0.75, lang_count)

        return p


class ResumeParser(SourceParser):
    """Extracted text from PDF/DOCX resume → partial CanonicalProfile."""

    def parse(self, text: str) -> CanonicalProfile:
        p = CanonicalProfile()
        src = SourceType.RESUME

        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # Name: usually first non-empty line
        if lines:
            name, nc = normalize_name(lines[0])
            if nc > 0.4:
                p.name = self._make_fv(name, src, nc * 0.85, lines[0])

        # Email anywhere in text
        email_m = _EMAIL_RE.search(text)
        if email_m:
            email, ec = normalize_email(email_m.group(0))
            p.email = self._make_fv(email, src, ec, email_m.group(0))

        # Phone anywhere in text
        phone_m = _PHONE_RE.search(text)
        if phone_m:
            phone, pc = normalize_phone(phone_m.group(0))
            p.phone = self._make_fv(phone, src, pc, phone_m.group(0))

        # LinkedIn URL
        li_m = re.search(r"linkedin\.com/in/[\w\-]+", text, re.IGNORECASE)
        if li_m:
            p.linkedin = self._make_fv("https://" + li_m.group(0), src, 0.9, li_m.group(0))

        # GitHub URL
        gh_m = re.search(r"github\.com/[\w\-]+", text, re.IGNORECASE)
        if gh_m:
            p.github = self._make_fv("https://" + gh_m.group(0), src, 0.9, gh_m.group(0))

        # Skills section
        skill_m = re.search(
            r"(?:skills?|technologies?|tech\s+stack|competencies)[:\s]*\n?(.*?)(?:\n{2,}|\Z)",
            text, re.IGNORECASE | re.DOTALL
        )
        if skill_m:
            skills, sc = normalize_skills(skill_m.group(1))
            if skills:
                p.skills = self._make_fv(skills, src, sc * 0.8, skill_m.group(1))

        # Title: look for common patterns
        title_m = re.search(
            r"(?:^|\n)((?:Senior|Junior|Lead|Principal|Staff)?\s*"
            r"(?:Software|Backend|Frontend|Full.Stack|ML|AI|Data|DevOps|Cloud)\s+"
            r"(?:Engineer|Developer|Scientist|Architect|Analyst))",
            text, re.IGNORECASE
        )
        if title_m:
            p.title = self._make_fv(title_m.group(1).strip(), src, 0.7, title_m.group(1))

        # Years of experience
        yoe, yc = extract_years_of_experience(text)
        if yoe:
            p.years_of_experience = self._make_fv(yoe, src, yc, None)

        # Summary: first few prose lines (skip name, headers, and contact-info lines)
        contact_pattern = re.compile(
            r"@|linkedin\.com|github\.com|^\+?\d[\d\s\-\(\)\.]{6,}$|^(skills?|education|experience)[:\s]*$",
            re.IGNORECASE,
        )
        prose_lines = [l for l in lines[1:8] if not contact_pattern.search(l)]
        summary_text = " ".join(prose_lines[:4])
        if len(summary_text) > 80:
            p.summary = self._make_fv(summary_text[:500], src, 0.55, summary_text)

        return p


class RecruiterNotesParser(SourceParser):
    """Free-text recruiter notes → partial CanonicalProfile."""

    def parse(self, text: str) -> CanonicalProfile:
        p = CanonicalProfile()
        src = SourceType.NOTES

        if not text:
            return p

        # Email
        email_m = _EMAIL_RE.search(text)
        if email_m:
            email, ec = normalize_email(email_m.group(0))
            p.email = self._make_fv(email, src, ec * 0.7, email_m.group(0))

        # Phone
        phone_m = _PHONE_RE.search(text)
        if phone_m:
            phone, pc = normalize_phone(phone_m.group(0))
            p.phone = self._make_fv(phone, src, pc * 0.7, phone_m.group(0))

        # Any mentioned company — capture up to 4 title-cased/short words, never crossing a period
        co_m = re.search(
            r"(?:works?\s+at|employed\s+at|from|company[:\s]+)\s+"
            r"([A-Z][\w&]*(?:\s+[A-Z&][\w&]*){0,3})(?=[\.,]|\s+(?:and|who|he|she|they)\b|$)",
            text,
        )
        if co_m:
            co = co_m.group(1).strip().rstrip(".,")
            p.current_company = self._make_fv(co, src, 0.45, co)

        # Name mention
        name_m = re.search(r"(?:candidate|name|applicant)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text)
        if name_m:
            name, nc = normalize_name(name_m.group(1))
            p.name = self._make_fv(name, src, nc * 0.6, name_m.group(1))

        # Skills/tech mentioned casually — capture comma/and-separated tech tokens up to sentence end
        skills_m = re.search(
            r"(?:knows?|familiar\s+with|proficient\s+in|experience\s+in|skilled?\s+in)\s+"
            r"([^\.]{2,120})",
            text, re.IGNORECASE
        )
        if skills_m:
            candidate_str = skills_m.group(1).strip()
            # Split on commas and standalone "and" (handles Oxford comma: "Python, ML, and AWS")
            tokens = re.split(r",\s*(?:and\s+)?|\s+and\s+", candidate_str)
            filler = {"well", "good", "very", "the", "he", "she", "they", "it"}
            tokens = [t.strip() for t in tokens if t.strip() and t.strip().lower() not in filler]
            if tokens:
                skills, sc = normalize_skills(tokens)
                if skills:
                    p.skills = self._make_fv(skills, src, sc * 0.5, candidate_str)

        return p


# ──────────────────────────────────────────────
# Merger / Conflict Resolver
# ──────────────────────────────────────────────

CANONICAL_FIELDS = [
    "name", "email", "phone", "current_company", "title",
    "location", "summary", "skills", "years_of_experience",
    "linkedin", "github", "website", "education", "languages", "top_repos",
]


def _merge_field(existing: Optional[FieldValue], incoming: Optional[FieldValue],
                 field_name: str, conflicts: list[dict]) -> Optional[FieldValue]:
    """
    Merge strategy:
    1. If incoming is empty/None, keep existing.
    2. If existing is None, take incoming.
    3. If same value, keep higher-confidence one.
    4. If different values: use SOURCE_PRIORITY + confidence to pick winner;
       log losing side as conflict.
    """
    if incoming is None:
        return existing
    if existing is None:
        return incoming

    # Normalise for comparison
    ev = str(existing.value).strip().lower()
    iv = str(incoming.value).strip().lower()

    if ev == iv:
        # Same value — keep the one with higher confidence
        return existing if existing.confidence >= incoming.confidence else incoming

    # Different values → conflict. Blend source trust and value confidence
    # instead of letting priority dominate outright — a low-confidence value
    # from a trusted source should not automatically beat a high-confidence,
    # more complete value from a less trusted source.
    ep = SOURCE_PRIORITY.get(existing.source, 0) / 100.0
    ip = SOURCE_PRIORITY.get(incoming.source, 0) / 100.0
    existing_score = 0.5 * ep + 0.5 * existing.confidence
    incoming_score = 0.5 * ip + 0.5 * incoming.confidence
    # Near-tie: prefer the more confident (i.e. more complete/reliable) value
    # rather than silently defaulting to whichever was processed first.
    if abs(existing_score - incoming_score) < 0.02:
        winner, loser = (existing, incoming) if existing.confidence >= incoming.confidence \
            else (incoming, existing)
    else:
        winner, loser = (existing, incoming) if existing_score > incoming_score else (incoming, existing)

    conflicts.append({
        "field": field_name,
        "winner": winner.to_dict(),
        "loser": loser.to_dict(),
        "reason": "source_priority+confidence",
    })
    return winner


def build_default_output_config() -> OutputConfig:
    fields = [
        FieldSpec(path="candidate_id", from_="candidate_id", type="string"),
        FieldSpec(path="name", from_="name", type="string"),
        FieldSpec(path="email", from_="email", type="string"),
        FieldSpec(path="phone", from_="phone", type="string"),
        FieldSpec(path="current_company", from_="current_company", type="string"),
        FieldSpec(path="title", from_="title", type="string"),
        FieldSpec(path="location", from_="location", type="string"),
        FieldSpec(path="summary", from_="summary", type="string"),
        FieldSpec(path="skills", from_="skills", type="string[]"),
        FieldSpec(path="years_of_experience", from_="years_of_experience", type="number"),
        FieldSpec(path="linkedin", from_="linkedin", type="string"),
        FieldSpec(path="github", from_="github", type="string"),
        FieldSpec(path="website", from_="website", type="string"),
        FieldSpec(path="education", from_="education", type="string"),
        FieldSpec(path="languages", from_="languages", type="string[]"),
        FieldSpec(path="top_repos", from_="top_repos", type="string[]"),
    ]
    return OutputConfig(fields=fields)


def _normalize_for_projection(value: Any, normalize: Optional[str]) -> Any:
    if value is None or not normalize:
        return value
    norm = normalize.lower()
    if norm == "e164" and isinstance(value, str):
        normalized, _ = normalize_phone(value)
        return normalized or value
    if norm == "canonical":
        if isinstance(value, str):
            normalized, _ = normalize_name(value)
            return normalized or value
        if isinstance(value, list):
            return [normalize_name(str(item))[0] if item is not None else item for item in value]
    if norm == "skills":
        if isinstance(value, (list, tuple, set)):
            normalized, _ = normalize_skills(list(value))
            return normalized
        normalized, _ = normalize_skills(value)
        return normalized
    return value


def _resolve_path_value(source: Any, path: str) -> Any:
    if not path:
        return source

    tokens = re.split(r"\.(?![^\[]*\])", path)

    def resolve_tokens(current: Any, remaining: list[str]) -> Any:
        if not remaining:
            return current
        if current is None:
            return None
        if isinstance(current, FieldValue):
            current = current.value
        token = remaining[0]
        if token.endswith("]"):
            base, index = token[:-1].split("[", 1)
            if base:
                if isinstance(current, dict):
                    current = current.get(base)
                else:
                    current = getattr(current, base, None)
            else:
                current = current
            if index == "":
                if not isinstance(current, list):
                    return None
                if len(remaining) == 1:
                    return current
                values = []
                for item in current:
                    resolved = resolve_tokens(item, remaining[1:])
                    if resolved is not None:
                        values.append(resolved)
                return values if values else None
            try:
                idx = int(index)
            except ValueError:
                return None
            if not isinstance(current, list):
                return None
            if 0 <= idx < len(current):
                return resolve_tokens(current[idx], remaining[1:])
            return None

        if isinstance(current, dict):
            current = current.get(token)
        else:
            current = getattr(current, token, None)
        return resolve_tokens(current, remaining[1:])

    return resolve_tokens(source, tokens)


def _serialize_field_value(value: Any, include_confidence: bool, include_provenance: bool) -> Any:
    if isinstance(value, FieldValue):
        payload: dict[str, Any] = {}
        if include_confidence:
            payload["confidence"] = round(value.confidence, 3)
        if include_provenance:
            payload["source"] = value.source.value
            payload["raw_value"] = value.raw_value
            payload["extracted_at"] = value.extracted_at
        if payload:
            payload["value"] = value.value
            return payload
        return value.value
    return value


def validate_projected_output(projected: dict, config: OutputConfig) -> dict:
    for field_spec in config.fields:
        if not field_spec.required:
            continue
        if field_spec.path in projected and projected.get(field_spec.path) is not None:
            continue
        if config.on_missing == "error":
            raise ProjectionError(f"Required field '{field_spec.path}' is missing")
    return projected


def project_profile(profile: CanonicalProfile, config: OutputConfig | dict | None) -> dict:
    if config is None:
        config = build_default_output_config()
    if isinstance(config, dict):
        config = OutputConfig(**config)

    projected: dict[str, Any] = {}
    for field_spec in config.fields:
        raw_value = _resolve_path_value(profile, field_spec.from_)
        if raw_value is None:
            if field_spec.required and config.on_missing == "error":
                raise ProjectionError(f"Required field '{field_spec.path}' is missing")
            if config.on_missing == "omit":
                continue
            projected[field_spec.path] = None
            continue

        resolved = _normalize_for_projection(raw_value, field_spec.normalize)
        projected[field_spec.path] = _serialize_field_value(
            resolved,
            include_confidence=config.include_confidence,
            include_provenance=config.include_provenance,
        )
    return validate_projected_output(projected, config)


def merge_profiles(profiles: list[CanonicalProfile]) -> CanonicalProfile:
    """Merge N partial profiles into one canonical profile."""
    merged = CanonicalProfile()
    merged.sources_used = list({p.sources_used[0] for p in profiles
                                 if p.sources_used}) if any(p.sources_used for p in profiles) else []

    for profile in profiles:
        for fname in CANONICAL_FIELDS:
            incoming: Optional[FieldValue] = getattr(profile, fname)
            existing: Optional[FieldValue] = getattr(merged, fname)
            result = _merge_field(existing, incoming, fname, merged.conflicts)
            setattr(merged, fname, result)

    # Compute overall confidence as avg of populated fields
    populated = [getattr(merged, f) for f in CANONICAL_FIELDS if getattr(merged, f)]
    if populated:
        merged.overall_confidence = sum(fv.confidence for fv in populated) / len(populated)

    # Generate stable candidate ID from email or name; fall back to a hash of all observed values.
    id_seed = ""
    if merged.email:
        id_seed = str(merged.email.value)
    elif merged.name:
        id_seed = str(merged.name.value)
    if not id_seed:
        values = []
        for profile in profiles:
            for fname in CANONICAL_FIELDS:
                fv = getattr(profile, fname, None)
                if fv is not None:
                    values.append(str(getattr(fv, "value", fv)))
        id_seed = "|".join(v for v in values if v)
    if id_seed:
        merged.candidate_id = "CAND_" + hashlib.sha256(id_seed.encode()).hexdigest()[:12].upper()
    else:
        merged.candidate_id = "CAND_UNKNOWN"

    return merged


# ──────────────────────────────────────────────
# Public Entry Point
# ──────────────────────────────────────────────

class CandidateTransformer:
    """
    Orchestrates all parsers and produces a single canonical profile.

    Usage:
        ct = CandidateTransformer()
        profile = ct.transform(
            csv_row={"name": "Jane Doe", "email": "jane@ex.com", ...},
            ats_blob={"full_name": "Jane Doe", "contact_email": "jane@ex.com", ...},
            github_data={...},          # GitHub REST API response + repos list
            resume_text="Jane Doe\n...",
            recruiter_notes="Candidate Jane is great at Python...",
        )
        print(profile.to_dict())
    """

    def __init__(self):
        self._csv_parser   = CSVParser()
        self._ats_parser   = ATSParser()
        self._gh_parser    = GitHubParser()
        self._resume_parser = ResumeParser()
        self._notes_parser = RecruiterNotesParser()

    def transform(
        self,
        csv_row: Optional[dict] = None,
        ats_blob: Optional[dict] = None,
        github_data: Optional[dict] = None,
        resume_text: Optional[str] = None,
        recruiter_notes: Optional[str] = None,
    ) -> CanonicalProfile:
        profiles: list[CanonicalProfile] = []

        if ats_blob:
            p = self._ats_parser.parse(ats_blob)
            p.sources_used = [SourceType.ATS.value]
            profiles.append(p)

        if csv_row:
            p = self._csv_parser.parse(csv_row)
            p.sources_used = [SourceType.CSV.value]
            profiles.append(p)

        if resume_text:
            p = self._resume_parser.parse(resume_text)
            p.sources_used = [SourceType.RESUME.value]
            profiles.append(p)

        if github_data:
            p = self._gh_parser.parse(github_data)
            p.sources_used = [SourceType.GITHUB.value]
            profiles.append(p)

        if recruiter_notes:
            p = self._notes_parser.parse(recruiter_notes)
            p.sources_used = [SourceType.NOTES.value]
            profiles.append(p)

        if not profiles:
            empty = CanonicalProfile()
            empty.candidate_id = "CAND_UNKNOWN"
            return empty

        merged = merge_profiles(profiles)
        merged.sources_used = [s for p in profiles for s in p.sources_used]
        return merged

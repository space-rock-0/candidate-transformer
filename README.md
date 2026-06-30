# CandidateTransformer

Eightfold ingests candidate information from many places at once. This service turns
those messy, conflicting inputs into one clean, canonical candidate profile — every
field carries its source and a confidence score, and nothing is silently guessed.

> Wrong-but-confident is worse than honestly-empty. If the data doesn't support a
> value, the field stays empty rather than being filled with a low-quality guess.

## What it does

CandidateTransformer ingests a candidate's data from up to five source types —
two structured, three unstructured — normalizes every field, deduplicates and
resolves conflicts across sources, and emits a single canonical profile with full
provenance:

| Group | Source | Notes |
|---|---|---|
| Structured | Recruiter CSV export | `name, email, phone, current_company, title` |
| Structured | ATS JSON blob | Arbitrary field names, remapped automatically |
| Unstructured | GitHub profile | Live REST API: bio, repos, languages |
| Unstructured | Resume (PDF / DOCX / text) | Regex + heuristic extraction |
| Unstructured | Recruiter notes (free text) | Lowest-trust, used to fill gaps only |

Every output field looks like this:

```json
{
  "value": "Siddhartha Sagi",
  "source": "ats_json",
  "confidence": 0.9,
  "raw_value": "Siddhartha Sagi",
  "extracted_at": "2026-06-30T03:34:30Z"
}
```

When two sources disagree, the merger picks a winner using a blend of **source
trust priority** and **value confidence** (not priority alone — a more complete,
higher-confidence value from a lower-priority source can still win), and the
losing value is kept in a `conflicts` array for audit, never silently discarded.

## Architecture

```
candidate-transformer/
├── backend/                  FastAPI service
│   ├── app/
│   │   ├── core/
│   │   │   └── transformer.py   Parsers, normalizers, merger — the core engine
│   │   └── main.py              REST API
│   ├── tests/
│   │   └── test_transformer.py  55 unit + integration tests
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                 React + Vite dashboard
│   ├── src/
│   │   ├── components/          SourceTimeline, FieldCard, StitchMeter, etc.
│   │   └── App.jsx
│   ├── nginx.conf
│   └── Dockerfile
├── docker-compose.yml
└── docs/
    └── CandidateTransformer_TechnicalDocumentation.docx
```

### Why this design

**Parser-per-source, single merger.** Each source type gets its own parser that
knows nothing about the others — `CSVParser`, `ATSParser`, `GitHubParser`,
`ResumeParser`, `RecruiterNotesParser`. Each emits a partial `CanonicalProfile`
with `FieldValue` objects carrying `(value, source, confidence, raw_value)`. A
single `merge_profiles()` function resolves all conflicts in one place — adding
a sixth source means writing one new parser, not touching merge logic.

**Confidence is computed at extraction time, not guessed at merge time.**
Normalizers (`normalize_email`, `normalize_phone`, etc.) return both a cleaned
value and a confidence score based on how well-formed the input was — a phone
number with a country code scores higher than a bare 10-digit number; an email
on a disposable domain scores lower than a corporate one. This is what lets the
merger make a principled trade-off instead of just trusting source rank blindly.

**Every conflict is logged, never silently dropped.** `CanonicalProfile.conflicts`
keeps the full losing `FieldValue` for every disputed field, so a recruiter or
downstream system can audit *why* a value was chosen.

## Running locally

### With Docker (recommended)

```bash
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Dashboard: http://localhost:5173

### Without Docker

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## API

### `POST /transform/json`

```bash
curl -X POST http://localhost:8000/transform/json \
  -H "Content-Type: application/json" \
  -d '{
    "csv_row": {"name": "Jane Doe", "email": "jane@corp.com", "phone": "9876543210"},
    "ats_blob": {"full_name": "Jane Doe", "employer": "Acme", "skills_list": ["Python"]},
    "github_url": "octocat",
    "resume_text": "Jane Doe\nSenior Engineer\njane@corp.com",
    "recruiter_notes": "Great candidate, knows Python and AWS."
  }'
```

### `POST /transform/multipart`

Same as above but accepts actual file uploads (`csv_file`, `resume_file`) plus
form fields for the rest.

### `POST /transform/batch`

Accepts an array of up to 50 candidate payloads, processed concurrently.

Full interactive docs are served at `/docs` (Swagger) and `/redoc`.

## Testing

```bash
cd backend
pytest tests/ -v
```

55 tests covering normalization edge cases, each parser independently, the
conflict-resolution merge logic, and full end-to-end multi-source transforms —
including a regression test for a real bug caught during manual stress-testing
(a more complete phone number losing to a less complete one purely on source
rank).

## Design notes — what "production-ready" meant here

- **No silent failures.** Missing, empty, or malformed sources never crash the
  pipeline — `transform()` accepts any subset of sources, including none.
- **Regex extraction is deliberately conservative.** Several extraction regexes
  (phone, company name, skills list) were tightened during development after
  stress-testing surfaced real over-matching bugs — see commit history in
  `transformer.py` comments for the reasoning.
- **CORS is open (`*`) for local development** — tighten this to specific
  origins before any production deployment.
- **GitHub API calls are unauthenticated** by default, which is rate-limited to
  60 requests/hour per IP. Add a `GITHUB_TOKEN` for production use (5,000/hour).

## Future enhancements

- LinkedIn parser (left unimplemented here since GitHub + resume + notes already
  satisfy the "at least one unstructured source" requirement; LinkedIn has no
  public API and would require a scraping or partner integration).
- Persistent storage (Postgres) for profile history and re-runs as new source
  data arrives over time.
- Active-learning loop: let recruiters confirm/reject merged conflicts, feeding
  corrections back into confidence weighting.
- Authentication and per-tenant source isolation.

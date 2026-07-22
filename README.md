# OT Prospector

A **compliance-first B2B prospecting tool** for finding the *conspicuously
published* business contact emails of **occupational therapy providers in
Queensland, Australia** — for legitimate outreach to clinics (software,
equipment, supplies, services, partnerships).

> ⚠️ **Read [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md) before you contact anyone.**
> Australia's **Spam Act 2003** and **Privacy Act 1988** govern how you may
> collect addresses and send mail. This tool is deliberately built to collect
> only public **business** contacts and to flag opt-out notices — but sending
> lawfully is your responsibility.

---

## What it does

- 🧑‍💼 **People Search (Apollo/RocketReach-style)** — enter **roles + industry + location** and it
  discovers matching companies, extracts **names & job titles** from their team pages, **infers each
  person's work email** from name+domain patterns, and **SMTP-verifies** it (with catch-all detection).
- 🔎 **Discovers** clinics/companies across a region (with a search API key).
- 🕸️ **Crawls** clinic websites politely (respects `robots.txt`, rate-limited) and
  extracts published emails from home / contact / about / team pages.
- 🧭 **Prefers role inboxes** (`info@`, `reception@`, `referrals@`) and flags
  personal, free-provider, and "no unsolicited contact" addresses.
- ✅ **Validates** emails (syntax + MX record) so you don't mail dead domains.
- ➕ **Enriches** per-domain contacts via Hunter.io (optional key).
- 📇 **Exports** a clean, de-duplicated CSV with a `source_url` for every record.

**What it does *not* do:** send email, bypass logins/paywalls, defeat
anti-bot protections, or scrape private/personal data. It is not a spam cannon.

---

## Requirements

- **Python 3.9+** (tested on 3.12). Get it from <https://python.org> or
  `winget install Python.Python.3.12`.
- Works with **zero API keys**. Optional keys unlock automated discovery and
  enrichment (see below).

## Install (Windows / PowerShell)

```powershell
git clone https://github.com/Draconius1984/prospecting.git
cd prospecting

python -m venv .venv
.\.venv\Scripts\Activate.ps1        # (macOS/Linux: source .venv/bin/activate)

pip install -r requirements.txt
```

## Configure (optional)

```powershell
Copy-Item config.example.env .env
# edit .env and add any keys you have — all are optional
```

---

## 🌐 Run it in your browser (localhost)

**Easiest: double-click `Start OT Prospector.bat`.** It launches the server and
opens your browser automatically. Close the window (or Ctrl+C) to stop.

Or from a terminal:
```powershell
.\.venv\Scripts\python.exe webapp\app.py
```
Either way it opens **http://localhost:5000** — a professional SaaS-style app with a sidebar:

- **People Search** — criteria form (roles / industry / location) → names, titles, and verified work
  emails in a sortable, filterable table with status badges, avatars, and CSV export.
- **Company Crawl** — paste company URLs → every published business email.
- **Saved Leads** — view/download `data/prospects.csv` in the browser.
- **Directories** — public sources to find company websites.
- A **Validate emails (MX)** toggle, per-row flags, and **Download CSV** / **Save to
  `data/prospects.csv`** buttons.

It binds to `127.0.0.1` (your machine only) and uses the exact same engine as the CLI.

---

## Usage (command line)

Every command: `python ot_prospector.py <command> -h` for options.

### 1. See the public directories to mine
```powershell
python ot_prospector.py sources
```

### 2. Crawl a list of clinic websites (no keys needed — the core workflow)
Point it at a CSV that has a `website` (or `source_url`) column, or a plain
`.txt` with one URL per line:
```powershell
python ot_prospector.py crawl --input data/prospects.csv --out data/crawled.csv
```

### 3. Discover clinics automatically (needs a search key)
```powershell
python ot_prospector.py discover --regions all --out data/discovered.csv
python ot_prospector.py discover --regions "Brisbane,Gold Coast" --per-query 10
```

### People Search — names, roles & work emails (the headline feature)
```powershell
python ot_prospector.py people --roles "occupational therapist,practice manager" `
  --industry "occupational therapy clinic" --location "Gold Coast QLD" --out data/people.csv
# or scan a list you already have (skips discovery):
python ot_prospector.py people --input companies.txt --roles "owner,director"
```
Flags: `--no-smtp` (skip live verification), `--hunter` (use Hunter.io if `HUNTER_API_KEY` set),
`--max-companies`, `--per-query`, `--max-pages`. Output includes `contact_name`, `title`,
`email`, `email_status` (verified/probable/accept_all/…), `email_pattern`, `seniority`.

### 4. Validate emails (syntax + MX)
```powershell
python ot_prospector.py validate --input data/crawled.csv --out data/validated.csv
```

### 5. Enrich by domain via Hunter.io (needs HUNTER_API_KEY)
```powershell
python ot_prospector.py enrich --input data/validated.csv --out data/enriched.csv
```

### 6. Merge + de-duplicate everything into a master list
```powershell
python ot_prospector.py dedupe --inputs data/crawled.csv data/enriched.csv --out data/master.csv
```

### Recommended end-to-end flow
```
discover (or hand-built site list) ──► crawl ──► validate ──► enrich ──► dedupe ──► master.csv
```

---

## Output columns

| Column | Meaning |
|--------|---------|
| `practice_name` | Business name (from the site's title/heading). |
| `contact_name` | Named individual, if known (mostly from enrichment). |
| `suburb`, `region` | Location. |
| `email` | The published address. |
| `email_type` | `generic` (role inbox) · `personal` (named) · `unknown`. |
| `phone` | Best AU phone found. |
| `website`, `source_url` | Where the practice / email was published (your evidence of conspicuous publication). |
| `services` | e.g. paediatric, NDIS, hand therapy, aged care. |
| `confidence` | `high` (fetched the page) · `medium` · `low`. |
| `status` | `crawled` · `validated` · `enriched` · **`flagged`** (do not use). |
| `mx_ok` | `yes` / `no` / `unknown` (domain can receive mail?). |
| `notes` | Warnings — e.g. *"PAGE REQUESTS NO UNSOLICITED CONTACT"*, free-provider mailbox. |

**Exclude every row where `status = flagged`** before any outreach.

---

## Which paid service should I add? (you asked for recommendations)

The tool is free/public-web-first. If you want more coverage or speed, add one:

| Need | Service | Rough cost | Why |
|------|---------|-----------|-----|
| **Automated discovery** (find the clinic sites for you) | **SerpAPI** | Free 100/mo · ~US$75/mo for 5k | Easiest drop-in; wired into `discover`. |
| Cheaper discovery at volume | **Google Programmable Search** | 100/day free · US$5/1,000 | Slightly fiddlier setup, best value. |
| **Find named-staff emails per clinic** | **Hunter.io** | Free 25/mo · from ~US$34/mo | Wired into `enrich`; good for `firstname@`. |
| Bulk enrichment + verification | **Apollo.io / Clearout / NeverBounce** | Varies | Larger lists; verify deliverability before send. |

You can start with **zero** paid services: mine the [directories](docs/SOURCES.md)
by hand into a URL list, then `crawl`.

---

## Project structure

```
prospecting/
├─ ot_prospector.py          # CLI entry point
├─ webapp/                   # local browser UI (Flask)
│  ├─ app.py                 # server: /api/crawl, /api/discover, /api/jobs/...
│  └─ templates/index.html   # single-page UI (no external assets)
├─ prospector/               # the shared package
│  ├─ pipeline.py            # the engine both front-ends call
│  ├─ sources.py             # QLD regions, directories, query builder
│  ├─ search.py              # SerpAPI / Google CSE / Bing adapters
│  ├─ crawler.py             # polite, robots-aware crawler
│  ├─ extract.py             # email / phone / name extraction
│  ├─ compliance.py          # business-email filters & opt-out detection
│  ├─ validate.py            # syntax + MX validation
│  ├─ enrich.py              # Hunter.io domain search
│  └─ models.py              # Prospect record + CSV schema
├─ data/
│  └─ seeds_qld_ot.csv       # curated public directories (committed)
│                            # your prospect CSVs stay here, git-ignored
├─ docs/
│  ├─ COMPLIANCE.md          # ⚠️ read this
│  └─ SOURCES.md             # research methodology + directory catalogue
├─ tests/
├─ requirements.txt
└─ config.example.env
```

---

## Disclaimer

This software is provided under the MIT licence for lawful B2B research only. It
does not send messages and grants no right to breach the Privacy Act 1988 or
Spam Act 2003. You are responsible for how you collect and use contact data.
Not legal advice.

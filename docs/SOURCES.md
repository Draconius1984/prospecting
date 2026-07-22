# Sources & methodology

How to find occupational-therapy providers in Queensland and where their
**conspicuously published business** contact details live.

## Method (what this tool automates)

1. **Enumerate** OT providers by region (Brisbane, Gold Coast, Sunshine Coast,
   Ipswich, Logan/Redlands, Moreton Bay, Toowoomba/Darling Downs, Cairns/FNQ,
   Townsville/NQ, Mackay, Central QLD, Wide Bay) and by niche (paediatric, NDIS,
   hand therapy, aged care, driving assessment).
2. **Collect** each provider's public website.
3. **Extract** the business email from its home / contact / about / team pages
   (the pages where clinics *intend* the public to reach them).
4. **Record** the `source_url` so you can evidence conspicuous publication.
5. **Validate** the address (syntax + MX) and **de-duplicate**.

## Primary directories (public)

| Source | Type | Notes |
|--------|------|-------|
| [OT Australia — Find an OT](https://otaus.com.au/find-an-ot) | Peak-body directory | Filter by QLD suburb/postcode. |
| [AHPRA Register of Practitioners](https://www.ahpra.gov.au/registration/registers-of-practitioners.aspx) | Regulator register | Verify registration; no emails. |
| [NDIS Provider Finder](https://www.ndis.gov.au/participants/working-providers/find-registered-provider/provider-finder) | Government | Registration group *Occupational Therapy* + QLD. |
| [Healthdirect Service Finder](https://www.healthdirect.gov.au/australian-health-services) | Government | Search "occupational therapy" by suburb. |
| [HealthEngine](https://healthengine.com.au/find/occupational-therapy/qld) | Health directory | Booking listings with contact info. |
| [Cylex](https://www.cylex-australia.com/s/occupational-therapist/queensland) · [Yellow Pages](https://www.yellowpages.com.au/search/listings?clue=occupational+therapist&locationClue=QLD) | Business directories | Often list email + phone directly. |
| [Halaxy directory](https://www.halaxy.com/search?type=occupational-therapist&location=Queensland) | Booking platform | Public practitioner profiles. |
| [Queensland Health – Find us](https://www.health.qld.gov.au/services/findus) | Public health | Hospital/community allied-health OT departments. |

These are also in [`data/seeds_qld_ot.csv`](../data/seeds_qld_ot.csv) and printed by
`python ot_prospector.py sources`.

## Search-query grid

`prospector/sources.py` builds queries as *term × region*, e.g.:

- `occupational therapist contact email "Gold Coast" Queensland`
- `paediatric occupational therapist "Cairns & Far North" Queensland`
- `NDIS occupational therapy provider "Toowoomba & Darling Downs" Queensland`

Feed these into a search API (`discover`) or paste them into a browser and
collect the resulting clinic websites into a `.txt` for `crawl`.

## Seed research data

An initial batch of real QLD OT providers gathered for this project is written
to **`data/prospects.csv`** (kept **local / git-ignored** because it contains
personal information — see [`COMPLIANCE.md`](COMPLIANCE.md)). Treat it as a
starting point: run `validate` before using it, and always keep the
`source_url` with each record.

## A note on directories vs. clinic sites

The crawler deliberately **skips** aggregator/social domains (Facebook,
LinkedIn, Yellow Pages, HealthEngine, NDIS, AHPRA, etc.) when extracting emails
— those pages publish the *directory's* address, not the clinic's. Use
directories to **find clinic websites**, then crawl the **clinic's own site**
for its published address.

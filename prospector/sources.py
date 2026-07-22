"""
Queensland-specific source catalog and search-query builders.

CURATED_SOURCES are public directories/registers you can mine by hand or feed
into the crawler. QLD_REGIONS x SEARCH_TERMS produces the query grid used by
the `discover` command when a search provider is configured.
"""

from __future__ import annotations

from typing import Dict, List

# Public directories & registers where QLD OTs conspicuously publish contacts.
CURATED_SOURCES: List[Dict[str, str]] = [
    {
        "name": "Occupational Therapy Australia — Find an OT",
        "url": "https://otaus.com.au/find-an-ot",
        "type": "professional_directory",
        "note": "Peak body directory; filter by QLD postcode/suburb.",
    },
    {
        "name": "AHPRA — Register of Practitioners (OT Board)",
        "url": "https://www.ahpra.gov.au/registration/registers-of-practitioners.aspx",
        "type": "regulator_register",
        "note": "Confirms registration; does not publish emails, use for verification.",
    },
    {
        "name": "NDIS Provider Finder",
        "url": "https://www.ndis.gov.au/participants/working-providers/find-registered-provider/provider-finder",
        "type": "government_directory",
        "note": "Filter registration group 'Occupational Therapy' + QLD region.",
    },
    {
        "name": "Healthdirect — Service Finder",
        "url": "https://www.healthdirect.gov.au/australian-health-services",
        "type": "government_directory",
        "note": "Search 'occupational therapy' by QLD suburb/postcode.",
    },
    {
        "name": "HealthEngine",
        "url": "https://healthengine.com.au/find/occupational-therapy/qld",
        "type": "health_directory",
        "note": "Booking directory; many clinics list contact details.",
    },
    {
        "name": "Cylex Australia",
        "url": "https://www.cylex-australia.com/s/occupational-therapist/queensland",
        "type": "business_directory",
        "note": "Business listings often include email + phone.",
    },
    {
        "name": "Yellow Pages Australia",
        "url": "https://www.yellowpages.com.au/search/listings?clue=occupational+therapist&locationClue=QLD",
        "type": "business_directory",
        "note": "Classic directory; email shown on many profiles.",
    },
    {
        "name": "Yelp — Occupational Therapy Queensland",
        "url": "https://www.yelp.com.au/search?find_desc=Occupational+Therapy&find_loc=Queensland",
        "type": "review_directory",
        "note": "Links through to clinic websites.",
    },
    {
        "name": "Halaxy practitioner directory",
        "url": "https://www.halaxy.com/search?type=occupational-therapist&location=Queensland",
        "type": "booking_directory",
        "note": "Practice-management platform's public directory.",
    },
    {
        "name": "Queensland Health — hospital & health services",
        "url": "https://www.health.qld.gov.au/services/findus",
        "type": "public_health",
        "note": "Public allied-health / OT departments (general enquiry lines).",
    },
]

# Queensland regions with representative suburbs, used to build local queries.
QLD_REGIONS: List[Dict[str, str]] = [
    {"region": "Brisbane", "hubs": "Brisbane CBD, Chermside, Sunnybank, Indooroopilly"},
    {"region": "Gold Coast", "hubs": "Southport, Robina, Burleigh Heads, Coomera"},
    {"region": "Sunshine Coast", "hubs": "Maroochydore, Caloundra, Noosa, Nambour"},
    {"region": "Ipswich & West Moreton", "hubs": "Ipswich, Springfield Lakes, Goodna"},
    {"region": "Logan & Redlands", "hubs": "Springwood, Cleveland, Capalaba"},
    {"region": "Moreton Bay", "hubs": "Caboolture, Redcliffe, Strathpine"},
    {"region": "Toowoomba & Darling Downs", "hubs": "Toowoomba, Highfields, Warwick"},
    {"region": "Cairns & Far North", "hubs": "Cairns, Smithfield, Edmonton"},
    {"region": "Townsville & North", "hubs": "Townsville, Kirwan, Thuringowa"},
    {"region": "Mackay & Whitsundays", "hubs": "Mackay, Proserpine"},
    {"region": "Central Queensland", "hubs": "Rockhampton, Gladstone, Emerald"},
    {"region": "Wide Bay", "hubs": "Bundaberg, Hervey Bay, Maryborough"},
]

# Search terms combined with each region to build discovery queries.
SEARCH_TERMS: List[str] = [
    "occupational therapist contact email",
    "occupational therapy clinic",
    "paediatric occupational therapist",
    "NDIS occupational therapy provider",
    "hand therapy occupational therapist",
    "occupational therapy private practice",
]


def build_queries(regions: List[Dict[str, str]] = None, terms: List[str] = None) -> List[str]:
    regions = regions or QLD_REGIONS
    terms = terms or SEARCH_TERMS
    queries: List[str] = []
    for r in regions:
        for t in terms:
            queries.append(f'{t} "{r["region"]}" Queensland')
    return queries

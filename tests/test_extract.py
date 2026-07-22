"""
Unit tests for extraction + compliance logic (no network required).

Run:  python -m pytest -q        (or)   python tests/test_extract.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prospector.compliance import (  # noqa: E402
    classify_email,
    is_collectable_business_email,
    looks_like_system_email,
    page_forbids_unsolicited,
)
from prospector.extract import (  # noqa: E402
    deobfuscate,
    extract_emails,
    extract_phones,
)


def test_extract_plain_email():
    emails = extract_emails("Contact us at info@brisbaneot.com.au today.")
    assert "info@brisbaneot.com.au" in emails


def test_deobfuscation():
    text = "reception [at] goldcoastot [dot] com [dot] au"
    assert "reception@goldcoastot.com.au" in extract_emails(deobfuscate(text))


def test_system_and_asset_emails_rejected():
    assert looks_like_system_email("logo@2x.png")
    assert looks_like_system_email("noreply@mailer.example.com")
    assert not is_collectable_business_email("sentry@sentry.io")
    assert is_collectable_business_email("admin@cairnstherapy.com.au")


def test_classify_email():
    assert classify_email("info@clinic.com.au") == "generic"
    assert classify_email("jane.smith@clinic.com.au") == "personal"


def test_phone_extraction():
    phones = extract_phones("Call us on 07 3211 4567 or 0412 345 678.")
    assert any("3211" in p for p in phones)
    assert any("0412" in p for p in phones)


def test_no_unsolicited_flag():
    assert page_forbids_unsolicited("We do not accept unsolicited marketing emails.")
    assert not page_forbids_unsolicited("Welcome to our friendly OT clinic.")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")

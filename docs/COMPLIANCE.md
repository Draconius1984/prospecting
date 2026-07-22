# Compliance guide — cold B2B email in Australia

> **This is a practical guide, not legal advice.** For anything material, confirm
> with a lawyer or check the primary sources: the **Spam Act 2003**, the
> **Privacy Act 1988** (Australian Privacy Principles), and current
> [ACMA](https://www.acma.gov.au) / [OAIC](https://www.oaic.gov.au) guidance.

You are doing B2B outreach: selling products/services to occupational-therapy
**practices**. That is a legitimate, common activity — but three laws shape how
you may gather addresses and send mail. This tool is built to keep you on the
right side of them.

---

## 1. Spam Act 2003 — the one that governs sending

Any "commercial electronic message" with an Australian link must satisfy **three**
rules:

| Rule | What it means for you |
|------|-----------------------|
| **Consent** | You need express or *inferred* consent (see below). |
| **Identify** | Every message clearly says who you are + how to contact you. |
| **Unsubscribe** | A working, free, obvious opt-out honoured within 5 business days (keep it live ≥30 days). |

### Inferred consent — the lawful basis for cold B2B email
You may **infer** consent when **all** of these hold:

1. The email address was **conspicuously published** (e.g. on the clinic's
   public website / a business directory) — *not* behind a login or scraped from
   a private source.
2. The publication was **not** accompanied by a statement like *"no unsolicited
   commercial messages"*.
3. Your message is **directly relevant to the role/business** of the address
   holder (e.g. emailing a clinic's `info@` about clinic software or supplies).

➡️ **This is exactly what OT Prospector collects for**: conspicuously-published
**business** addresses, with the `notes` column flagging any page that says "no
unsolicited contact" so you can exclude it. Prefer role inboxes
(`info@`, `reception@`, `referrals@`) — they're the clearest fit for inferred
consent.

### The address-harvesting prohibition (read this)
The Spam Act **prohibits using address-harvesting software or a harvested-address
list to send unsolicited commercial electronic messages.** In plain terms:

- ✅ Collecting a **conspicuously-published business address** and sending a
  **relevant** message for which consent can be **inferred** is fine.
- ❌ Indiscriminately scraping every address you can find and blasting
  unsolicited mail to them is **not** — that is the harvesting scenario the Act
  targets.

Use this tool for the first case, never the second. Keep the `source_url` for
every address (the tool stores it) so you can show *where* it was published.

---

## 2. Privacy Act 1988 — the one that governs the data

A named person's work email (e.g. `jane.smith@clinic.com.au`) is **personal
information**. If the Act applies to you (generally businesses with >A$3M annual
turnover, plus all health-service providers and a few other categories), the
Australian Privacy Principles require you to:

- **APP 3** — only collect what's reasonably necessary for your function.
- **APP 5** — take reasonable steps to notify people you've collected their info
  (a privacy statement in your first email + a linked privacy policy usually
  covers this).
- **APP 7** — for direct marketing, always offer a simple opt-out and stop when
  asked.
- **APP 10/11** — keep it accurate and hold it securely; delete when no longer
  needed.

Even under the small-business exemption, following these is good practice and
builds trust with clinicians.

---

## 3. A practical pre-send checklist

- [ ] Address came from a **public business** source (`source_url` recorded).
- [ ] It's a **business/role** inbox where possible (`email_type = generic`).
- [ ] The source page did **not** say "no unsolicited contact"
      (rows flagged `status = flagged` are excluded).
- [ ] Message is **relevant to the clinic's work**.
- [ ] Every email **identifies you** (name, business, ABN, contact details).
- [ ] Every email has a **one-click unsubscribe** that actually works.
- [ ] You have a **privacy statement / policy** linked.
- [ ] You **suppress** anyone who unsubscribes — permanently.
- [ ] You do **not** email addresses with **no MX record** (`mx_ok = no`).

---

## 4. How the tool helps you comply

| Feature | Compliance purpose |
|---------|--------------------|
| Respects `robots.txt`, rate-limited | Access sites politely; don't hammer servers. |
| Only home + contact/about/team pages | Targets *conspicuously published* contacts. |
| `notes` flags "no unsolicited contact" pages | Lets you exclude opt-out sites. |
| Prefers role inboxes; flags free-mailbox & personal | Steer toward inferred-consent-friendly addresses. |
| Stores `source_url` for every record | Evidence of conspicuous publication. |
| `.gitignore` keeps `data/*.csv` out of git | Avoid publishing personal info by accident. |
| MX validation | Avoid mailing dead domains. |

**Sending is still your responsibility.** This tool gathers and organises
publicly-published business contacts; it does not send mail. Pair it with a
reputable email platform that provides compliant unsubscribe handling.

---

## 5. Aggressive discovery — what the tool does and does NOT do

"Deep search" widens collection to more **public** channels. Everything used is
public web pages, public archives, public DNS/SMTP, or licensed APIs:

| Channel | What it is |
|---------|-----------|
| Company website crawl | The org's own published emails (incl. Cloudflare-obfuscated). |
| Search-engine dorking | `site:`/`filetype:`/`intext:` operators via a **licensed SERP API** (never raw Google scraping). |
| Wayback Machine | Emails archived on old public contact/team pages. |
| MX + SMTP RCPT probe | Public mail-server responses; **no message is ever sent**. |
| Email-pattern inference | Pure math on a name + domain. |

**Deliberately NOT implemented (illegal / high-risk — the research flagged these):**

- ❌ **Breached-credential / combolist dumps** (DeHashed-style, "Collection #1"). Unlawful processing; operators have been arrested.
- ❌ **Authenticated LinkedIn / social scraping**, fake accounts, or login/rate-limit bypass (CFAA/ToS/trespass exposure).
- ❌ **Microsoft 365 login enumeration** (GetCredentialType / Autodiscover) — account-enumeration used in phishing recon.
- ❌ **Raw Google/Bing scraping via captcha-evading proxies** (ToS violation).
- ❌ **SMTP `VRFY`/`EXPN`** and **send-and-monitor bounce testing** (emailing real people to read bounces).

If you ever want one of these, the answer is no — they create legal liability
and get your domain/IP blacklisted.

**Verification infrastructure note.** Live SMTP verification only works well from
a host with **outbound port 25 open** and correct **PTR/rDNS + HELO + SPF**
alignment — i.e. a VPS, not a home PC (residential ISPs block port 25). On your
PC, found emails will read **"Probable/Unverified"**; that's expected. Google
Workspace / Microsoft 365 domains often "accept-all", so a 250 there is weak —
the tool marks those and leans on pattern-inference confidence instead.

**Personal data.** A named person's work email is personal data under GDPR/CCPA
even when public. Honour opt-outs and takedown requests, keep a do-not-contact
suppression list, and don't bulk-resell harvested data.

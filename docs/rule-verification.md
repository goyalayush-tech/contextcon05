# Rule verification record

Checked on 2026-11-22. The rights engine (`flightback/rules.py`) encodes only what is listed here as verified.

## DGCA CAR Section 3, Series M, Part IV (cancellation and delay) — VERIFIED

- Source: https://www.dgca.gov.in/digigov-portal/Upload?flag=iframeAttachView&attachId=we1PSlOuQhYdHcwKKrm7ew%3D%3D
- File: `D3M-M4(R4_Jan2023).pdf`, 8 pages, footer "Rev. 4, dated 25th Jan, 2023", header "Effective: 15th February 2023"
- SHA-256 of the file as retrieved: `3b4b50844edc6a46099cce3b94626d29b03f90ccc61318aa1aa2db6d0fa3ff4a`
- Read paragraph by paragraph: 1.4, 1.5, 3.3.1-3.3.5, 3.4.1-3.4.5, 3.8.1, 3.9.1-3.9.3, 3.10.4.
- Corrections made to the product spec while encoding:
  - In the two-weeks-to-24-hours window, 3.3.1 only requires an alternate-flight or refund *offer*. Compensation therefore
    depends on whether that offer was made, not on notice time alone.
  - Para 1.5 lists ATC decisions, meteorological conditions and security risks as extraordinary circumstances.
  - Part IV has no cash-compensation formula for delays. The engine never promises one.

## DGCA CAR Section 3, Series M, Part II (refunds) — NOT VERIFIED

- The only Part II retrieved from dgca.gov.in is an older version (header "Feb 2019"): 21 working days for agent/portal refunds,
  look-in barred inside 5 days. Not the Rev. 3 of 24 Feb 2026.
- Unchanged and present in the older text: 7 days for credit card; immediate for cash; statutory taxes and UDF/ADF/PSF
  refundable on all fares; credit shell is the passenger's choice; cancellation charge capped at basic fare plus fuel
  surcharge; no charge to process a refund; foreign carriers follow their home regulations.
- Figures taken from news reports of the 2026 revision only (not primary text): 14 working days; 7-day (domestic) and
  15-day (international) look-in minimum; effective 26 March 2026.
- Every refund assessment carries this warning. Replace with the primary text before relying on those figures.

## Crustdata behaviour observed while verifying

- Web Fetch returned HTTP 200 with empty content for the CAR PDF, with and without browser-like mode. The rule text was
  therefore read from a direct download, not through Crustdata.
- Web Search ignored the `site:` restriction and returned redirect links, so official pages are found by known domain, not search.
- Company Identify by domain resolved IndiGo, Air India and Akasa Air at confidence 1.0.

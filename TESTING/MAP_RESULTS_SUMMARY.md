# Firecrawl MAP Endpoint Test Results
**Site:** https://phccconnect2025.eventscribe.net/
**Date:** 2025-10-29

## Summary

Ran MAP endpoint on 6 URLs. Most pages only return 1 link (themselves), but the home page returned 7 links total.

**Key Finding:** The exhibitors page shows "85 results found" but MAP only returns the page itself. We'll need to use CRAWL or SCRAPE endpoint to extract the actual exhibitor data.

---

## 1. Home Page
**URL:** https://phccconnect2025.eventscribe.net
**Links Found:** 7

```
1. https://phccconnect2025.eventscribe.net/sitemap.xml (404 Not Found)
2. https://phccconnect2025.eventscribe.net (Home)
3. https://phccconnect2025.eventscribe.net/SearchByExpoCompany.asp (Exhibitors - 85 results)
4. https://phccconnect2025.eventscribe.net/aaStatic.asp (Companion Experience)
5. https://phccconnect2025.eventscribe.net/ajaxcalls/ExhibitorInfo.asp (Exhibitor Info)
6. https://phccconnect2025.eventscribe.net/agenda.asp (Full Schedule)
7. https://phccconnect2025.eventscribe.net/login.asp (Login)
```

---

## 2. Exhibitors Page
**URL:** https://phccconnect2025.eventscribe.net/SearchByExpoCompany.asp
**Links Found:** 1
**Warning:** "Only 1 result(s) found. For broader coverage, try mapping the base domain: eventscribe.net"

**Description:** Lists 85 exhibitors including:
- Mueller Streamline Co.
- National Energy & Fuels Institute
- Navien, Inc.
- NIBCO
- Norgas Controls, Inc.
- Sioux Chief

**Note:** MAP doesn't discover individual exhibitor pages. Need to SCRAPE this page.

---

## 3. Companion Experience Page
**URL:** https://phccconnect2025.eventscribe.net/aaStatic.asp
**Links Found:** 1
**Warning:** "Only 1 result(s) found. For broader coverage, try mapping the base domain: eventscribe.net"

**Description:** Cultural excursions and networking activities

---

## 4. Exhibitor Info Page
**URL:** https://phccconnect2025.eventscribe.net/ajaxcalls/ExhibitorInfo.asp
**Links Found:** 1
**Warning:** "Only 1 result(s) found. For broader coverage, try mapping the base domain: eventscribe.net"

**Description:** Details about Legend Valve and other exhibitors

---

## 5. Schedule Page
**URL:** https://phccconnect2025.eventscribe.net/agenda.asp
**Links Found:** 1
**Warning:** "Only 1 result(s) found. For broader coverage, try mapping the base domain: eventscribe.net"

**Description:** Full event schedule starting October 26, 2025

---

## 6. Login Page
**URL:** https://phccconnect2025.eventscribe.net/login.asp
**Links Found:** 1
**Warning:** "Only 1 result(s) found. For broader coverage, try mapping the base domain: eventscribe.net"

**Description:** Access key login

---

## Next Steps

1. **Use SCRAPE endpoint** on the Exhibitors page to extract the 85 exhibitor listings
2. **Use CRAWL endpoint** to discover and scrape all exhibitor detail pages
3. Consider mapping the base domain `eventscribe.net` for broader coverage

## Files Created
- `TESTING/map_1_home.json` (1.9KB)
- `TESTING/map_2_exhibitors.json` (462B)
- `TESTING/map_3_companion.json` (457B)
- `TESTING/map_4_exhibitorinfo.json` (463B)
- `TESTING/map_5_schedule.json` (457B)
- `TESTING/map_6_login.json` (438B)
- `TESTING/run_maps.sh` (script used)

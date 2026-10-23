# 0037. Credit wording for each data source, and how far each licence has been checked

- Status: Accepted. Two credit items are flagged as unverified; the page wording is decided here (OQ-22)
- Date: Oct 9, 2026
- Source: Open question OQ-22. Each licence was read from the provider's primary page where one could be reached. Secondary sources are marked as such.

## Context

The page and the README must credit each source. The credit must match the licence, and some licences require exact wording. OQ-22 asked for the terms and the credit text for CelesTrak, FCC, NPS and OpenCelliD, and for the wording that says coverage is a map claim. Two of the primary pages could not be read from the build environment (HTTP 403), so those entries say so.

## Decision

### Verified from the primary licence or page

- **Copernicus GLO-30 (licence for COP-DEM-GLO-30-F, Articles 5 and 6).** The licence is free of charge. Public notice, for unmodified data: "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved." Our horizons are derived, so the notice for modified data applies: "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved." When the data are distributed to the public, the licence also requires this statement: the organisations in charge of the Copernicus programme do not incur liability for any use of the data. Article 6(c) gives the wording.
- **NPS.** Material created by the NPS is generally in the public domain unless marked otherwise. Credit is appreciated and is not required. The NPS Arrowhead symbol must not be used. Some content carries third-party rights. Credit used: "Trail data: National Park Service."

### Taken from secondary sources, to confirm before the page goes live

- **U.S. Census Bureau, TIGER/Line.** Declared CC0 (public domain) on data.gov. Some files carry a rights flag, "otherRestrictions", whose meaning is not stated. Confirm on the Census page for the exact vintage (first-run check, ADR 0035). Credit used: "Road data: U.S. Census Bureau, TIGER/Line."
- **OpenCelliD.** The licence is CC BY-SA 4.0 according to secondary sources. The OpenCelliD site returned HTTP 403, so the attribution page could not be read. Credit used: "Cell tower locations: OpenCelliD (opencellid.org), licensed CC BY-SA 4.0." Share-alike applies to the derived data (ADR 0024). **Unverified:** the exact credit text and terms, to read before publishing.
- **FCC mobile coverage.** Secondary sources report that the FCC asks for credit as a courtesy, not as a legal condition. The FCC broadband map page returned HTTP 403, so its terms could not be read. The carrier submissions behind the mobile map may carry their own restrictions. Credit used: "Coverage data: FCC National Broadband Map (broadbandmap.fcc.gov)." **Unverified:** the terms for carrier-level mobile data, to read before the Phase B coverage is published.

### No terms found

- **CelesTrak.** No usage, terms or credit requirement was found on the CelesTrak webmaster page. Credit used, as a courtesy: "Orbital data: CelesTrak (celestrak.org), maintained by Dr. T.S. Kelso." The project publishes derived satellite windows, not the raw element sets. Before any raw element sets are republished, the maintainer is asked directly through the site.

### Ookla

- Unchanged. The exact notice in ADR 0013 applies.

### Page wording: coverage is a claim, and satellite texts are not guaranteed

- Shown on the trail page, next to the coverage strip: "Coverage shown is the FCC's modelled claim, not a measurement. Satellite texts are not guaranteed: they need T-Mobile service and a supported phone, and they can fail under cover that the terrain model does not show."
- The wording states the limits that the design already records. It is not a promise about any single message.

## Alternatives considered

- Paraphrased credits. Rejected: the Copernicus licence gives exact wording, and it is used as written.
- Leaving the credits until the page is built. Rejected: the credit text is part of the acceptance check AC-1B.1 and the page's review.

## Consequences

- Three entries (OpenCelliD, FCC mobile data, the Census rights flag) must be checked before publishing. They are listed as open first-run checks in the platform and security documents.
- The credit lines are the wording used on the page and in the README.

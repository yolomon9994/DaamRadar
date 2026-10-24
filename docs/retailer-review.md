# Retailer access investigation

Initial review: 18 October 2026; reliability follow-up: 20 October; pantry expansion: 24 October 2026. These are point-in-time observations from this environment. Public crawler rules and technical reachability do not establish a general license to reuse a website or its contents. The current collector is a small, manually invoked prototype that records factual product/offer fields only.

## Initial observations

Three real observations were imported through the tested Jalal Sons collector:

| Public product page | Listed PKR price when checked |
| --- | --- |
| [Olpers Milk 1Ltr](https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398) | 350.00 |
| [Olpers Milk 1.5Ltr](https://www.jalalsons.com.pk/product/olpers-milk-15ltr-2809399) | 518.00 |
| [Nestle Everyday Milk 180Ml](https://www.jalalsons.com.pk/product/nestle-everyday-milk-180ml-2809387) | 44.00 |

Each page reported `InStock` in its public JSON-LD. Exact check times are stored in the local database. These are dated observations, not guaranteed current prices or delivery quotes. No branch/location was selected; every record says delivery area is unverified.

An intermediate two-product attempt on 18 October timed out and is recorded as blocked under the original error model. A later manual invocation with the same identity completed those pages. On 20 October, run #5 refreshed all three existing records in four HTTP requests; prices were unchanged, and each listing now has two real observations. The updated client permits at most one delayed retry for timeout exceptions only. Access denials and HTTP errors never retry. See the [collection runbook](collection-workflow.md).

## Second-source follow-up, 20 October 2026

- **Cartpk:** [robots](https://www.cartpk.com/robots.txt) permits ordinary public product paths and specifies a five-second delay. The canonical [terms page](https://www.cartpk.com/terms-conditions) covers delivery/refunds and did not state an explicit factual-price scraping prohibition; no general reuse license is claimed. Initial product inspection found undecodable JSON-LD and one follow-up encountered `ConnectionError`. Further inspection with the unchanged named crawler identified the cause: an invalid `\&#039;` escape in an authored description. The public [Olper's 1L page](https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr) independently contains one scoped final-price field (360), visible price `Rs 360.00`, duplicate agreeing numeric price metadata, explicit PKR currency metadata, and one `In stock` label. A strict DOM adapter now uses only those factual fields, without repairing JSON-LD or copying descriptions/images. It is limited to this exact URL and rejects variant controls, incompatible titles, mismatching metadata, and ambiguous prices. Run #6 imported one real PKR 360 observation in two HTTP requests on 20 October and linked it to the existing Jalal Sons 1L product. One successful import does not establish sustained reliability or broader permitted reuse.
- **Olpers Mart:** public robots and homepage were accessible and contained exact product links. Its [terms](https://olpersmart.pk/terms-and-condition) include restrictions on business use and third-party use/notification, as well as website-material reuse. No product collector was enabled and no price records were imported. Clarify the applicable access/reuse basis before pursuing this source.

The first real listed-price comparison is now available: Jalal Sons PKR 350 (checked 22:49 PKT) and Cartpk PKR 360 (checked 23:04 PKT), both on 20 October 2026. Both titles normalize to single 1L full-cream milk, and the existing matcher linked them without manual reassignment. Delivery areas remain unverified; no winning-retailer badge or savings claim is shown. Naheed's denied collector was not retried or given a different identity. Springs, Al-Fatah, and Olpers Mart remain disabled.

| Source | Actual observations | Current decision |
| --- | --- | --- |
| [Jalal Sons](https://www.jalalsons.com.pk/) | Direct identified requests retrieved [robots.txt](https://www.jalalsons.com.pk/robots.txt), [terms](https://www.jalalsons.com.pk/terms-and-conditions), and product HTML. Robots excludes `/api/*`, checkout and account routes; public `/product/...` paths are not excluded. Reviewed terms cover ordering/delivery and did not state an explicit product-price scraping ban. | Limited manual factual-price adapter enabled locally. Nine distinct live listings after the milk and pantry expansions below, all using explicit PKR JSON-LD offers. Delivery area unverified; no bulk-republication license claimed. |
| [Cartpk](https://www.cartpk.com/) | Public robots, canonical terms, and five milk pages reviewed on 20 October, plus three pantry pages on 24 October. Five-second crawl delay. Malformed description JSON-LD is unused; scoped final prices and PKR metadata agree. | Manual DOM adapter accepts eight reviewed URL/title pairs. Eight live listings match Jalal Sons canonical products. A partial run's connection failure and separate recovery are documented below. Delivery area unverified; no general reuse agreement claimed. |
| [Naheed](https://www.naheed.pk/) | The initial web-fetch-tool request returned 403. A later identified review request retrieved [robots](https://www.naheed.pk/robots.txt), [terms](https://www.naheed.pk/terms-and-conditions), and an Olper's product page. The actual `DaamRadarBot` collector then returned 403 and stopped. Terms assert rights in original content and restrict trademark use; no licensed feed was established. | Unavailable for collection. Source-format adapter and factual extract retained for offline tests; adapter and local collection flag disabled. No Naheed prices imported. Do not switch bot identity to work around the denial. |
| [Springs](https://springs.com.pk/) | Direct robots retrieval succeeded, correcting the initial web tool's inconclusive result. It excludes internal APIs, branch selection and various utility routes, plus named bots. [Terms](https://springs.com.pk/pages/terms-conditions) restrict copying/distribution of site material without written permission. The initial homepage opened location/branch selection. | Unavailable. Source-specific reuse and location-aware retrieval require further agreement/validation. |
| [Al-Fatah](https://alfatah.pk/) | Public storefront and [robots](https://alfatah.pk/robots.txt) inspected. [Terms](https://alfatah.pk/pages/terms-conditions) restrict site materials to personal shopping/noncommercial use and restrict redistribution. | Unavailable. Establish a suitable permission/feed arrangement before collecting for this platform. A provisional offline parser is included. |
| [GrocerApp](https://grocerapp.pk/) | Robots retrieval succeeded and lists product sitemaps. Homepage HTML did not expose useful product records in the inspection; applicable terms and product retrieval were not fully validated. | Investigated briefly; no adapter or imported data. |
| [Imtiaz](https://shop.imtiaz.com.pk/) | Robots request returned HTTP 307 to `/404`; the public ordering site requires location selection. | Not validated; no adapter or imported data. |

## Method and limits

Review requests identified themselves as `DaamRadarReview/0.1` with the public project repository URL. Production collection identifies itself as `DaamRadarBot/0.1` with a configured contact email or HTTPS project URL. These identities describe their respective purposes; the production identity was not changed after Naheed denied it. Collection does not retry access denials.

The collector reads robots before product requests and uses Protego for wildcard/allow precedence and repeated groups. Requests are HTTPS-only and restricted to source-specific public paths, without query parameters, redirects, internal API calls, login, CAPTCHA solving, proxy rotation, branch-cookie fabrication, or browser fingerprint spoofing. At least five seconds separate requests to a source, with stricter robots delays honored.

JSON-LD adapters require one unambiguous PKR Product/Offer and a matching heading. Cartpk instead requires a single reviewed DOM product block, one final-price field, agreeing visible/metadata prices, and explicit PKR currency. Recommendation prices are excluded. It does not repair malformed JSON, infer a price from a range, or select among variants. Images and descriptions are excluded. Fixtures contain minimal factual extracts, not complete pages or site/session configuration. Product illustrations are project-owned SVGs.

Local collection is enabled for Jalal Sons and eight reviewed Cartpk URLs, following the expansion described below. The environment switch permits manual commands; no scheduler exists. New source records default to disabled, and seeding preserves existing settings. Errors are stored in `ScrapeRun`; completed observations are retained if a later URL fails.

## Five-product expansion, 20 October 2026

The initial single-URL limit above is historical. The robots-aware named collector rechecked canonical terms and inspected four additional exact pairs: Olper's 1.5L, Nestle Milkpak 250ml, Nurpur 1L and Haleeb 1L. See the [reviewed catalog](milk-catalog.md) for the exact source URLs, observed prices, extraction/matching evidence and reproducible commands. Public terms still covered delivery/order/refund conditions; no general reuse license or retailer endorsement is claimed.

Cartpk's current adapter accepts only those four paths plus the original Olper's 1L path. Every allowed path has an expected identity, checked on both retailers before ingestion. Its Milkpak sale price (105) agrees with final/visible/metadata fields; regular price 120 is excluded. Nurpur's published 620 price is retained without substituting a category-page or assumed market value. Delivery areas remain unverified and winning/savings claims remain suppressed. Naheed, Springs, Al-Fatah and Olpers Mart were not enabled or retried.

Actual collection: run #7 stored five Jalal Sons observations; run #8 stored three Cartpk observations before a connection error; run #9 separately completed the two unfinished Cartpk URLs. The partial run is preserved. All five pairs share canonical products, with no duplicate imports during recovery. The catalog now contains eleven real listings across six products, including the earlier Everyday 180ml single-source listing. These runs demonstrate the small manual workflow; connection closures mean sustained reliability is still unverified.

## Pantry follow-up, 24 October 2026

The named robots-aware collector rechecked canonical terms and exact product pages. Three additional title/size/variant pairs were enabled: Dalda Sunflower Oil Pouch 1L, Dalda Canola Oil 4.5L and Shan Biryani Masala 50g. Reviewed tea/water candidates did not yield an exact pair and were not added. Canola/spice packaging remains unspecified rather than inferred. Both sources retain the delivery-area caveat.

Runs #12 and #13 each stored three observations in four requests. All earlier records were preserved; the catalog now has nine real products and seventeen listings, including the earlier single-source Everyday record. Cartpk's actual Biryani product price was 130, independently verified against visible/final/PKR metadata rather than a search/category snapshot. Preliminary connection closures stopped those review requests without automatic retries; separate unchanged-identity reviews succeeded. Both actual import runs succeeded. See the [pantry catalog](pantry-catalog.md) for exact URLs, dated prices, fixture evidence and scope. No general reuse license or retailer endorsement is claimed.

## Open source and data reuse

An open-source code license governs rights in the code licensed by its authors. It does not grant rights in another site's content. Nonprofit use is not a blanket exception to copyright, contract terms, access restrictions, or applicable law. Factual prices differ from authored descriptions and photographs, but that alone does not settle every source-specific or jurisdiction-specific issue. This engineering review is not a determination of legal rights for public launch or bulk collection.

References: [WIPO copyright FAQ](https://www.wipo.int/en/web/copyright/faq-copyright), [Creative Commons FAQ on facts and database contents](https://creativecommons.org/faq/), and [RFC 9309 section 1](https://www.rfc-editor.org/rfc/rfc9309.html#section-1), which distinguishes crawler rules from access authorization.

Before broader publication or scheduling, document the applicable reuse basis, any source agreement, allowed fields, attribution requirements, limits, delivery-area semantics, and fixture provenance. Revalidate technical behavior and terms as the integration grows.

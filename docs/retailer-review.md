# Retailer access investigation

Initial review: 18 October 2026; reliability and candidate-source follow-up: 20 October 2026. These are point-in-time observations from this environment. Public crawler rules and technical reachability do not establish a general license to reuse a website or its contents. The current collector is a small, manually invoked prototype that records factual product/offer fields only.

## Outcome

Three real observations were imported through the tested Jalal Sons collector:

| Public product page | Listed PKR price when checked |
| --- | --- |
| [Olpers Milk 1Ltr](https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398) | 350.00 |
| [Olpers Milk 1.5Ltr](https://www.jalalsons.com.pk/product/olpers-milk-15ltr-2809399) | 518.00 |
| [Nestle Everyday Milk 180Ml](https://www.jalalsons.com.pk/product/nestle-everyday-milk-180ml-2809387) | 44.00 |

Each page reported `InStock` in its public JSON-LD. Exact check times are stored in the local database. These are dated observations, not guaranteed current prices or delivery quotes. No branch/location was selected; every record says delivery area is unverified.

An intermediate two-product attempt on 18 October timed out and is recorded as blocked under the original error model. A later manual invocation with the same identity completed those pages. On 20 October, run #5 refreshed all three existing records in four HTTP requests; prices were unchanged, and each listing now has two real observations. The updated client permits at most one delayed retry for timeout exceptions only. Access denials and HTTP errors never retry. See the [collection runbook](collection-workflow.md).

## Second-source follow-up, 20 October 2026

- **Cartpk:** [robots](https://www.cartpk.com/robots.txt) permits ordinary public product paths and specifies a five-second delay. Its public footer linked `/terms-conditions/`, which redirected to the canonical [terms page](https://www.cartpk.com/terms-conditions); the canonical address was reviewed separately. The reviewed text covers delivery/refunds and did not state an explicit factual-price scraping prohibition. An identified request retrieved the public [Olper's 1L page](https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr), but the inspected JSON-LD could not be decoded. A follow-up attempt to inspect price fields failed with `ConnectionError`. No adapter was enabled, no malformed payload was repaired or guessed, and no prices were imported. A strict parser and reliable direct retrieval remain unvalidated. Terms/robots do not constitute a general reuse license.
- **Olpers Mart:** public robots and homepage were accessible and contained exact product links. Its [terms](https://olpersmart.pk/terms-and-condition) include restrictions on business use and third-party use/notification, as well as website-material reuse. No product collector was enabled and no price records were imported. Clarify the applicable access/reuse basis before pursuing this source.

Naheed's denied collector was not retried or given a different identity. Springs and Al-Fatah remain disabled. There is still no real cross-retailer comparison, and delivery areas remain unverified.

| Source | Actual observations | Current decision |
| --- | --- | --- |
| [Jalal Sons](https://www.jalalsons.com.pk/) | Direct identified requests retrieved [robots.txt](https://www.jalalsons.com.pk/robots.txt), [terms](https://www.jalalsons.com.pk/terms-and-conditions), and product HTML. Robots excludes `/api/*`, checkout and account routes; public `/product/...` paths are not excluded. Reviewed terms cover ordering/delivery and did not state an explicit product-price scraping ban. Three pages each exposed one explicit PKR JSON-LD Offer. | Limited manual factual-price adapter enabled locally; three observations imported. No endorsement, permission for bulk republication, or licensed feed claimed. Delivery area unverified. An intermediate timeout is documented. |
| [Naheed](https://www.naheed.pk/) | The initial web-fetch-tool request returned 403. A later identified review request retrieved [robots](https://www.naheed.pk/robots.txt), [terms](https://www.naheed.pk/terms-and-conditions), and an Olper's product page. The actual `DaamRadarBot` collector then returned 403 and stopped. Terms assert rights in original content and restrict trademark use; no licensed feed was established. | Unavailable for collection. Source-format adapter and factual extract retained for offline tests; adapter and local collection flag disabled. No Naheed prices imported. Do not switch bot identity to work around the denial. |
| [Springs](https://springs.com.pk/) | Direct robots retrieval succeeded, correcting the initial web tool's inconclusive result. It excludes internal APIs, branch selection and various utility routes, plus named bots. [Terms](https://springs.com.pk/pages/terms-conditions) restrict copying/distribution of site material without written permission. The initial homepage opened location/branch selection. | Unavailable. Source-specific reuse and location-aware retrieval require further agreement/validation. |
| [Al-Fatah](https://alfatah.pk/) | Public storefront and [robots](https://alfatah.pk/robots.txt) inspected. [Terms](https://alfatah.pk/pages/terms-conditions) restrict site materials to personal shopping/noncommercial use and restrict redistribution. | Unavailable. Establish a suitable permission/feed arrangement before collecting for this platform. A provisional offline parser is included. |
| [GrocerApp](https://grocerapp.pk/) | Robots retrieval succeeded and lists product sitemaps. Homepage HTML did not expose useful product records in the inspection; applicable terms and product retrieval were not fully validated. | Investigated briefly; no adapter or imported data. |
| [Imtiaz](https://shop.imtiaz.com.pk/) | Robots request returned HTTP 307 to `/404`; the public ordering site requires location selection. | Not validated; no adapter or imported data. |

## Method and limits

Review requests identified themselves as `DaamRadarReview/0.1` with the public project repository URL. Production collection identifies itself as `DaamRadarBot/0.1` with a configured contact email or HTTPS project URL. These identities describe their respective purposes; the production identity was not changed after Naheed denied it. Collection does not retry access denials.

The collector reads robots before product requests and uses Protego for wildcard/allow precedence and repeated groups. Requests are HTTPS-only and restricted to source-specific public paths, without query parameters, redirects, internal API calls, login, CAPTCHA solving, proxy rotation, branch-cookie fabrication, or browser fingerprint spoofing. At least five seconds separate requests to a source, with stricter robots delays honored.

The parser requires one unambiguous PKR Product/Offer and a matching visible heading. It does not infer prices from ranges or choose among multiple offers. Images and descriptions are excluded from imports. Source fixtures contain minimal factual extracts, not complete pages or site/session configuration. Product illustrations are project-owned SVGs.

Local collection is enabled only for Jalal Sons. The environment switch permits manual commands; no scheduler exists. New source records default to disabled, and retailer seeding preserves existing collection settings. Errors are stored in `ScrapeRun`; completed observations are retained if a later URL fails.

## Open source and data reuse

An open-source code license governs rights in the code licensed by its authors. It does not grant rights in another site's content. Nonprofit use is not a blanket exception to copyright, contract terms, access restrictions, or applicable law. Factual prices differ from authored descriptions and photographs, but that alone does not settle every source-specific or jurisdiction-specific issue. This engineering review is not a determination of legal rights for public launch or bulk collection.

References: [WIPO copyright FAQ](https://www.wipo.int/en/web/copyright/faq-copyright), [Creative Commons FAQ on facts and database contents](https://creativecommons.org/faq/), and [RFC 9309 section 1](https://www.rfc-editor.org/rfc/rfc9309.html#section-1), which distinguishes crawler rules from access authorization.

Before broader publication or scheduling, document the applicable reuse basis, any source agreement, allowed fields, attribution requirements, limits, delivery-area semantics, and fixture provenance. Revalidate technical behavior and terms as the integration grows.

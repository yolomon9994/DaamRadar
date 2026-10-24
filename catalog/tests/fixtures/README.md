# Parser fixture provenance

- `product.html` is the original **synthetic** fixture, not retailer content.
- `naheed_milk.html` contains the title and factual offer fields extracted from the public JSON-LD at https://www.naheed.pk/olper-s-full-cream-milk-1000ml on 18 October 2026. The observed price was PKR 380 and schema availability was `InStock`. The source uses `http://schema.org/Offer` as a fully qualified type.
- `jalal_milk.html` contains title, product ID, and factual offer fields extracted from public JSON-LD at https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398 on 18 October 2026. The observed price was PKR 350 and schema availability was `InStock`.
- `cartpk_milk.html` reproduces the factual product-block fields inspected at https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr on 20 October 2026: one final-price wrapper (360), visible price `Rs 360.00`, duplicate agreeing price metadata (360 and 360.00), explicit PKR metadata, the 1 Litre heading, canonical URL, and an `In stock` label. Two recommendation prices (190 and 720) remain outside the product block to test scoping. The JSON-LD is represented by a minimal invalid `\&#039;` escape matching the observed syntax failure; no source description is retained.

The expansion fixtures were extracted from the exact public pages below on 20 October 2026 using the same named collector and robots-aware client. Surrounding markup is reconstructed. Jalal Sons extracts contain the observed heading/name, brand, price, currency and schema availability. Cartpk extracts contain canonical URL, agreeing numeric/currency metadata, heading, scoped final price, stock label, and regular price when present.

| Fixture suffix (both `jalal_` and `cartpk_`) | Jalal Sons public page | Cartpk public page | Observed PKR (Jalal / Cartpk) |
| --- | --- | --- | --- |
| `olpers_1500.html` | https://www.jalalsons.com.pk/product/olpers-milk-15ltr-2809399 | https://www.cartpk.com/olpers-milk-1-5-ltr | 518 / 570 |
| `milkpak_250.html` | https://www.jalalsons.com.pk/product/nestle-milkpak-250ml-2809389 | https://www.cartpk.com/nestle-milk-pack-250-ml | 94 / 105 (regular 120) |
| `nurpur_1000.html` | https://www.jalalsons.com.pk/product/nurpur-milk-1ltr-2809394 | https://www.cartpk.com/nurpur-milk-full-cream-1ltr | 358 / 620 |
| `haleeb_1000.html` | https://www.jalalsons.com.pk/product/haleeb-milk-1ltr-2809384 | https://www.cartpk.com/haleeb-milk-1ltr | 334 / 405 |

The eight milk expansion extracts reported in-stock availability. Six pantry extracts were added from these exact pages on 24 October 2026 with the same robots-aware named client:

| Fixture suffix (both `jalal_` and `cartpk_`) | Jalal Sons public page | Cartpk public page | Observed PKR (Jalal / Cartpk) |
| --- | --- | --- | --- |
| `dalda_sunflower_1000.html` | https://www.jalalsons.com.pk/product/dalda-sunflower--oil-pouch-1ltr-2809005 | https://www.cartpk.com/dalda-sunflower-oil-pouch-1ltr | 609 / 630 |
| `dalda_canola_4500.html` | https://www.jalalsons.com.pk/product/dalda-canola-oil-45l-2809029 | https://www.cartpk.com/dalda-canola-oil-4-5ltr | 2834 / 3150 |
| `shan_biryani_50.html` | https://www.jalalsons.com.pk/product/shan-biryani-masala-50g-2808968 | https://www.cartpk.com/shan-biryani-masala-50g | 158 / 130 |

All pantry extracts reported in-stock availability. Source titles are preserved, including case/whitespace, with factual surrounding markup reconstructed as above. Cartpk fixtures retain agreeing visible/final/metadata prices, explicit PKR and canonical URL. No search/category price was substituted for the product page.

Every source-derived file is a **minimal factual extract**, not a complete saved page. Descriptions, images, executable scripts, analytics, browser/session metadata, and unrelated site configuration are omitted. These snapshots test observed formats and are not current-price claims or retailer-provided licensed feeds. Tests never fetch the source websites. See the [milk catalog](../../../docs/milk-catalog.md) and [pantry catalog](../../../docs/pantry-catalog.md) for scope and known limits.

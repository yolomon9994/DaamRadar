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

## 29 October 2026 expansion

Twenty-three minimal factual extracts were inspected with the same named, robots-aware client. Surrounding markup is reconstructed. Jalal Sons extracts preserve heading/name, structured brand and explicit PKR offer/stock. Cartpk extracts preserve canonical URL, heading, final-price amount/text, agreeing price/currency metadata and stock. No descriptions, images, executable code or session data are included. `jalal` and `cartpk` name the fixture source; absent source columns have no fixture and are not enabled counterparts. All reported in-stock availability at review. These are dated parser evidence, never seed data.

| Fixture key (`<source>_expanded_<key>.html`) | Jalal Sons page / PKR | Cartpk page / PKR |
| --- | --- | --- |
| `dalda_ghee_5000` | [https://www.jalalsons.com.pk/product/dalda-ghee-5kg-2809046](https://www.jalalsons.com.pk/product/dalda-ghee-5kg-2809046) / 3044.00 | — |
| `dalda_ghee_2500` | [https://www.jalalsons.com.pk/product/dalda-ghee-25kg-2809045](https://www.jalalsons.com.pk/product/dalda-ghee-25kg-2809045) / 1574.00 | — |
| `tapal_bags_100` | [https://www.jalalsons.com.pk/product/tapal-danedar-tea-bags-100-pieces-3007873](https://www.jalalsons.com.pk/product/tapal-danedar-tea-bags-100-pieces-3007873) / 899.00 | — |
| `lipton_430` | [https://www.jalalsons.com.pk/product/lipton-tea-430gm-2810108](https://www.jalalsons.com.pk/product/lipton-tea-430gm-2810108) / 1008.00 | — |
| `surf_1000` | — | [https://www.cartpk.com/surf-excel-detergent-powder-1kg](https://www.cartpk.com/surf-excel-detergent-powder-1kg) / 640.00 |
| `yogurt_plain_200` | [https://www.jalalsons.com.pk/product/nestle-yogurt-plain-200gm-2808831](https://www.jalalsons.com.pk/product/nestle-yogurt-plain-200gm-2808831) / 164.00 | — |
| `yogurt_strawberry_100` | [https://www.jalalsons.com.pk/product/nestle-fruit-yogurt-strawberry-100gm-2808827](https://www.jalalsons.com.pk/product/nestle-fruit-yogurt-strawberry-100gm-2808827) / 110.00 | — |
| `milkpak_cream_200` | [https://www.jalalsons.com.pk/product/nestle-milkpak-cream-200ml-2809410](https://www.jalalsons.com.pk/product/nestle-milkpak-cream-200ml-2809410) / 228.00 | [https://www.cartpk.com/nestle-milk-pack-cream-200-ml](https://www.cartpk.com/nestle-milk-pack-cream-200-ml) / 250.00 |
| `milkpak_butter_200` | [https://www.jalalsons.com.pk/product/nestle-milk-pak-dairy-butter-200g-3007553](https://www.jalalsons.com.pk/product/nestle-milk-pak-dairy-butter-200g-3007553) / 658.00 | — |
| `nesfruta_mango_1000` | [https://www.jalalsons.com.pk/product/nestle-nesfruta-mango-1l-2809139](https://www.jalalsons.com.pk/product/nestle-nesfruta-mango-1l-2809139) / 249.00 | — |
| `milo_180` | [https://www.jalalsons.com.pk/product/nestle-milo-drink-180ml-2809136](https://www.jalalsons.com.pk/product/nestle-milo-drink-180ml-2809136) / 94.00 | — |
| `milo_tin_235` | [https://www.jalalsons.com.pk/product/nestle-milo-drink-tin-235ml-2809137](https://www.jalalsons.com.pk/product/nestle-milo-drink-tin-235ml-2809137) / 594.00 | — |
| `national_chat_100` | [https://www.jalalsons.com.pk/product/national-chat-masala-100g-2808927](https://www.jalalsons.com.pk/product/national-chat-masala-100g-2808927) / 188.00 | — |
| `national_biryani_45` | [https://www.jalalsons.com.pk/product/national-biryani-masala-45g-2808924](https://www.jalalsons.com.pk/product/national-biryani-masala-45g-2808924) / 158.00 | — |
| `national_ginger_50` | [https://www.jalalsons.com.pk/product/national-ginger-powder-50g-3012051](https://www.jalalsons.com.pk/product/national-ginger-powder-50g-3012051) / 244.00 | — |
| `national_salt_800` | [https://www.jalalsons.com.pk/product/national-iodized-salt-800gm-2808929](https://www.jalalsons.com.pk/product/national-iodized-salt-800gm-2808929) / 60.00 | — |
| `national_chilli_100` | [https://www.jalalsons.com.pk/product/national-red-chilli-powder-100gm-2808930](https://www.jalalsons.com.pk/product/national-red-chilli-powder-100gm-2808930) / 198.00 | — |
| `evian_500` | [https://www.jalalsons.com.pk/product/evian-water-500ml-2810170](https://www.jalalsons.com.pk/product/evian-water-500ml-2810170) / 594.00 | — |
| `malee_coconut_330` | [https://www.jalalsons.com.pk/product/malee-coconut-water-330ml-2809163](https://www.jalalsons.com.pk/product/malee-coconut-water-330ml-2809163) / 548.00 | — |
| `everyday_15` | [https://www.jalalsons.com.pk/product/nestle-everyday-15g-2809418](https://www.jalalsons.com.pk/product/nestle-everyday-15g-2809418) / 30.00 | — |
| `shan_korma_50` | — | [https://www.cartpk.com/shan-korma-masala-50g](https://www.cartpk.com/shan-korma-masala-50g) / 350.00 |
| `national_chat_50` | — | [https://www.cartpk.com/national-chat-masala-50g](https://www.cartpk.com/national-chat-masala-50g) / 170.00 |

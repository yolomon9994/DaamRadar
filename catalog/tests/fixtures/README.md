# Parser fixture provenance

- `product.html` is the original **synthetic** fixture, not retailer content.
- `naheed_milk.html` contains the title and factual offer fields extracted from the public JSON-LD at https://www.naheed.pk/olper-s-full-cream-milk-1000ml on 18 October 2026. The observed price was PKR 380 and schema availability was `InStock`. The source uses `http://schema.org/Offer` as a fully qualified type.
- `jalal_milk.html` contains title, product ID, and factual offer fields extracted from public JSON-LD at https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398 on 18 October 2026. The observed price was PKR 350 and schema availability was `InStock`.

The last two files are **minimal factual extracts**, not complete saved pages. Surrounding markup is reconstructed for parser tests. Descriptions, images, scripts, analytics, browser/session metadata, and unrelated site configuration are deliberately omitted. These snapshots test observed formats and are not current-price claims or a retailer-provided licensed data feed. Tests never fetch the source websites.

from decimal import Decimal
from django.test import SimpleTestCase

from catalog.matching.normalization import identify, match_score, normalize_text


class MatchingTests(SimpleTestCase):
    def test_brand_punctuation_and_unit_aliases(self):
        base = identify("Olper's Full Cream Milk 1L")
        for title in ["Olpers Milk 1 Litre", "Olpers UHT Milk 1000ml", "OLPERS full cream MILK 1 liter", "Olpers Milk 1 ltr"]:
            with self.subTest(title=title):
                self.assertGreaterEqual(match_score(base, identify(title)), 92)
        self.assertEqual(base.quantity, Decimal("1000"))
        self.assertEqual(base.brand, "olpers")

    def test_compatible_weight_units(self):
        self.assertEqual(match_score(identify("Surf Excel Washing Powder 1kg"), identify("Surf Excel Washing Powder 1000 grams")), 100)

    def test_reject_incompatible_products(self):
        pairs = [
            ("Olpers Milk 1L", "Olpers Milk 250ml"),
            ("Olpers Milk 1L", "Olpers Milk 1kg"),
            ("Olpers Milk 1L", "Nestle Milk 1L"),
            ("Olpers Milk 1L", "Olpers Low Fat Milk 1L"),
            ("Olpers Milk 1L", "Olpers Chocolate Milk 1L"),
            ("Lays Masala 70g", "Lays Salted 70g"),
            ("National Ketchup 400g pouch", "National Ketchup 400g bottle"),
            ("National Ketchup 400g", "National Ketchup 400g pouch"),
            ("Olpers Milk 1L", "Olpers Milk 6x1L"),
            ("Olpers Milk 1L", "Olpers Milk 1L pack of 6"),
            ("Surf Excel Powder 1kg", "Surf Excel Automatic Powder 1kg"),
            ("Olpers Milk 1L", "Olpers Milk"),
        ]
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertLess(match_score(identify(left), identify(right)), 92)

    def test_pack_sizes(self):
        for title in ["Olpers Milk 6x1L", "Olpers Milk 6 × 1000ml", "Olpers Milk 1L pack of 6", "Olpers Milk 1L x 6", "Olpers Milk 1L 6 pack", "Olpers Milk 1L 6pk"]:
            with self.subTest(title=title):
                value = identify(title)
                self.assertEqual(value.pack_count, 6)
                self.assertEqual(value.quantity, Decimal("1000"))

    def test_gtin_does_not_override_size_or_variant(self):
        self.assertEqual(match_score(identify("Olpers Milk 1L", gtin="123"), identify("Olpers Milk 250ml", gtin="123")), 0)
        self.assertEqual(match_score(identify("Olpers Milk 1L", gtin="123"), identify("Olpers Milk 1L", gtin="456")), 0)
        self.assertEqual(match_score(identify("Olpers Milk 1L", gtin="123"), identify("Olpers UHT Milk 1000ml", gtin="123")), 100)

    def test_unknown_brand_size_and_ambiguous_sizes_are_not_merged(self):
        for title in ["Milk 1L", "Olpers Milk", "Olpers Milk 1L + 250ml", "Olpers Milk 0ml", "Olpers Milk 1L pack of 0", "Olpers Milk 1L pack of 2 pack of 6"]:
            with self.subTest(title=title):
                self.assertEqual(match_score(identify(title), identify(title)), 0)

    def test_decimal_sizes_and_normalization(self):
        self.assertEqual(identify("Nestlé Water 1.5L").quantity, Decimal("1500"))
        self.assertEqual(normalize_text("  OLPer’s   Milk "), "olpers milk")

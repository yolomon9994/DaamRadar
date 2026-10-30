import json

from django.core.management.base import BaseCommand

from catalog.services.catalog_quality import CHECKS, catalog_quality


class Command(BaseCommand):
    help = "Review local catalog metadata and identity issues without writes or retailer requests."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=["live", "demo"], default="live")
        parser.add_argument("--severity", choices=["all", "error", "warning"], default="all")
        parser.add_argument("--check", choices=["all", *CHECKS], default="all")
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        report = catalog_quality(**{key: options[key] for key in ("source", "severity", "check")})
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, ensure_ascii=False))
            return
        counts = report["counts"]
        self.stdout.write(f'Catalog quality ({report["source"]}) at {report["as_of"]}')
        self.stdout.write(f'Products {counts["products_scanned"]}/{counts["products_total"]}; listings {counts["listings_scanned"]}/{counts["listings_total"]}; compatible pairs {counts["pairs_checked"]}/{counts["pairs_possible"]}.')
        self.stdout.write(f'{counts["findings_selected"]} selected findings; {counts["findings_returned"]} returned. Review candidates only: never merge or reassign automatically.')
        if not report["complete"]:
            self.stdout.write('PARTIAL REPORT: limits reached for ' + ', '.join(key for key, value in report["limits"].items() if value) + '. Counts are limited to evaluated records.')
        for finding in report["findings"]:
            ids = [f'product #{p["id"]}' for p in finding["products"]] + [f'listing #{o["id"]}' for o in finding["listings"]]
            self.stdout.write(f'[{finding["severity"]}] {finding["code"]}: {", ".join(ids)} — {finding["detail"]}')
            if finding["evidence"]:
                self.stdout.write('  ' + json.dumps(finding["evidence"], ensure_ascii=False))
            if finding["references_limited"]:
                self.stdout.write(f'  References shortened: {finding["product_count"]} products / {finding["listing_count"]} listings.')
        if not report["findings"]:
            self.stdout.write("No findings in this selection of evaluated checks. This does not certify catalog accuracy.")

import os
from contextlib import closing
from pathlib import Path
import sqlite3

from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Create a new consistent SQLite backup without replacing an existing file."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("output", type=Path, help="New backup filename, normally under backups/.")

    def handle(self, *args, **options):
        database = connections["default"].settings_dict
        if database["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("Use pg_dump for PostgreSQL; this command supports file-backed SQLite only.")
        name = str(database["NAME"])
        if not name or name == ":memory:" or name.startswith("file:"):
            raise CommandError("A file-backed SQLite database is required.")
        source = Path(name).resolve()
        destination = options["output"].resolve()
        if not source.is_file():
            raise CommandError("The configured SQLite database does not exist.")
        if destination == source or destination.exists() or destination.is_symlink():
            raise CommandError("Choose a new backup filename; existing files are never replaced.")
        created = False
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            created = True
            os.close(descriptor)
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
                with closing(sqlite3.connect(destination)) as backup:
                    original.backup(backup)
                    if backup.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                        raise CommandError("Backup integrity verification failed.")
        except (OSError, sqlite3.Error, CommandError) as exc:
            if created:
                destination.unlink(missing_ok=True)
            raise CommandError("SQLite backup failed; source database was not modified.") from exc
        self.stdout.write(self.style.SUCCESS(f"Verified SQLite backup created: {destination}"))

# Database backup and restore

Backups include catalog records, history, scrape runs and Django admin account/password-hash data. Keep them private, retain copies outside the application machine, and test restoration periodically. `backups/` is Git-ignored; local backups are not automatically uploaded or scheduled. Preserve the application's secret key and deployment configuration separately in private storage; neither is included in a database backup.

## SQLite

Create a new consistent backup of the database selected by the current settings:

```powershell
.\.venv\Scripts\python.exe manage.py backup_sqlite backups/daamradar-2026-10-24.sqlite3
```

Choose a new filename each time. To select a deployed SQLite database, add `--settings=config.production` with that deployment's environment. The command accepts file-backed SQLite only; it rejects PostgreSQL, missing/in-memory source databases, the source path and existing output files. It opens the source read-only, uses SQLite's online backup API to include committed WAL data, closes both connections and verifies the result with `PRAGMA quick_check`. A failed operation removes only the new incomplete output it created. It does not change prices, check times or history.

Do not copy only a running `db.sqlite3` while ignoring its WAL file. Use the backup command above for a consistent snapshot. For example, verify an existing backup read-only without accidentally creating a database if the path is wrong:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; from pathlib import Path; p=Path('backups/daamradar-2026-10-24.sqlite3').resolve(); c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); print(c.execute('PRAGMA quick_check').fetchall()); print(c.execute('PRAGMA foreign_key_check').fetchall()); c.close()"
```

Expected results are `[('ok',)]` and `[]`. Integrity alone does not prove the desired data was backed up; compare product/listing/history counts and dated observations as well.

For restoration, work with a **new file** first:

1. Copy the verified backup to a separate restored filename and point an isolated application checkout at it using a SQLite `DATABASE_URL`. Keep collection disabled there.
2. Verify integrity, migration state and representative products/history/admin access with the matching application revision. Take another backup before any forward migrations.
3. Stop the actual app and all writers before promoting a restored database. Preserve the original database and any `-wal`/`-shm` companions together as a rollback set. Do not leave old companions alongside the restored database.
4. Prefer switching `DATABASE_URL` to the new validated filename while the app is stopped. Restart, check `/health/` through the intended route, and inspect actual catalog/history results before resuming writers.

The deployment implementation created a dated backup under local `backups/` and validated a separate restored copy under ignored `reports/`. Their complete logical SQL dumps, including every table, matched the untouched source. No restore was performed over the development database.

## PostgreSQL

Use PostgreSQL client tools compatible with the server major version. The following examples use native custom-format dumps, not Django `dumpdata`, and prompt for a password if required. In PowerShell, native `--file` avoids text encoding or binary redirection problems:

```powershell
pg_dump --host=127.0.0.1 --port=5432 --username=daamradar --dbname=daamradar --format=custom --file=backups/daamradar-2026-10-24.dump
pg_restore --list backups/daamradar-2026-10-24.dump
```

Create `backups/` first if necessary. Use the real database name, host and role, without placing passwords in command arguments or checked-in files. `pg_dump` takes a consistent database snapshot; it does not include cluster-wide roles or hosting configuration. Preserve role/extension provisioning through the deployment process. An encrypted provider backup may complement these logical dumps.

Restore into a newly created database owned by the appropriate application role:

```powershell
createdb --host=127.0.0.1 --port=5432 --username=daamradar --owner=daamradar daamradar_restore_check
pg_restore --host=127.0.0.1 --port=5432 --username=daamradar --dbname=daamradar_restore_check --no-owner --no-acl --exit-on-error backups/daamradar-2026-10-24.dump
```

The role needs permission to create that database, or an administrator/provider must provision it. `--no-owner --no-acl` leaves ownership with the restoring role and does not recreate previous grants; restore the intended grants separately. Do not use `--clean` against a live database. Check migrations and application data against this new database, then plan a stopped-writer cutover by changing the connection configuration. Keep the original database until restoration and cutover are verified.

Local validation used PostgreSQL 17.11, a disposable cluster and matching `pg_dump`/`pg_restore` binaries. A custom-format dump restored successfully into a second database, and every row of every public table matched the source, including migrations, permissions, products, listings and price history. This does not test a chosen provider's managed backup retention or off-machine recovery; exercise those after hosting is selected.

References: [SQLite backup API](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.backup), [PostgreSQL backup and restoration](https://www.postgresql.org/docs/17/backup-dump.html), [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

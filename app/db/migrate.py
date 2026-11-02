import argparse
import hashlib
import re
from pathlib import Path

from app.db.database import get_conn

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
LOCK_ID = 724180231


def load_migrations(directory):
    migrations = []
    versions = set()
    for path in sorted(Path(directory).glob("*.sql")):
        match = re.fullmatch(r"(\d{3})_[a-z0-9_]+\.sql", path.name)
        if match is None:
            raise ValueError(f"Invalid migration filename: {path.name}")
        version = match.group(1)
        if version in versions:
            raise ValueError(f"Duplicate migration version: {version}")
        versions.add(version)
        source = path.read_text(encoding="utf-8")
        if not source.strip():
            raise ValueError(f"Empty migration: {path.name}")
        checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()
        migrations.append((path.name, checksum, source))
    if not migrations:
        raise ValueError("No SQL migrations found")
    return migrations


def apply_migrations(directory=MIGRATIONS_DIR):
    migrations = load_migrations(directory)
    connection = get_conn()
    completed = []
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public.schema_migrations (
                        version text PRIMARY KEY,
                        checksum text NOT NULL,
                        applied_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    "SELECT version, checksum FROM public.schema_migrations ORDER BY version"
                )
                history = cursor.fetchall()
                expected = [(name, checksum) for name, checksum, _ in migrations[:len(history)]]
                if history != expected:
                    raise RuntimeError("Migration history differs from local files")
                for name, checksum, source in migrations[len(history):]:
                    cursor.execute(source)
                    cursor.execute(
                        "INSERT INTO public.schema_migrations (version, checksum) VALUES (%s, %s)",
                        (name, checksum),
                    )
                    completed.append(name)
        return completed
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    completed = apply_migrations()
    for name in completed:
        print(f"Applied: {name}")
    if not completed:
        print("Database schema is up to date")


if __name__ == "__main__":
    main()

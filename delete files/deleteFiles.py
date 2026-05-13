
"""
Delete files listed in a CSV from a given folder.

CSV format expectation:
- One filename per row (with or without header)
- Filenames can be just the name (e.g. "report.pdf") or a full/relative path
  (only the basename will be used for matching within the target folder)
"""

import csv
import os
import logging
from pathlib import Path
from typing import List, Optional

# ── Config ────────────────────────────────────────────────────────────────────
CSV_PATH   = r"C:\Users\sesa51816\Schneider Electric\C&S Common Group - Documents\IDSIG Product Data Repository\PDM\downloaded\_header_types\type_02_483files_10cols.csv"
CSV_COLUMN = None          # Set to None to use the first column
HAS_HEADER = False              # Set to False if CSV has no header row
FOLDER     = r"C:\Users\sesa51816\Schneider Electric\C&S Common Group - Documents\IDSIG Product Data Repository\PDM\downloaded"
DRY_RUN    = False                # Set to False to actually delete
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def read_filenames_from_csv(csv_path: str, column: Optional[str], has_header: bool) -> List[str]:
    names = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        if has_header:
            reader = csv.DictReader(f)
            col = column or reader.fieldnames[0]
            for row in reader:
                val = row.get(col, "").strip()
                if val:
                    names.append(Path(val).name)
        else:
            reader = csv.reader(f)
            col_idx = 0
            for row in reader:
                if row:
                    val = row[col_idx].strip()
                    if val:
                        names.append(Path(val).name)
    return names


def delete_files(folder: str, filenames: list[str], dry_run: bool) -> None:
    folder_path = Path(folder)
    if not folder_path.is_dir():
        log.error("Folder not found: %s", folder_path)
        return

    mode = "[DRY RUN] " if dry_run else ""
    found = deleted = skipped = 0

    for name in filenames:
        target = folder_path / name
        if target.exists():
            found += 1
            if dry_run:
                log.info("%sWould delete: %s", mode, target)
            else:
                try:
                    target.unlink()
                    log.info("Deleted: %s", target)
                    deleted += 1
                except OSError as e:
                    log.error("Failed to delete %s: %s", target, e)
        else:
            skipped += 1
            log.warning("Not found, skipping: %s", target)

    log.info("─" * 50)
    if dry_run:
        log.info("DRY RUN complete — %d would be deleted, %d not found.", found, skipped)
    else:
        log.info("Done — %d deleted, %d not found.", deleted, skipped)


def main():
    log.info("Reading CSV: %s", CSV_PATH)
    filenames = read_filenames_from_csv(CSV_PATH, CSV_COLUMN, HAS_HEADER)
    log.info("%d filename(s) loaded from CSV.", len(filenames))

    if not filenames:
        log.warning("No filenames found in CSV. Exiting.")
        return

    delete_files(FOLDER, filenames, DRY_RUN)


if __name__ == "__main__":
    main()
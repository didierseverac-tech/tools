"""consolidate_pim_csv.py

Consolidate two PIM CSV exports into one file.
"""

from __future__ import annotations

changelog = [
    "1.00   11/03/26    Initial version",
    "1.01   11/03/26    Add CLI args (--in / --out) with default file paths",
    "1.02   11/03/26    Normalize multiline cell values during consolidation",
]

import argparse
import csv
from pathlib import Path as _Path

INPUT_FILES = [
    _Path(r"C:\temp\Downloads\csv-2026-03-11_02.40.09.csv"),
    _Path(r"C:\temp\Downloads\csv-2026-03-11_02.47.22.csv"),
]
OUTPUT_FILE = _Path(r"C:\temp\Pim Extraction.csv")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for generic CSV consolidation."""

    _parser = argparse.ArgumentParser(description="Consolidate multiple CSV files into one output file")
    _parser.add_argument(
        "--in",
        dest="input_files",
        nargs="+",
        default=[str(_p) for _p in INPUT_FILES],
        help="Input CSV file paths (space-separated).",
    )
    _parser.add_argument(
        "--out",
        dest="output_file",
        default=str(OUTPUT_FILE),
        help="Output CSV file path.",
    )
    _parser.add_argument(
        "--keep-multiline-fields",
        action="store_true",
        help="Do not normalize embedded line breaks inside CSV fields.",
    )
    return _parser.parse_args()


def _detect_dialect(_csv_file: _Path) -> csv.Dialect:
    """Detect CSV dialect from a sample of the first input file."""

    with _csv_file.open("r", newline="", encoding="utf-8-sig") as _fi:
        _sample = _fi.read(65536)

    if not _sample:
        raise ValueError(f"Input file is empty: {_csv_file}")

    try:
        return csv.Sniffer().sniff(_sample, delimiters=",;	|")
    except Exception:
        class _Fallback(csv.Dialect):
            delimiter = ";"
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        return _Fallback


def _normalize_row_multiline(_row: list[str]) -> tuple[list[str], int]:
    """Replace embedded line breaks inside CSV cells with single spaces."""

    _out: list[str] = []
    _fixed = 0
    for _cell in _row:
        _txt = str(_cell)
        if "\n" in _txt or "\r" in _txt:
            _txt = " ".join(_txt.replace("\r", "\n").split("\n"))
            _txt = " ".join(_txt.split())
            _fixed += 1
        _out.append(_txt)
    return _out, _fixed


def consolidate_csv(
    _input_files: list[_Path],
    _output_file: _Path,
    *,
    normalize_multiline_fields: bool = True,
) -> None:
    """Merge multiple CSV files into one output file.

    Keeps the header from the first readable file and skips repeated headers.
    """

    _output_file.parent.mkdir(parents=True, exist_ok=True)

    _dialect = _detect_dialect(_input_files[0])

    _header: list[str] | None = None
    _rows_written = 0
    _fixed_cells = 0

    with _output_file.open("w", newline="", encoding="utf-8") as _fo:
        _writer = csv.writer(
            _fo,
            delimiter=_dialect.delimiter,
            quotechar=_dialect.quotechar,
            doublequote=_dialect.doublequote,
            quoting=_dialect.quoting,
            lineterminator="\n",
        )

        for _input_file in _input_files:
            if not _input_file.exists():
                raise FileNotFoundError(f"Input file not found: {_input_file}")

            with _input_file.open("r", newline="", encoding="utf-8-sig") as _fi:
                _reader = csv.reader(
                    _fi,
                    delimiter=_dialect.delimiter,
                    quotechar=_dialect.quotechar,
                    doublequote=_dialect.doublequote,
                    quoting=_dialect.quoting,
                )
                for _row in _reader:
                    if not _row or not any(str(_cell).strip() for _cell in _row):
                        continue

                    if normalize_multiline_fields:
                        _row, _fixed = _normalize_row_multiline(list(_row))
                        _fixed_cells += _fixed

                    if _header is None:
                        _header = list(_row)
                        _writer.writerow(_header)
                        continue

                    if list(_row) == _header:
                        continue

                    _writer.writerow(_row)
                    _rows_written += 1

    if _header is None:
        raise ValueError("No readable CSV content found in input files")

    print(f"Consolidated {_rows_written} data rows into: {_output_file}")
    if normalize_multiline_fields:
        print(f"Normalized multiline cells: {_fixed_cells}")


def main() -> int:
    """Run consolidation with configured file paths."""

    _args = parse_args()
    _input_files = [_Path(_p) for _p in _args.input_files]
    _output_file = _Path(_args.output_file)

    consolidate_csv(
        _input_files,
        _output_file,
        normalize_multiline_fields=not bool(_args.keep_multiline_fields),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

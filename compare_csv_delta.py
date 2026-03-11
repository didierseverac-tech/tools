"""compare_csv_delta.py

Compare two CSV files and export delta rows, using the first column as key.
"""

from __future__ import annotations

changelog = [
    "1.00   11/03/26    Initial version",
    "1.01   11/03/26    Use order-insensitive multiset comparison for robust delta detection",
    "1.02   11/03/26    Split outputs by change type and restore keyed CHANGED detection",
    "1.03   11/03/26    Auto-use first column as key; remove no-key branch",
    "1.04   11/03/26    Restore --key-cols; default to first column when omitted",
    "1.05   11/03/26    Fix wrapped CSV payload parsing to avoid comma-truncation false CHANGED",
    "1.06   11/03/26    Normalize quote artifacts in values to reduce false CHANGED",
    "1.07   11/03/26    Improve result CSV parsing and add changed_long output",
    "1.08   11/03/26    Export changed file with only key + changed column old/new values",
]

import argparse
import csv
import re as _re
from collections import Counter
from datetime import datetime as _datetime
from pathlib import Path as _Path
from typing import Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    _parser = argparse.ArgumentParser(description="Compare two CSV files and export delta (key = first column)")
    _parser.add_argument("--old", required=True, help="Baseline (old) CSV file path")
    _parser.add_argument("--new", required=True, help="Current (new) CSV file path")
    _parser.add_argument("--out", required=True, help="Output delta CSV file path")
    _parser.add_argument(
        "--key-cols",
        default="",
        help="Comma-separated key column names (default: first column)",
    )
    return _parser.parse_args()


def _detect_dialect(_csv_file: _Path) -> csv.Dialect:
    with _csv_file.open("r", newline="", encoding="utf-8-sig") as _fi:
        _sample = _fi.read(65536)

    if not _sample:
        raise ValueError(f"Input file is empty: {_csv_file}")

    try:
        return csv.Sniffer().sniff(_sample, delimiters=",;\t|")
    except Exception:
        class _Fallback(csv.Dialect):
            delimiter = ";"
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        return _Fallback


def _read_dict_rows(_csv_file: _Path) -> Tuple[List[str], List[Dict[str, str]], csv.Dialect]:
    def _read_wrapped_semicolon_payload() -> Tuple[List[str], List[Dict[str, str]]]:
        _payload_rows: List[List[str]] = []
        with _csv_file.open("r", newline="", encoding="utf-8-sig") as _fi:
            for _line in _fi:
                _line = _line.rstrip("\r\n")
                if not _line:
                    continue

                _payload_match = _re.match(r'^"(.*)"(?:,*)$', _line)
                _payload = _payload_match.group(1) if _payload_match else _line
                if _payload == "":
                    continue

                _payload = _payload.replace('""', '"')

                _inner_reader = csv.reader([_payload], delimiter=";", quotechar='"', doublequote=True)
                _inner_row = next(_inner_reader, [])
                if _inner_row:
                    _payload_rows.append(_inner_row)

        if not _payload_rows:
            return [], []

        _fieldnames_local = _payload_rows[0]
        _rows_local: List[Dict[str, str]] = []
        for _row_values in _payload_rows[1:]:
            _row_dict = {
                k: (_row_values[i] if i < len(_row_values) else "")
                for i, k in enumerate(_fieldnames_local)
            }
            _rows_local.append(_row_dict)

        return _fieldnames_local, _rows_local

    def _read_with_delimiter(_delimiter: str) -> Tuple[List[str], List[Dict[str, str]]]:
        with _csv_file.open("r", newline="", encoding="utf-8-sig") as _fi:
            _reader = csv.DictReader(
                _fi,
                delimiter=_delimiter,
                quotechar='"',
                doublequote=True,
                quoting=csv.QUOTE_MINIMAL,
            )
            _fieldnames_local = list(_reader.fieldnames or [])
            _rows_local = [dict(_row) for _row in _reader]
        return _fieldnames_local, _rows_local

    _dialect = _detect_dialect(_csv_file)
    _fieldnames, _rows = _read_with_delimiter(_dialect.delimiter)

    if len(_fieldnames) == 1 and ";" in (_fieldnames[0] or ""):
        _wrapped_fieldnames, _wrapped_rows = _read_wrapped_semicolon_payload()
        if len(_wrapped_fieldnames) > 1:
            _fieldnames = _wrapped_fieldnames
            _rows = _wrapped_rows

            class _Semicolon(csv.Dialect):
                delimiter = ";"
                quotechar = '"'
                doublequote = True
                skipinitialspace = False
                lineterminator = "\n"
                quoting = csv.QUOTE_MINIMAL

            _dialect = _Semicolon
            return _fieldnames, _rows, _dialect

    if len(_fieldnames) <= 1:
        _candidate_delimiters = [";", ",", "\t", "|"]
        _best_fieldnames = _fieldnames
        _best_rows = _rows
        _best_delimiter = _dialect.delimiter

        for _delimiter in _candidate_delimiters:
            _candidate_fieldnames, _candidate_rows = _read_with_delimiter(_delimiter)
            if len(_candidate_fieldnames) > len(_best_fieldnames):
                _best_fieldnames = _candidate_fieldnames
                _best_rows = _candidate_rows
                _best_delimiter = _delimiter

        _fieldnames = _best_fieldnames
        _rows = _best_rows

        if _best_delimiter != _dialect.delimiter:
            class _Override(csv.Dialect):
                delimiter = _best_delimiter
                quotechar = '"'
                doublequote = True
                skipinitialspace = False
                lineterminator = "\n"
                quoting = csv.QUOTE_MINIMAL

            _dialect = _Override

    return _fieldnames, _rows, _dialect


def _normalize(_value: str | None) -> str:
    if _value is None:
        return ""

    _text = str(_value).strip()
    while len(_text) >= 2 and _text.startswith('"') and _text.endswith('"'):
        _text = _text[1:-1].strip()

    _text = _text.replace('""', '"')
    _text = _text.replace('"', '')
    return _text.strip()


def _row_signature(_row: Dict[str, str], _cols: List[str]) -> Tuple[str, ...]:
    return tuple(_normalize(_row.get(_c, "")) for _c in _cols)


def _build_key(_row: Dict[str, str], _key_cols: List[str]) -> Tuple[str, ...]:
    return tuple(_normalize(_row.get(_c, "")) for _c in _key_cols)


def _row_from_signature(_sig: Tuple[str, ...], _cols: List[str]) -> Dict[str, str]:
    return {c: v for c, v in zip(_cols, _sig)}


def _derive_output_path(_base_out: _Path, _suffix: str) -> _Path:
    return _base_out.with_name(f"{_base_out.stem}_{_suffix}{_base_out.suffix}")


def _write_rows_to_csv(_target_file: _Path, _fieldnames: List[str], _rows: List[Dict[str, str]], _dialect: csv.Dialect) -> _Path:
    _target_file.parent.mkdir(parents=True, exist_ok=True)
    _actual_file = _target_file

    try:
        with _actual_file.open("w", newline="", encoding="utf-8-sig") as _fo:
            _writer = csv.DictWriter(
                _fo,
                fieldnames=_fieldnames,
                delimiter=",",
                quotechar='"',
                doublequote=True,
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
                extrasaction="ignore",
            )
            _writer.writeheader()
            _writer.writerows(_rows)
    except PermissionError:
        _stamp = _datetime.now().strftime("%Y%m%d_%H%M%S")
        _actual_file = _target_file.with_name(f"{_target_file.stem}_{_stamp}{_target_file.suffix}")
        with _actual_file.open("w", newline="", encoding="utf-8-sig") as _fo:
            _writer = csv.DictWriter(
                _fo,
                fieldnames=_fieldnames,
                delimiter=",",
                quotechar='"',
                doublequote=True,
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
                extrasaction="ignore",
            )
            _writer.writeheader()
            _writer.writerows(_rows)

    return _actual_file


def main() -> int:
    _args = parse_args()
    _old_file = _Path(_args.old)
    _new_file = _Path(_args.new)
    _out_file = _Path(_args.out)

    if not _old_file.exists():
        raise FileNotFoundError(f"Old CSV not found: {_old_file}")
    if not _new_file.exists():
        raise FileNotFoundError(f"New CSV not found: {_new_file}")

    _old_cols, _old_rows, _old_dialect = _read_dict_rows(_old_file)
    _new_cols, _new_rows, _new_dialect = _read_dict_rows(_new_file)

    if not _old_cols:
        raise ValueError(f"Old CSV has no columns: {_old_file}")
    if not _new_cols:
        raise ValueError(f"New CSV has no columns: {_new_file}")

    _key_cols = [c.strip() for c in (_args.key_cols or "").split(",") if c.strip()]
    if not _key_cols:
        _key_cols = [_old_cols[0]]
        if _new_cols[0] != _key_cols[0]:
            raise ValueError(f"First column mismatch: old='{_key_cols[0]}', new='{_new_cols[0]}'")

    for _c in _key_cols:
        if _c not in _old_cols:
            raise ValueError(f"Key column '{_c}' not found in old CSV")
        if _c not in _new_cols:
            raise ValueError(f"Key column '{_c}' not found in new CSV")

    _all_cols: List[str] = []
    for _c in _old_cols + _new_cols:
        if _c not in _all_cols:
            _all_cols.append(_c)

    print(f"Key column(s): {_key_cols}")
    print(f"Columns tracked: {_all_cols}")

    _delta_rows: List[Dict[str, str]] = []
    _added_rows: List[Dict[str, str]] = []
    _removed_rows: List[Dict[str, str]] = []
    _changed_rows: List[Dict[str, str]] = []

    _old_grouped: Dict[Tuple[str, ...], Counter[Tuple[str, ...]]] = {}
    _new_grouped: Dict[Tuple[str, ...], Counter[Tuple[str, ...]]] = {}

    for _r in _old_rows:
        _k = _build_key(_r, _key_cols)
        _old_grouped.setdefault(_k, Counter())[_row_signature(_r, _all_cols)] += 1

    for _r in _new_rows:
        _k = _build_key(_r, _key_cols)
        _new_grouped.setdefault(_k, Counter())[_row_signature(_r, _all_cols)] += 1

    _all_keys = set(_old_grouped.keys()) | set(_new_grouped.keys())
    for _k in sorted(_all_keys):
        _old_counter = _old_grouped.get(_k, Counter())
        _new_counter = _new_grouped.get(_k, Counter())

        _added_counter = _new_counter - _old_counter
        _removed_counter = _old_counter - _new_counter

        _pairs_to_change = min(sum(_added_counter.values()), sum(_removed_counter.values()))
        while _pairs_to_change > 0:
            _old_sig = next((_s for _s, _c in _removed_counter.items() if _c > 0), None)
            _new_sig = next((_s for _s, _c in _added_counter.items() if _c > 0), None)
            if _old_sig is None or _new_sig is None:
                break

            _removed_counter[_old_sig] -= 1
            if _removed_counter[_old_sig] <= 0:
                del _removed_counter[_old_sig]

            _added_counter[_new_sig] -= 1
            if _added_counter[_new_sig] <= 0:
                del _added_counter[_new_sig]

            _old_row = _row_from_signature(_old_sig, _all_cols)
            _new_row = _row_from_signature(_new_sig, _all_cols)
            _diff_cols = [c for c in _all_cols if _normalize(_old_row.get(c, "")) != _normalize(_new_row.get(c, ""))]

            _changed = {
                "change_type": "CHANGED",
                "changed_columns": "|".join(_diff_cols),
            }
            _changed.update({f"old_{c}": _normalize(_old_row.get(c, "")) for c in _all_cols})
            _changed.update({f"new_{c}": _normalize(_new_row.get(c, "")) for c in _all_cols})
            _delta_rows.append(_changed)

            for _col in _diff_cols:
                _changed_entry = {
                    "column": _col,
                    "old_value": _normalize(_old_row.get(_col, "")),
                    "new_value": _normalize(_new_row.get(_col, "")),
                }
                for _key_col in _key_cols:
                    _changed_entry[_key_col] = _normalize(_new_row.get(_key_col, ""))
                _changed_rows.append(_changed_entry)
            _pairs_to_change -= 1

        for _sig, _count in sorted(_added_counter.items()):
            _row = _row_from_signature(_sig, _all_cols)
            for _ in range(_count):
                _delta = {"change_type": "ADDED", "changed_columns": ""}
                _delta.update({f"old_{c}": "" for c in _all_cols})
                _delta.update({f"new_{c}": _normalize(_row.get(c, "")) for c in _all_cols})
                _delta_rows.append(_delta)
                _added_rows.append(_row)

        for _sig, _count in sorted(_removed_counter.items()):
            _row = _row_from_signature(_sig, _all_cols)
            for _ in range(_count):
                _delta = {"change_type": "REMOVED", "changed_columns": ""}
                _delta.update({f"old_{c}": _normalize(_row.get(c, "")) for c in _all_cols})
                _delta.update({f"new_{c}": "" for c in _all_cols})
                _delta_rows.append(_delta)
                _removed_rows.append(_row)

    _out_cols = ["change_type", "changed_columns"] + [f"old_{c}" for c in _all_cols] + [f"new_{c}" for c in _all_cols]
    _out_file_written = _write_rows_to_csv(_out_file, _out_cols, _delta_rows, _new_dialect)

    _added_out = _derive_output_path(_out_file, "added")
    _removed_out = _derive_output_path(_out_file, "removed")
    _changed_out = _derive_output_path(_out_file, "changed")
    _changed_out_cols = _key_cols + ["column", "old_value", "new_value"]

    _added_out_written = _write_rows_to_csv(_added_out, _all_cols, _added_rows, _new_dialect)
    _removed_out_written = _write_rows_to_csv(_removed_out, _all_cols, _removed_rows, _new_dialect)
    _changed_out_written = _write_rows_to_csv(_changed_out, _changed_out_cols, _changed_rows, _new_dialect)

    print(
        f"Delta exported: total={len(_delta_rows)}, added={len(_added_rows)}, "
        f"removed={len(_removed_rows)}, changed={len(_changed_rows)} -> {_out_file_written}"
    )
    print(f"Added file   : {_added_out_written}")
    print(f"Removed file : {_removed_out_written}")
    print(f"Changed file : {_changed_out_written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
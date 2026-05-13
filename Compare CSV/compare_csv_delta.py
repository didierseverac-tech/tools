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
    "1.09   11/03/26    Repair wrapped rows where first key field is merged as id;name",
    "1.10   11/03/26    Normalize key columns safely and enforce cleaned keys in outputs",
    "1.11   11/03/26    Revert to first-column key default and clean duplicated id artifacts in output",
    "1.12   11/03/26    Normalize ID artifacts during key matching to avoid add/remove duplicates",
    "1.13   11/03/26    Exclude key columns from changed-column detection",
    "1.14   11/03/26    Stabilize parser/comparison flow after false-positive investigation",
    "1.15   11/03/26    Suppress one-column-shift CHANGED false positives",
    "1.16   11/03/26    Enforce same parser mode on old/new and fix wrapped quote handling",
    "1.17   11/03/26    Replace wrapped/standard CSV parsing flow with unified auto-detection helpers",
    "1.18   11/03/26    Parse wrapped files with row-based outer CSV reader to support embedded line breaks",
    "1.19   11/03/26    Rebuild wrapped payload from full outer row to preserve commas inside fields",
    "1.20   11/03/26    Sanitize embedded line breaks in both input files before parsing",
]

import argparse
import csv
import tempfile
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


def _is_wrapped_format(_csv_file: _Path) -> bool:
    """Return True if file uses outer-comma / inner-semicolon wrapped format."""
    with _csv_file.open("r", newline="", encoding="utf-8-sig") as _fi:
        for _line in _fi:
            _line = _line.strip()
            if not _line:
                continue
            _outer = next(csv.reader([_line], delimiter=",", quotechar='"', doublequote=True), [])
            if not _outer:
                return False
            _payload = _outer[0]
            return ";" in _payload and len(_payload) > 10
    return False


def _parse_wrapped_row(_raw_line: str) -> List[str]:
    """
    Parse one raw line of the wrapped format:
      "field1;""field2"";""value, with comma"",,,,
    Step 1 – outer csv.reader extracts the quoted payload (handles commas inside quotes).
    Step 2 – inner csv.reader with ; splits into individual fields.
    """
    _raw_line = _raw_line.rstrip("\r\n")
    _outer = next(csv.reader([_raw_line], delimiter=",", quotechar='"', doublequote=True), [])
    _payload = _outer[0] if _outer else ""
    _inner = next(csv.reader([_payload], delimiter=";", quotechar='"', doublequote=True), [])
    return _inner


def _read_wrapped_file(_csv_file: _Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read a wrapped outer-comma / inner-semicolon CSV into fieldnames + row dicts."""
    _all_rows: List[List[str]] = []
    with _csv_file.open("r", newline="", encoding="utf-8-sig") as _fi:
        _outer_reader = csv.reader(_fi, delimiter=",", quotechar='"', doublequote=True)
        for _outer_row in _outer_reader:
            if not _outer_row:
                continue

            _payload = ",".join(_outer_row).rstrip(",").strip()
            if _payload == "":
                continue

            _row = next(csv.reader([_payload], delimiter=";", quotechar='"', doublequote=True), [])
            if _row:
                _all_rows.append(_row)

    if not _all_rows:
        return [], []

    _fieldnames = [_f.strip() for _f in _all_rows[0]]
    _rows: List[Dict[str, str]] = []
    for _values in _all_rows[1:]:
        _row_dict = {
            _fieldnames[_i]: (_values[_i].strip() if _i < len(_values) else "")
            for _i in range(len(_fieldnames))
        }
        _rows.append(_row_dict)
    return _fieldnames, _rows


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


def _read_standard_file(_csv_file: _Path) -> Tuple[List[str], List[Dict[str, str]], csv.Dialect]:
    """Read a standard CSV using dialect sniffing with semicolon fallback."""
    _dialect = _detect_dialect(_csv_file)
    with _csv_file.open("r", newline="", encoding="utf-8-sig") as _fi:
        _reader = csv.DictReader(
            _fi,
            delimiter=_dialect.delimiter,
            quotechar=_dialect.quotechar,
            doublequote=_dialect.doublequote,
            quoting=_dialect.quoting,
        )
        _fieldnames = list(_reader.fieldnames or [])
        _rows = [dict(_r) for _r in _reader]
    return _fieldnames, _rows, _dialect


def _sanitize_embedded_line_breaks(_src_file: _Path) -> _Path:
    """Create a temp copy where embedded line breaks inside quoted text are replaced by spaces."""
    _raw = _src_file.read_text(encoding="utf-8-sig")
    _out_chars: List[str] = []
    _in_quotes = False
    _i = 0

    while _i < len(_raw):
        _ch = _raw[_i]

        if _ch == '"':
            if _in_quotes and _i + 1 < len(_raw) and _raw[_i + 1] == '"':
                _out_chars.append('"')
                _out_chars.append('"')
                _i += 2
                continue
            _in_quotes = not _in_quotes
            _out_chars.append(_ch)
            _i += 1
            continue

        if _ch in {"\r", "\n"}:
            if _in_quotes:
                _out_chars.append(" ")
                if _ch == "\r" and _i + 1 < len(_raw) and _raw[_i + 1] == "\n":
                    _i += 2
                else:
                    _i += 1
                continue

            if _ch == "\r" and _i + 1 < len(_raw) and _raw[_i + 1] == "\n":
                _out_chars.append("\n")
                _i += 2
            else:
                _out_chars.append("\n")
                _i += 1
            continue

        _out_chars.append(_ch)
        _i += 1

    _tmp_name = f"{_src_file.stem}_sanitized_{_datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{_src_file.suffix}"
    _tmp_path = _Path(tempfile.gettempdir()) / _tmp_name
    _tmp_path.write_text("".join(_out_chars), encoding="utf-8-sig", newline="\n")
    return _tmp_path


def _read_dict_rows(_csv_file: _Path) -> Tuple[List[str], List[Dict[str, str]], csv.Dialect]:
    """
    Unified entry point: auto-detects wrapped vs standard format.
    Returns (fieldnames, rows, dialect).
    """
    if _is_wrapped_format(_csv_file):
        class _SemicolonDialect(csv.Dialect):
            delimiter = ";"
            quotechar = '"'
            doublequote = True
            skipinitialspace = False
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        _fieldnames, _rows = _read_wrapped_file(_csv_file)
        return _fieldnames, _rows, _SemicolonDialect

    return _read_standard_file(_csv_file)


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
    _key_values: List[str] = []
    for _c in _key_cols:
        _v = _normalize(_row.get(_c, ""))
        if _c.strip().lower() in {"<id>", "id"}:
            _v = _clean_id_artifact(_v)
        _key_values.append(_v)
    return tuple(_key_values)


def _clean_id_artifact(_value: str) -> str:
    _parts = [p.strip() for p in _value.split(";")]
    if len(_parts) == 2 and _parts[0] and _parts[0] == _parts[1]:
        return _parts[0]
    return _value


def _normalize_for_column(_column_name: str, _value: str | None) -> str:
    _normalized = _normalize(_value)
    if _column_name.strip().lower() in {"<id>", "id"}:
        return _clean_id_artifact(_normalized)
    return _normalized


def _clean_row_output(_row: Dict[str, str]) -> Dict[str, str]:
    _out = dict(_row)
    for _key_name in ("<ID>", "id"):
        if _key_name in _out:
            _out[_key_name] = _clean_id_artifact(_normalize(_out.get(_key_name, "")))
    return _out


def _row_from_signature(_sig: Tuple[str, ...], _cols: List[str]) -> Dict[str, str]:
    return {c: v for c, v in zip(_cols, _sig)}


def _is_shifted_false_positive(_old_row: Dict[str, str], _new_row: Dict[str, str], _all_cols: List[str], _key_cols_set: set[str]) -> bool:
    _cols = [c for c in _all_cols if c not in _key_cols_set]
    if len(_cols) < 10:
        return False

    _forward_hits = 0
    _forward_total = 0
    for _i in range(len(_cols) - 1):
        _a = _normalize(_old_row.get(_cols[_i], ""))
        _b = _normalize(_new_row.get(_cols[_i + 1], ""))
        if _a != "" or _b != "":
            _forward_total += 1
            if _a == _b:
                _forward_hits += 1

    _backward_hits = 0
    _backward_total = 0
    for _i in range(1, len(_cols)):
        _a = _normalize(_old_row.get(_cols[_i], ""))
        _b = _normalize(_new_row.get(_cols[_i - 1], ""))
        if _a != "" or _b != "":
            _backward_total += 1
            if _a == _b:
                _backward_hits += 1

    _forward_ratio = (_forward_hits / _forward_total) if _forward_total else 0.0
    _backward_ratio = (_backward_hits / _backward_total) if _backward_total else 0.0
    return max(_forward_ratio, _backward_ratio) >= 0.85


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
    _old_file_input = _Path(_args.old)
    _new_file_input = _Path(_args.new)
    _out_file = _Path(_args.out)

    if not _old_file_input.exists():
        raise FileNotFoundError(f"Old CSV not found: {_old_file_input}")
    if not _new_file_input.exists():
        raise FileNotFoundError(f"New CSV not found: {_new_file_input}")

    _old_file = _sanitize_embedded_line_breaks(_old_file_input)
    _new_file = _sanitize_embedded_line_breaks(_new_file_input)

    _old_cols, _old_rows, _old_dialect = _read_dict_rows(_old_file)
    _new_cols, _new_rows, _new_dialect = _read_dict_rows(_new_file)

    if not _old_cols:
        raise ValueError(f"Old CSV has no columns: {_old_file_input}")
    if not _new_cols:
        raise ValueError(f"New CSV has no columns: {_new_file_input}")

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

    _key_cols_set = set(_key_cols)

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
            _diff_cols = [
                c for c in _all_cols
                if c not in _key_cols_set and _normalize(_old_row.get(c, "")) != _normalize(_new_row.get(c, ""))
            ]

            if len(_diff_cols) >= 20 and _is_shifted_false_positive(_old_row, _new_row, _all_cols, _key_cols_set):
                _pairs_to_change -= 1
                continue

            _changed = {
                "change_type": "CHANGED",
                "changed_columns": "|".join(_diff_cols),
            }
            _changed.update({f"old_{c}": _normalize_for_column(c, _old_row.get(c, "")) for c in _all_cols})
            _changed.update({f"new_{c}": _normalize_for_column(c, _new_row.get(c, "")) for c in _all_cols})
            _delta_rows.append(_changed)

            for _col in _diff_cols:
                _changed_entry = {
                    "column": _col,
                    "old_value": _normalize_for_column(_col, _old_row.get(_col, "")),
                    "new_value": _normalize_for_column(_col, _new_row.get(_col, "")),
                }
                for _key_col in _key_cols:
                    _changed_entry[_key_col] = _clean_id_artifact(_normalize(_new_row.get(_key_col, "")))
                _changed_rows.append(_changed_entry)
            _pairs_to_change -= 1

        for _sig, _count in sorted(_added_counter.items()):
            _row = _row_from_signature(_sig, _all_cols)
            for _ in range(_count):
                _delta = {"change_type": "ADDED", "changed_columns": ""}
                _delta.update({f"old_{c}": "" for c in _all_cols})
                _delta.update({f"new_{c}": _normalize_for_column(c, _row.get(c, "")) for c in _all_cols})
                _delta_rows.append(_delta)
                _added_rows.append(_row)

        for _sig, _count in sorted(_removed_counter.items()):
            _row = _clean_row_output(_row_from_signature(_sig, _all_cols))
            for _ in range(_count):
                _delta = {"change_type": "REMOVED", "changed_columns": ""}
                _delta.update({f"old_{c}": _normalize_for_column(c, _row.get(c, "")) for c in _all_cols})
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
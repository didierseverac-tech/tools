import csv
from pathlib import Path
from collections import defaultdict

FOLDER = Path(r"C:\Users\sesa51816\Schneider Electric\C&S Common Group - Documents\IDSIG Product Data Repository\PDM\downloaded")
OUTPUT_FOLDER = FOLDER / "_header_types"

def get_csv_headers(filepath: Path) -> tuple[str, ...]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(filepath, newline="", encoding=encoding) as f:
                headers = next(csv.reader(f), [])
                return tuple(h.strip() for h in headers)
        except (UnicodeDecodeError, StopIteration):
            continue
    return ()

def main():
    csv_files = sorted(FOLDER.glob("*.csv"))

    if not csv_files:
        print("No CSV files found in the folder.")
        return

    signature_to_files: dict[tuple, list[str]] = defaultdict(list)

    for filepath in csv_files:
        sig = get_csv_headers(filepath)
        signature_to_files[sig].append(filepath.name)

    OUTPUT_FOLDER.mkdir(exist_ok=True)

    sorted_types = sorted(signature_to_files.items(), key=lambda x: -len(x[1]))

    print(f"Found {len(sorted_types)} distinct header structure(s) across {len(csv_files)} file(s).")
    print(f"Output folder: {OUTPUT_FOLDER}\n")

    for i, (sig, files) in enumerate(sorted_types, start=1):
        out_path = OUTPUT_FOLDER / f"type_{i:02d}_{len(files)}files_{len(sig)}cols.csv"
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["File Name"] + list(sig))
            for fname in sorted(files):
                writer.writerow([fname] + [""] * len(sig))
        print(f"Type {i:02d} — {len(files):>4} file(s), {len(sig):>2} col(s) → {out_path.name}")

    print("\n✅ Done.")

if __name__ == "__main__":
    main()
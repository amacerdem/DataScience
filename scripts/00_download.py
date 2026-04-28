"""Download the Olist Brazilian E-Commerce dataset from Kaggle.

Uses the new KGAT_ bearer-token API endpoint (no username required).
Set KAGGLE_API_TOKEN env var, or store it in ~/.kaggle/kaggle.json as
{"key": "KGAT_..."}.
"""
from pathlib import Path
import json
import os
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

DATASET = "olistbr/brazilian-ecommerce"
URL = f"https://www.kaggle.com/api/v1/datasets/download/{DATASET}"
ZIP = RAW / "olist.zip"


def get_token() -> str:
    token = os.environ.get("KAGGLE_API_TOKEN")
    if token:
        return token
    cfg = Path.home() / ".kaggle" / "kaggle.json"
    if cfg.exists():
        data = json.loads(cfg.read_text())
        return data.get("key", "")
    raise SystemExit("No Kaggle token found in env or ~/.kaggle/kaggle.json")


def main() -> None:
    token = get_token()
    print(f"Downloading {DATASET} → {ZIP}")
    req = urllib.request.Request(URL, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp, ZIP.open("wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    print(f"  zip size: {ZIP.stat().st_size / 1024 / 1024:.2f} MB")

    print("Extracting…")
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(RAW)
    ZIP.unlink()

    csvs = sorted(RAW.glob("*.csv"))
    print(f"\nExtracted {len(csvs)} CSVs:")
    for p in csvs:
        print(f"  {p.name:50s} {p.stat().st_size / 1024 / 1024:7.2f} MB")


if __name__ == "__main__":
    main()

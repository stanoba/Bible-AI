import sys
import urllib.request
import zipfile
from pathlib import Path

# Pridáme koreňový adresár do sys.path pre import config
sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def download_file(url: str, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"  [SKIP] Súbor už existuje: {dest_path.name}")
        return
    print(f"  [DOWN] Sťahujem: {url} -> {dest_path.name}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response, open(dest_path, "wb") as out_file:
        out_file.write(response.read())
    print(f"  [OK] Uložené: {dest_path.name}")


def download_cross_references():
    dest_path = config.FILE_CROSS_REFS
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"  [SKIP] Súbor už existuje: {dest_path.name}")
        return

    zip_path = config.DATA_RAW_DIR / "cross-references.zip"
    url = config.URL_CROSS_REFS
    print(f"  [DOWN] Sťahujem OpenBible cross-references.zip z {url}...")
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response, open(zip_path, "wb") as out_file:
        out_file.write(response.read())

    print("  [UNZIP] Rozbaľujem cross_references.txt...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        with zip_ref.open("cross_references.txt") as src, open(dest_path, "wb") as dst:
            dst.write(src.read())
            
    print(f"  [OK] Uložené do: {dest_path.name}")


def main():
    print("--- 1. Sťahovanie externých zdrojov ---")
    download_file(config.URL_BIBLE_XML, config.FILE_BIBLE_XML)
    download_cross_references()
    download_file(config.URL_GEOCODING, config.FILE_GEOCODING)
    print("Sťahovanie dokončené!\n")


if __name__ == "__main__":
    main()
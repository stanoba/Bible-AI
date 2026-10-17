import json
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def parse_audio_files():
    print("--- 2. Indexovanie MP3 súborov ---")
    if not config.DATA_AUDIO_DIR.exists():
        print(f"Varovanie: Adresár {config.DATA_AUDIO_DIR} neexistuje!")
        return {}

    audio_files = sorted(list(config.DATA_AUDIO_DIR.rglob("*.mp3")))
    print(f"Nájdených {len(audio_files)} MP3 súborov.")

    audio_index = {}

    for mp3_path in audio_files:
        parent_folder = mp3_path.parent.name.lower()
        file_name = mp3_path.name

        # Zistenie OSIS kódu podľa názvu adresára (napr. 01_genezis -> Gen, 40_evanjelium_podla_matusa -> Matt)
        osis_code = config.FOLDER_TO_OSIS.get(parent_folder)
        if not osis_code:
            continue

        # Extrakcia čísla kapitoly z konca názvu súboru (napr. 01_gn_01.mp3 -> 1, 19_z_001.mp3 -> 1, 6_bar_02.mp3 -> 2)
        match = re.search(r'_(\d+)\.mp3$', file_name, re.IGNORECASE)
        if match:
            chapter_num = int(match.group(1))
            rel_path = str(mp3_path.relative_to(config.BASE_DIR)).replace("\\", "/")
            key = f"{osis_code}_{chapter_num}"
            audio_index[key] = rel_path

    config.FILE_AUDIO_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with open(config.FILE_AUDIO_INDEX, "w", encoding="utf-8") as f:
        json.dump(audio_index, f, ensure_ascii=False, indent=2)

    print(f"  [OK] Indexovaných {len(audio_index)} kapitol. Uložené v {config.FILE_AUDIO_INDEX.name}\n")
    return audio_index


if __name__ == "__main__":
    parse_audio_files()
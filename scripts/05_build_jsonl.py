import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    print("--- 5. Generovanie JSONL pre Vektorové databázy ---")
    config.JSONL_DIR.mkdir(parents=True, exist_ok=True)

    audio_index = {}
    if config.FILE_AUDIO_INDEX.exists():
        with open(config.FILE_AUDIO_INDEX, "r", encoding="utf-8") as f:
            audio_index = json.load(f)

    if not config.FILE_BIBLE_XML.exists():
        print(f"Chyba: Súbor {config.FILE_BIBLE_XML} neexistuje! Spustite najprv 'task download'.")
        return

    tree = ET.parse(config.FILE_BIBLE_XML)
    root = tree.getroot()

    books_data = config.parse_bible_elements(root)
    count = 0

    with open(config.FILE_JSONL, "w", encoding="utf-8") as out:
        for book in books_data:
            book_name = book["book_name"]
            osis_code = book["osis_code"]
            sk_code = config.OSIS_TO_SK.get(osis_code, osis_code)

            for chapter in book["chapters"]:
                chap_num = chapter["chapter_num"]
                audio_path = audio_index.get(f"{osis_code}_{chap_num}")

                for verse in chapter["verses"]:
                    verse_num = verse["verse_num"]
                    verse_text = verse["text"]

                    record = {
                        "id": f"{osis_code}_{chap_num}_{verse_num}",
                        "book": book_name,
                        "code": sk_code,
                        "osis": osis_code,
                        "chapter": chap_num,
                        "verse": verse_num,
                        "text": verse_text,
                        "audio_file": audio_path
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1

    print(f"  [OK] JSONL vygenerovaný ({count} riadkov) v {config.FILE_JSONL}\n")


if __name__ == "__main__":
    main()
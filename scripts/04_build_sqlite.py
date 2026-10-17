import json
import sqlite3
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
    print("--- 4. Generovanie SQLite databázy pre Antigravity ---")
    config.SQLITE_DIR.mkdir(parents=True, exist_ok=True)

    if config.FILE_SQLITE_DB.exists():
        config.FILE_SQLITE_DB.unlink()

    conn = sqlite3.connect(config.FILE_SQLITE_DB)
    cur = conn.cursor()

    # Hlavná tabuľka pre verše
    cur.execute("""
    CREATE TABLE verses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book TEXT,
        code TEXT,
        osis_code TEXT,
        chapter INTEGER,
        verse INTEGER,
        text TEXT,
        audio_file TEXT,
        audio_start TEXT,
        audio_end TEXT,
        audio_start_sec REAL,
        audio_end_sec REAL
    )
    """)
    cur.execute("CREATE INDEX idx_book_chap_verse ON verses(osis_code, chapter, verse);")

    # FTS5 tabuľka pre bleskové full-text vyhľadávanie
    cur.execute("""
    CREATE VIRTUAL TABLE verses_fts USING fts5(
        book,
        text,
        content='verses',
        content_rowid='id'
    );
    """)

    # Triggery na udržiavanie FTS indexu synchronizovaného s tabuľkou verses
    cur.execute("""
    CREATE TRIGGER verses_ai AFTER INSERT ON verses BEGIN
        INSERT INTO verses_fts(rowid, book, text) VALUES (new.id, new.book, new.text);
    END;
    """)

    audio_index = {}
    if config.FILE_AUDIO_INDEX.exists():
        with open(config.FILE_AUDIO_INDEX, "r", encoding="utf-8") as f:
            audio_index = json.load(f)

    audio_timestamps = {}
    if config.FILE_AUDIO_TIMESTAMPS.exists():
        try:
            with open(config.FILE_AUDIO_TIMESTAMPS, "r", encoding="utf-8") as f:
                audio_timestamps = json.load(f)
        except Exception:
            audio_timestamps = {}

    if not config.FILE_BIBLE_XML.exists():
        print(f"Chyba: Súbor {config.FILE_BIBLE_XML} neexistuje! Spustite najprv 'task download'.")
        return

    tree = ET.parse(config.FILE_BIBLE_XML)
    root = tree.getroot()

    books_data = config.parse_bible_elements(root)
    count = 0

    for book in books_data:
        book_name = book["book_name"]
        osis_code = book["osis_code"]
        sk_code = config.OSIS_TO_SK.get(osis_code, osis_code)

        for chapter in book["chapters"]:
            chap_num = chapter["chapter_num"]
            audio_key = f"{osis_code}_{chap_num}"
            audio_path = audio_index.get(audio_key)
            chap_timestamps = audio_timestamps.get(audio_key, {}).get("verses", {})

            for verse in chapter["verses"]:
                verse_num = verse["verse_num"]
                verse_text = verse["text"]

                v_ts = chap_timestamps.get(str(verse_num))
                a_start = v_ts.get("start_formatted") if v_ts else None
                a_end = v_ts.get("end_formatted") if v_ts else None
                a_start_sec = v_ts.get("start") if v_ts else None
                a_end_sec = v_ts.get("end") if v_ts else None

                cur.execute("""
                INSERT INTO verses (book, code, osis_code, chapter, verse, text, audio_file, audio_start, audio_end, audio_start_sec, audio_end_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (book_name, sk_code, osis_code, chap_num, verse_num, verse_text, audio_path, a_start, a_end, a_start_sec, a_end_sec))
                count += 1

    conn.commit()
    conn.close()
    print(f"  [OK] SQLite databáza vytvorená ({count} veršov) v {config.FILE_SQLITE_DB}\n")


if __name__ == "__main__":
    main()
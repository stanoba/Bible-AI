import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

# Pridáme koreňový adresár do sys.path pre import config
sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_cross_references():
    cross_refs = defaultdict(list)
    if not config.FILE_CROSS_REFS.exists():
        return cross_refs

    with open(config.FILE_CROSS_REFS, "r", encoding="utf-8") as f:
        # OpenBible používajú ako oddeľovač tabulátor (\t)
        reader = csv.reader(f, delimiter="\t")
        next(reader, None)  # Preskočíme hlavičku

        for row in reader:
            # Kontrola: riadok má aspoň 3 stĺpce a tretí stĺpec (počet hlasov) je číslo >= 10
            if len(row) >= 3 and row[2].isdigit() and int(row[2]) >= 10:
                parts = row[0].split(".")
                if len(parts) == 3:
                    target_parts = row[1].split(".")
                    if len(target_parts) == 3:
                        sk_code = config.OSIS_TO_SK.get(
                            target_parts[0], target_parts[0]
                        )
                        cross_refs[(parts[0], parts[1], parts[2])].append(
                            f"{sk_code} {target_parts[1]}, {target_parts[2]}"
                        )
    return cross_refs


# Zoznam najčastejších slovenských biblických názvov miest a ich preklad na anglický kľúč v modern.jsonl
SLOVAK_PLACE_ALIASES = {
    "jeruzalem": "jerusalem",
    "jeruzaleme": "jerusalem",
    "jeruzalema": "jerusalem",
    "betlehem": "bethlehem",
    "betleheme": "bethlehem",
    "nazaret": "nazareth",
    "nazarete": "nazareth",
    "egypt": "egypt",
    "egypte": "egypt",
    "egypta": "egypt",
    "jordán": "jordan",
    "jordane": "jordan",
    "jordan": "jordan",
    "galilea": "galilee",
    "galilei": "galilee",
    "galilejské": "galilee",
    "samária": "samaria",
    "samárii": "samaria",
    "jericho": "jericho",
    "jerichu": "jericho",
    "rím": "rome",
    "ríme": "rome",
    "rim": "rome",
    "damask": "damascus",
    "damasku": "damascus",
    "babylon": "babylon",
    "babylone": "babylon",
    "babylona": "babylon",
    "antiochia": "antioch",
    "antiochii": "antioch",
    "atény": "athens",
    "aténach": "athens",
    "korint": "corinth",
    "korinte": "corinth",
    "efez": "ephesus",
    "efeza": "ephesus",
    "sinaj": "sinai",
    "sinaji": "sinai",
    "hebron": "hebron",
    "hebrone": "hebron",
    "betel": "bethel",
    "béthel": "bethel",
    "sichem": "shechem",
    "týrus": "tyre",
    "tyrus": "tyre",
    "sidon": "sidon",
    "sidón": "sidon",
    "tiberias": "tiberias",
    "kána": "cana",
    "kana": "cana",
    "kafarnaum": "capernaum",
    "kapernaum": "capernaum",
    "cezarea": "caesarea",
    "tarzus": "tarsus",
    "joppe": "joppa",
    "tarsus": "tarsus"
}


def load_places():
    places = {}
    if not config.FILE_GEOCODING.exists():
        return places

    with open(config.FILE_GEOCODING, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            lonlat = data.get("lonlat")
            if not lonlat:
                continue

            # OpenBible lonlat je vo formáte "longitude,latitude"
            coords = lonlat.split(",")
            if len(coords) == 2:
                lon, lat = coords[0].strip(), coords[1].strip()

                # Získame všetky známe názvy danej lokality
                names = [n.get("name") for n in data.get("names", []) if n.get("name")]
                if not names and data.get("friendly_id"):
                    names = [data.get("friendly_id")]

                for name in names:
                    places[name.lower()] = {
                        "name": name,
                        "lat": lat,
                        "lon": lon,
                        "maps": f"https://www.google.com/maps?q={lat},{lon}"
                    }
    return places


def find_places_in_text(text: str, places_db: dict):
    matched = []
    seen = set()
    # Vyčistíme slová z textu
    words = re.findall(r'\b[a-zA-ZáäčďéíĺľňóôŕšťúýžÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ]+\b', text)
    for w in words:
        w_lower = w.lower()
        target_name = SLOVAK_PLACE_ALIASES.get(w_lower, w_lower)
        if target_name in places_db and target_name not in seen:
            matched.append(places_db[target_name])
            seen.add(target_name)
    return matched


def main():
    print("--- 3. Generovanie Markdown pre NotebookLM ---")
    config.MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)

    cross_refs = load_cross_references()
    places_db = load_places()

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
    print(f"Spracovávam {len(books_data)} kníh Biblie...")

    CHUNK_SIZE = 10  # Cca 10 kníh na súbor (pre dodržanie limitu max 50 zdrojov v NotebookLM)

    for chunk_idx in range(0, len(books_data), CHUNK_SIZE):
        chunk_books = books_data[chunk_idx : chunk_idx + CHUNK_SIZE]
        part_num = chunk_idx // CHUNK_SIZE + 1
        filename = f"Biblia_Cast_{part_num:02d}.md"
        filepath = config.MARKDOWN_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            for book in chunk_books:
                book_name = book["book_name"]
                osis_code = book["osis_code"]
                f.write(f"# {book_name}\n\n")

                for chapter in book["chapters"]:
                    chap_num = chapter["chapter_num"]
                    f.write(f"## {book_name} - Kapitola {chap_num}\n")

                    audio_key = f"{osis_code}_{chap_num}"
                    if audio_key in audio_index:
                        f.write(f"*🎧 Audio nahrávka: `{audio_index[audio_key]}`*\n")
                    f.write("\n")

                    for verse in chapter["verses"]:
                        verse_num = verse["verse_num"]
                        verse_text = verse["text"]

                        refs = cross_refs.get((osis_code, str(chap_num), str(verse_num)), [])[:4]
                        matched_geo = find_places_in_text(verse_text, places_db)

                        extra = []
                        if refs:
                            extra.append(f"porov. {'; '.join(refs)}")
                        if matched_geo:
                            geo_str = ", ".join(
                                [f"📍 {g['name']} ({g['maps']})" for g in matched_geo[:2]]
                            )
                            extra.append(geo_str)

                        info_tag = f" *({ ' | '.join(extra) })*" if extra else ""
                        f.write(f"**{verse_num}.** {verse_text}{info_tag}\n")
                    f.write("\n")

    print(f"  [OK] Markdown súbory boli úspešne vygenerované v {config.MARKDOWN_DIR}\n")


if __name__ == "__main__":
    main()

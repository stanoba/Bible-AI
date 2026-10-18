import argparse
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
        reader = csv.reader(f, delimiter="\t")
        next(reader, None)  # Preskočíme hlavičku

        for row in reader:
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

            coords = lonlat.split(",")
            if len(coords) == 2:
                lon, lat = coords[0].strip(), coords[1].strip()
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


# Zoznam slovenských slov, ktoré vyzerajú ako mestá, ale v texte Biblie sú často všeobecnými slovami
PLACE_BLACKLIST = {"veria"}


def find_places_in_text(text: str, places_db: dict):
    matched = []
    seen = set()

    # Extrahujeme slová, ktoré sa začínajú VEĽKÝM písmenom (vlastné mená / mesta)
    words = re.findall(r'\b[A-ZÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ][a-zA-Záäčďéíĺľňóôŕšťúýž]*\b', text)

    for w in words:
        w_lower = w.lower()

        # Preskočíme slová z blacklistu
        if w_lower in PLACE_BLACKLIST:
            continue

        target_name = SLOVAK_PLACE_ALIASES.get(w_lower, w_lower)
        if target_name in places_db and target_name not in seen:
            matched.append(places_db[target_name])
            seen.add(target_name)

    return matched


def parse_universal_bible_xml(root):
    """
    Univerzálny parser podporujúci SEB Bibliu aj apokryfy.
    Bezpečne spracováva aj nečíselné kapitoly a verše (napr. number="Prologue").
    """
    first_book = root.find(".//book")
    if first_book is None:
        first_book = root.find(".//b")
    
    if first_book is not None and ("name" in first_book.attrib or "n" in first_book.attrib):
        books_data = []
        for testament in root.findall(".//testament") or [root]:
            for book in testament.findall(".//book") + testament.findall(".//b"):
                book_name = book.attrib.get("name") or book.attrib.get("n", "Neznáma kniha")
                osis_code = book.attrib.get("code") or book.attrib.get("osis", "APOC")
                
                chapters = []
                for idx, chapter in enumerate(book.findall("chapter") + book.findall("c"), start=1):
                    raw_num = chapter.attrib.get("number") or chapter.attrib.get("n", str(idx))
                    try:
                        chap_num = int(raw_num)
                    except ValueError:
                        chap_num = raw_num
                    
                    verses = []
                    for v_idx, verse in enumerate(chapter.findall("verse") + chapter.findall("v"), start=1):
                        raw_v_num = verse.attrib.get("number") or verse.attrib.get("n", str(v_idx))
                        try:
                            v_num = int(raw_v_num)
                        except ValueError:
                            v_num = raw_v_num

                        v_text = verse.text or ""
                        verses.append({"verse_num": v_num, "text": v_text})
                    
                    chapters.append({"chapter_num": chap_num, "verses": verses})
                
                if chapters:
                    books_data.append({
                        "book_name": book_name,
                        "osis_code": osis_code,
                        "chapters": chapters
                    })
        return books_data

    return config.parse_bible_elements(root)


def main():
    parser = argparse.ArgumentParser(description="Generovanie Markdown súborov z Biblie alebo apokryfov.")
    parser.add_argument(
        "--xml",
        type=str,
        default=str(config.FILE_BIBLE_XML),
        help="Cesta k XML súboru (predvolené: štandardná Biblia)"
    )
    args = parser.parse_args()

    xml_path = Path(args.xml)
    print(f"--- 3. Generovanie Markdown (vstup: {xml_path.name}) ---")
    
    config.MARKDOWN_DIR.mkdir(parents=True, exist_ok=True)

    cross_refs = load_cross_references()
    places_db = load_places()

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

    if not xml_path.exists():
        print(f"Chyba: Súbor {xml_path} neexistuje!")
        return

    tree = ET.parse(xml_path)
    root = tree.getroot()

    books_data = parse_universal_bible_xml(root)
    if not books_data:
        print("Chyba: Nepodarilo sa parsovať žiadne knihy zo zadaného XML.")
        return

    print(f"Spracovávam {len(books_data)} kníh...")

    CHUNK_SIZE = 10  # Cca 10 kníh na súbor

    for chunk_idx in range(0, len(books_data), CHUNK_SIZE):
        chunk_books = books_data[chunk_idx : chunk_idx + CHUNK_SIZE]
        part_num = chunk_idx // CHUNK_SIZE + 1
        
        prefix = xml_path.stem.replace("_sk", "")
        filename = f"{prefix}_Cast_{part_num:02d}.md" if prefix != "SlovakianSEBBible" else f"Biblia_Cast_{part_num:02d}.md"
        filepath = config.MARKDOWN_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            for book in chunk_books:
                book_name = book["book_name"]
                osis_code = book["osis_code"]
                f.write(f"# {book_name}\n\n")

                for chapter in book["chapters"]:
                    chap_num = chapter["chapter_num"]
                    
                    if isinstance(chap_num, int):
                        f.write(f"## {book_name} - Kapitola {chap_num}\n")
                    else:
                        f.write(f"## {book_name} - {chap_num}\n")

                    audio_key = f"{osis_code}_{chap_num}"
                    if audio_key in audio_index:
                        f.write(f"*🎧 Audio nahrávka: `{audio_index[audio_key]}`*\n")
                    f.write("\n")

                    chap_timestamps = audio_timestamps.get(audio_key, {}).get("verses", {})

                    for verse in chapter["verses"]:
                        verse_num = verse["verse_num"]
                        verse_text = verse["text"]

                        refs = cross_refs.get((osis_code, str(chap_num), str(verse_num)), [])[:4]
                        matched_geo = find_places_in_text(verse_text, places_db)
                        verse_ts = chap_timestamps.get(str(verse_num))

                        extra = []
                        if refs:
                            extra.append(f"porov. {'; '.join(refs)}")
                        if matched_geo:
                            geo_str = ", ".join(
                                [f"📍 {g['name']} ({g['maps']})" for g in matched_geo[:2]]
                            )
                            extra.append(geo_str)
                        if verse_ts and "start_formatted" in verse_ts:
                            extra.append(f"⏱️ {verse_ts['start_formatted']} - {verse_ts['end_formatted']}")

                        info_tag = f" *({ ' | '.join(extra) })*" if extra else ""
                        v_num_str = str(verse_num).strip()
                        prefix = f"**{verse_num}.** " if v_num_str not in ("0", "") else ""
                        f.write(f"{prefix}{verse_text}{info_tag}\n")
                    f.write("\n")

    print(f"  [OK] Markdown súbory boli úspešne vygenerované v {config.MARKDOWN_DIR}\n")


if __name__ == "__main__":
    main()

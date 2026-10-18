"""
Rýchly prekladač OCP apokryfov do čistej slovenčiny pomocou Google Gemini API.

Použitie:
  python scripts/10_translate_gemini.py --book LivPro
  python scripts/10_translate_gemini.py --book SibOr --model gemini-3.8-flash
"""

import argparse
import functools
import json
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("[CHYBA] Knižnica 'google-genai' nie je nainštalovaná. Nainštalujte ju: pip install google-genai")
    sys.exit(1)

print = functools.partial(print, flush=True)

sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Katalóg nekanonických kníh z OCP s prioritou pôvodných kompletných jazykov (starogréčtina, latinčina)
APOCRYPHA_BOOKS = {
    "1En": {
        "name_sk": "Prvá kniha Henochova",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/1En.xml",
        "version_priority": ["Ethiopic (English)", "English", "Ethiopic"],
    },
    "Jubi": {
        "name_sk": "Kniha Jubileí",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/Jubi.xml",
        "version_priority": ["Latin", "Latin (English)", "Ethiopic (English)", "Ethiopic", "English"],
    },
    "2Bar": {
        "name_sk": "Sýrska apokalypsa Baruchova (2 Baruch)",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/2Bar.xml",
        "version_priority": ["Greek", "Syriac", "Syriac (English)", "English"],
    },
    "3Bar": {
        "name_sk": "Grécka apokalypsa Baruchova (3 Baruch)",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/3Bar.xml",
        "version_priority": ["Greek", "Greek (English)", "English"],
    },
    "4Bar": {
        "name_sk": "Štvrtá kniha Baruchova",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/4Bar.xml",
        "version_priority": ["Greek", "Greek (English)", "English"],
    },
    "4Ezra": {
        "name_sk": "Štvrtá kniha Ezdrášova",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/4Ezra.xml",
        "version_priority": ["Latin", "Greek", "Latin (English)", "Syriac (English)", "English"],
    },
    "4Macc": {
        "name_sk": "Štvrtá kniha Makabejská",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/4Macc.xml",
        "version_priority": ["Greek", "Greek (English)", "English"],
    },
    "AdamEve": {
        "name_sk": "Život Adama a Evy (Apokalypsa Mojžišova)",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/AdamEve.xml",
        "version_priority": ["Greek", "Latin (Meyer)", "Latin (Mozley)", "Latin", "Greek (English)", "Latin (Meyer) (English)", "Latin (Mozley) (English)", "English"],
    },
    "Mois": {
        "name_sk": "Nanebovstúpenie Mojžiša (Testament Mojžišov)",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/Mois.xml",
        "version_priority": ["Latin", "Greek", "Latin (English)", "English"],
    },
    "TAbr": {
        "name_sk": "Testament Abrahámov",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/TAbr.xml",
        "version_priority": ["Greek", "Greek (English)", "English"],
    },
    "SibOr": {
        "name_sk": "Sibiline proroctvá",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/SibOr.xml",
        "version_priority": ["Greek", "English", "Greek (English)"],
    },
    "PssSol": {
        "name_sk": "Šalamúnove žalmy",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/PssSol.xml",
        "version_priority": ["Greek", "Greek (English)", "English"],
    },
    "JosAsen": {
        "name_sk": "Jozef a Aseneth",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/JosAsen.xml",
        "version_priority": ["Greek", "Greek (English)", "English"],
    },
    "LivPro": {
        "name_sk": "Životy prorokov",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/LivPro.xml",
        "version_priority": ["Greek", "English", "Greek (English)"],
    },
}

SYSTEM_INSTRUCTION = """
Si špičkový odborník na teologické a antické preklady zo starogréčtiny, latinčiny a angličtiny do spisovnej slovenčiny.
Prelož nasledujúce verše starovekej knižky do spisovnej, vznešenej a teologicky presnej slovenčiny.

DÔLEŽITÉ PRAVIDLÁ:
1. PÔVODNÝ JAZYK A KONTEXT: Text je v pôvodnej starogréčtine (Koine), latinčine alebo anglickom kritickom znení. Zachovaj pôvodný biblický význam, metafory a teologickú hĺbku starovekých autorov.
2. ŠTÝL A TERMINOLÓGIA: Používaj tradičnú slovenskú biblickú terminológiu a ustálené tvary (napr. archa zmluvy [nie truhla], prepílený vo dvoje, Siloe, Manasse, Šalamún, Ezechiáš). Vyhni sa moderným anachronizmom.
3. MENÁ: Mená biblických postáv a prorokov uvádzaj v spisovnej slovenskej biblickej podobe (napr. Izaiáš, Jeremiáš, Ezechiel, Ámos, Ozeáš, Sofoniáš, Aggeus, Zachariáš, Malachiáš, Nátan, Eliáš, Elizeus).
4. FORMÁT JSON: Vráť VÝHRADNE validný JSON objekt, kde kľúče sú ID veršov a hodnoty sú finálne slovenské preklady veršov.
"""


def ensure_input_file(book_code: str, book_info: dict) -> Path:
    config.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_file = config.DATA_RAW_DIR / f"{book_code}.xml"
    if raw_file.exists() and raw_file.stat().st_size > 0:
        return raw_file

    url = book_info.get("url")
    print(f"  [DOWN] Sťahujem {raw_file.name}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response, open(raw_file, "wb") as out_file:
        out_file.write(response.read())
    return raw_file


def parse_ocp_xml(root, version_priority):
    target_version = None

    # Pomocná funkcia: ignorujeme nekompletné verzie (fragmenty)
    def is_valid_version(version_elem):
        title = version_elem.attrib.get("title", "").lower()
        return "fragment" not in title

    # 1. Najprv vyhľadáme presnú zhodu názvu verzie (napr. 'Greek' má prednosť pred 'Greek (English)')
    for priority_title in version_priority:
        if "fragment" in priority_title.lower():
            continue
        for v in root.findall(".//version"):
            if not is_valid_version(v):
                continue
            title = v.attrib.get("title", "")
            if priority_title.lower() == title.lower():
                target_version = v
                print(f"  [VERZIA] Vybraná verzia textu (presná zhoda): '{title}'")
                break
        if target_version is not None:
            break

    # 2. Ak presná zhoda neexistuje, hľadáme čiastočnú zhodu
    if target_version is None:
        for priority_title in version_priority:
            if "fragment" in priority_title.lower():
                continue
            for v in root.findall(".//version"):
                if not is_valid_version(v):
                    continue
                title = v.attrib.get("title", "")
                if priority_title.lower() in title.lower():
                    target_version = v
                    print(f"  [VERZIA] Vybraná verzia textu (čiastočná zhoda): '{title}'")
                    break
            if target_version is not None:
                break

    if target_version is None:
        for v in root.findall(".//version"):
            if is_valid_version(v):
                target_version = v
                print(f"  [VERZIA] Používam náhradnú verziu: '{target_version.attrib.get('title')}'")
                break

    if target_version is None:
        target_version = root.find(".//version")

    if target_version is None:
        return {}

    text_elem = target_version.find("text")
    if text_elem is None:
        text_elem = target_version

    chapters_data = {}

    for chap_div in text_elem.findall("./div"):
        chap_num = chap_div.attrib.get("number", "").strip()
        if not chap_num:
            continue

        verse_list = []
        for verse_div in chap_div.findall("./div"):
            verse_num = verse_div.attrib.get("number", "").strip()
            if not verse_num:
                continue

            readings = [
                "".join(r.itertext()).strip()
                for r in verse_div.findall(".//reading")
                if "".join(r.itertext()).strip()
            ]
            full_text = " ".join(readings).strip()
            if full_text:
                verse_list.append((str(verse_num), full_text))

        if verse_list:
            chapters_data[str(chap_num)] = verse_list

    return chapters_data


def main():
    parser = argparse.ArgumentParser(description="Preklad OCP apokryfov cez Google Gemini API.")
    parser.add_argument(
        "--book",
        "-b",
        default="LivPro",
        choices=list(APOCRYPHA_BOOKS.keys()),
        help="Kód knižky na preklad (predvolené: LivPro)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default="gemini-3.8-flash",
        help="Názov modelu Gemini (predvolené: gemini-3.8-flash)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Počet veršov v jednej dávke pre Gemini API (predvolené: 50)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("\n[CHYBA] Nastavte premennú GEMINI_API_KEY z https://aistudio.google.com/\n")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    book_code = args.book
    book_info = APOCRYPHA_BOOKS[book_code]

    print(f"--- Preklad cez Google Gemini API: {book_info['name_sk']} ({book_code}) ---")
    print(f"Model: {args.model} | Dávkovanie: {args.batch_size} veršov/dávka\n")

    raw_file = ensure_input_file(book_code, book_info)

    tree = ET.parse(raw_file)
    chapters_data = parse_ocp_xml(tree.getroot(), book_info["version_priority"])

    checkpoint_file = config.DATA_RAW_DIR / f"{book_code}_checkpoint.json"
    output_sk_xml = config.DATA_RAW_DIR / f"{book_code}_sk.xml"

    checkpoint = {}
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                raw_cp = json.load(f)
                checkpoint = {str(k).strip(): v for k, v in raw_cp.items()}
        except Exception:
            checkpoint = {}

    # Zozbierame chýbajúce verše
    batch_to_translate = {}
    for chap_num, verses in chapters_data.items():
        for v_num, raw_text in verses:
            v_key = f"{chap_num}_{v_num}"
            if v_key not in checkpoint:
                batch_to_translate[v_key] = raw_text

    if not batch_to_translate:
        print("Všetky verše sú už preložené v checkpointe.")
    else:
        items = list(batch_to_translate.items())
        total_items = len(items)
        batch_size = max(1, args.batch_size)
        total_batches = (total_items + batch_size - 1) // batch_size

        print(f"Odosielam {total_items} veršov na preklad do Gemini API v {total_batches} dávkach...\n")

        for b_idx in range(0, total_items, batch_size):
            chunk = dict(items[b_idx : b_idx + batch_size])
            current_batch_num = b_idx // batch_size + 1
            print(f"  [DÁVKA {current_batch_num}/{total_batches}] Odosielam {len(chunk)} veršov ({args.model})...")

            prompt = "Prelož nasledujúci JSON objekt s veršami do slovenčiny:\n" + json.dumps(chunk, ensure_ascii=False, indent=2)

            try:
                response = client.models.generate_content(
                    model=args.model,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
                    contents=prompt,
                )

                raw_text = response.text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]

                translated_batch = json.loads(raw_text.strip())
                checkpoint.update(translated_batch)

                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump(checkpoint, f, ensure_ascii=False, indent=2)

                print(f"  [OK] Dávka {current_batch_num}/{total_batches} úspešne preložená ({len(translated_batch)} veršov).")

            except Exception as e:
                print(f"\n[CHYBA Gemini API]: {e}")
                sys.exit(1)

    # Overenie chýbajúcich veršov pred zostavením XML
    missing_verses = []
    for chap_num, verses in chapters_data.items():
        for v_num, _ in verses:
            v_key = f"{chap_num}_{v_num}"
            if v_key not in checkpoint:
                missing_verses.append(v_key)

    if missing_verses:
        print(f"\n[UPOZORNENIE] V checkpointe chýba ešte {len(missing_verses)} veršov. Výsledné XML sa vygeneruje až po dokončení všetkých veršov.")
        sys.exit(0)

    # Vytvorenie finálneho XML
    xml_root_sk = ET.Element("bible", attrib={"translation": f"Online Critical Pseudepigrapha ({book_info['name_sk']})", "status": "Gemini API preklad"})
    testament_elem = ET.SubElement(xml_root_sk, "testament", name="Old")
    book_elem = ET.SubElement(testament_elem, "book", name=book_info["name_sk"], code=book_code)

    for chap_num, verses in chapters_data.items():
        chapter_elem = ET.SubElement(book_elem, "chapter", number=str(chap_num))
        for v_num, _ in verses:
            v_key = f"{chap_num}_{v_num}"
            verse_elem = ET.SubElement(chapter_elem, "verse", number=str(v_num))
            verse_elem.text = checkpoint.get(v_key, "")

    rough_string = ET.tostring(xml_root_sk, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    with open(output_sk_xml, "wb") as f:
        f.write(reparsed.toprettyxml(indent="    ", encoding="utf-8"))

    print(f"\n[OK] Výsledný XML súbor vygenerovaný: {output_sk_xml}")


if __name__ == "__main__":
    main()
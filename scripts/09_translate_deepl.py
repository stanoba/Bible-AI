"""
Rýchly paralelný prekladateľ apokryfných kníh (1Henoch, Jubileá, atď.) z OCP repozitára 
do čistej slovenčiny pomocou oficiálneho DeepL API (s ochranou proti preťaženiu / rate limitom).

Použitie:
  python scripts/09_translate_deepl.py --book 1En --threads 2
"""

import argparse
import functools
import json
import os
import signal
import sys
import threading
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from xml.dom import minidom
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import deepl
except ImportError:
    print("[CHYBA] Knižnica 'deepl' nie je nainštalovaná. Nainštalujte ju pomocou: pip install deepl")
    sys.exit(1)

# Vynútenie okamžitého flushovania všetkých print volaní
print = functools.partial(print, flush=True)

# Pridanie koreňového adresára do sys.path pre import config
sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Zámok na vláknovo bezpečný zápis checkpointu do JSON súboru
checkpoint_lock = threading.Lock()

# Globálny Event na okamžité bezpečné zastavenie všetkých vlákien pri chybe alebo prerušení
stop_event = threading.Event()


def force_exit_on_ctrl_c(sig, frame):
    """Okamžite ukončí proces pri stlačení Ctrl+C bez čakania na blokované vlákna."""
    stop_event.set()
    print("\n\n" + "!" * 70)
    print(" [PRERUŠENÉ] Preklad cez DeepL bol okamžite zastavený (Ctrl+C).")
    print(" Všetky doposiaľ preložené verše sú bezpečne uložené v checkpoint JSON súbore.")
    print("!" * 70 + "\n")
    os._exit(0)


# Registrácia signal handlera pre okamžitú reakciu na Ctrl+C (SIGINT)
signal.signal(signal.SIGINT, force_exit_on_ctrl_c)


APOCRYPHA_BOOKS = {
    "1En": {
        "name_sk": "Prvá kniha Henochova",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/1En.xml",
        "version_priority": ["Ethiopic (English)", "English"],
    },
    "Jubi": {
        "name_sk": "Kniha Jubileí",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/Jubi.xml",
        "version_priority": ["Ethiopic (English)", "Latin (English)", "Latin", "Ethiopic"],
    },
    "2Bar": {
        "name_sk": "Sýrska apokalypsa Baruchova (2 Baruch)",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/2Bar.xml",
        "version_priority": ["Syriac (English)", "English", "Syriac"],
    },
    "3Bar": {
        "name_sk": "Grécka apokalypsa Baruchova (3 Baruch)",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/3Bar.xml",
        "version_priority": ["Greek (English)", "English", "Greek"],
    },
    "4Bar": {
        "name_sk": "Štvrtá kniha Baruchova",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/4Bar.xml",
        "version_priority": ["Greek (English)", "English", "Greek"],
    },
    "4Ezra": {
        "name_sk": "Štvrtá kniha Ezdrášova",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/4Ezra.xml",
        "version_priority": ["Latin (English)", "Syriac (English)", "Latin", "English"],
    },
    "4Macc": {
        "name_sk": "Štvrtá kniha Makabejská",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/4Macc.xml",
        "version_priority": ["Greek (English)", "English", "Greek"],
    },
    "AdamEve": {
        "name_sk": "Život Adama a Evy (Apokalypsa Mojžišova)",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/AdamEve.xml",
        "version_priority": ["Greek (English)", "Latin (English)", "English"],
    },
    "Mois": {
        "name_sk": "Nanebovstúpenie Mojžiša (Testament Mojžišov)",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/Mois.xml",
        "version_priority": ["Latin (English)", "Latin", "English"],
    },
    "TAbr": {
        "name_sk": "Testament Abrahámov",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/TAbr.xml",
        "version_priority": ["Greek (English)", "English", "Greek"],
    },
    "SibOr": {
        "name_sk": "Sibiline proroctvá",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/SibOr.xml",
        "version_priority": ["Greek","Greek (English)", "English"],
    },
    "PssSol": {
        "name_sk": "Šalamúnove žalmy",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/PssSol.xml",
        "version_priority": ["Greek (English)", "English", "Greek"],
    },
    "JosAsen": {
        "name_sk": "Jozef a Aseneth",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/JosAsen.xml",
        "version_priority": ["Greek (English)", "English", "Greek"],
    },
    "LivPro": {
        "name_sk": "Životy prorokov",
        "url": "https://raw.githubusercontent.com/OnlineCriticalPseudepigrapha/Online-Critical-Pseudepigrapha/master/static/docs/LivPro.xml",
        "version_priority": ["Greek (English)", "English", "Greek"],
    },
}

BIBLICAL_NAMES_SK = {
    "Isaiah": "Izaiáš", "Jeremiah": "Jeremiáš", "Ezekiel": "Ezechiel", "Daniel": "Daniel",
    "Hosea": "Ozeáš", "Joel": "Joel", "Amos": "Ámos", "Obadiah": "Obadiáš", "Jonah": "Jonáš",
    "Micah": "Micheáš", "Nahum": "Nahum", "Habakkuk": "Habakuk", "Zephaniah": "Sofoniáš",
    "Haggai": "Aggeus", "Zechariah": "Zachariáš", "Malachi": "Malachiáš", "Moses": "Mojžiš",
    "Aaron": "Áron", "Adam": "Adam", "Eve": "Eva", "Enoch": "Henoch", "Noah": "Noe",
    "Abraham": "Abrahám", "Isaac": "Izák", "Jacob": "Jakub", "Joseph": "Jozef",
}


def clean_single_word(word: str) -> str:
    stripped = word.strip(".,;:!?()[]\"' ")
    if not stripped:
        return word.strip()
    return BIBLICAL_NAMES_SK.get(stripped, BIBLICAL_NAMES_SK.get(stripped.capitalize(), word.strip()))


def ensure_input_file(book_code: str, book_info: dict) -> Path:
    config.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_file = config.DATA_RAW_DIR / f"{book_code}.xml"

    if raw_file.exists() and raw_file.stat().st_size > 0:
        print(f"  [OK] Načítavam lokálny súbor: {raw_file.name}")
        return raw_file

    url = book_info.get("url")
    if not url:
        print(f"\n[CHYBA] Súbor '{raw_file.name}' nebol nájdený v {config.DATA_RAW_DIR}!")
        sys.exit(1)

    print(f"  [DOWN] Sťahujem {raw_file.name} z GitHubu...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as response, open(raw_file, "wb") as out_file:
            out_file.write(response.read())
        print(f"  [OK] Uložené do: {raw_file.name}")
    except Exception as e:
        print(f"\n[CHYBA] Nepodarilo sa stiahnuť súbor: {e}")
        sys.exit(1)

    return raw_file


def save_checkpoint_safe(checkpoint: dict, checkpoint_file: Path):
    """Vláknovo bezpečné uloženie checkpointu ošetrené proti WinError 5 na Windowse."""
    with checkpoint_lock:
        temp_file = checkpoint_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            for attempt in range(5):
                try:
                    temp_file.replace(checkpoint_file)
                    break
                except PermissionError:
                    if attempt < 4:
                        time.sleep(0.05)
                    else:
                        with open(checkpoint_file, "w", encoding="utf-8") as f:
                            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
                        if temp_file.exists():
                            try:
                                temp_file.unlink()
                            except Exception:
                                pass
        except Exception as e:
            print(f" Upozornenie pri zápise checkpointu: {e}")


def parse_ocp_xml(root, version_priority):
    target_version = None

    for priority_title in version_priority:
        for v in root.findall(".//version"):
            title = v.attrib.get("title", "")
            if priority_title.lower() in title.lower():
                target_version = v
                print(f"  [VERZIA] Vybraná verzia textu: '{title}'")
                break
        if target_version is not None:
            break

    if target_version is None:
        target_version = root.find(".//version")
        if target_version is not None:
            print(f"  [VERZIA] Používam náhradnú verziu: '{target_version.attrib.get('title')}'")

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

            readings = []
            for reading in verse_div.findall(".//reading"):
                r_text = "".join(reading.itertext()).strip()
                if r_text:
                    readings.append(r_text)

            full_verse_text = " ".join(readings).strip()
            if full_verse_text:
                verse_list.append((str(verse_num), full_verse_text))

        if verse_list:
            chapters_data[str(chap_num)] = verse_list

    return chapters_data


def process_deepl_verse_task(task_data, translator, max_retries=5):
    """Spracuje preklad jedného verša cez DeepL API s opakovaným čakaním pri Rate Limite."""
    if stop_event.is_set():
        return None

    chap_num, v_num, raw_text, book_code = task_data
    v_key = f"{chap_num}_{v_num}"

    for attempt in range(1, max_retries + 1):
        if stop_event.is_set():
            return None

        try:
            result = translator.translate_text(raw_text, target_lang="SK")
            v_sk_text = result.text.strip()
            return chap_num, v_num, v_key, v_sk_text
        except Exception as e:
            err_str = str(e)
            if "Too many requests" in err_str or "429" in err_str or "high load" in err_str:
                backoff_sec = attempt * 3  # Graduálne predlžovanie čakania (3s, 6s, 9s...)
                if attempt < max_retries:
                    time.sleep(backoff_sec)
                    continue
            
            stop_event.set()
            print(f"\n[CHYBA DeepL API] Zlyhal preklad pre verš {chap_num}:{v_num}: {e}")
            raise e


def main():
    parser = argparse.ArgumentParser(description="Paralelný prekladač OCP apokryfov pomocou DeepL API.")
    parser.add_argument(
        "--book",
        "-b",
        default="1En",
        choices=list(APOCRYPHA_BOOKS.keys()),
        help="Kód knižky na preklad (predvolené: 1En)",
    )
    parser.add_argument(
        "--threads",
        "-t",
        type=int,
        default=2,
        help="Počet paralelných vlákien pre DeepL API (predvolené: 2)",
    )
    parser.add_argument(
        "--api-key",
        "-k",
        type=str,
        default=os.environ.get("DEEPL_API_KEY", ""),
        help="DeepL API kľúč (predvolené: premenná prostredia DEEPL_API_KEY)",
    )
    args = parser.parse_args()

    api_key = args.api_key.strip()
    if not api_key:
        print("\n" + "!" * 70)
        print(" [CHYBA] Chýba DeepL API kľúč!")
        print(" Zadajte ho pomocou argumentu --api-key alebo uložte do premennej DEEPL_API_KEY.")
        print("!" * 70 + "\n")
        sys.exit(1)

    try:
        translator = deepl.Translator(api_key)
        usage = translator.get_usage()
        if usage.character.valid:
            used = usage.character.count
            limit = usage.character.limit
            print(f"  [DEEPL] Pripojené úspešne. Využitie znakov: {used} / {limit}")
    except Exception as e:
        print(f"\n[CHYBA] Nepodarilo sa pripojiť k DeepL API: {e}")
        sys.exit(1)

    book_code = args.book
    num_threads = max(1, args.threads)
    book_info = APOCRYPHA_BOOKS[book_code]

    print(f"--- Preklad apokryfu cez DeepL API: {book_info['name_sk']} ({book_code}) ---")

    raw_file = ensure_input_file(book_code, book_info)

    tree = ET.parse(raw_file)
    root = tree.getroot()

    chapters_data = parse_ocp_xml(root, book_info["version_priority"])
    print(f"Nájdených {len(chapters_data)} kapitol.")

    if not chapters_data:
        print("Chyba: Nepodarilo sa vyextrahovať žiadne kapitoly!")
        sys.exit(1)

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

    unprocessed_tasks = []
    skipped_count = 0
    auto_resolved_count = 0

    for chap_num, verses in chapters_data.items():
        for v_num, raw_text in verses:
            v_key = f"{chap_num}_{v_num}"
            raw_clean = raw_text.strip()
            words = raw_clean.split()

            if len(words) <= 1:
                existing_val = checkpoint.get(v_key, "").strip()
                if not existing_val or len(existing_val.split()) > 3:
                    resolved_text = clean_single_word(words[0]) if words else raw_clean
                    checkpoint[v_key] = resolved_text
                    save_checkpoint_safe(checkpoint, checkpoint_file)
                    auto_resolved_count += 1
                skipped_count += 1
                continue

            if v_key in checkpoint:
                skipped_count += 1
            else:
                unprocessed_tasks.append((chap_num, v_num, raw_text, book_code))

    translated_count = 0
    total_to_translate = len(unprocessed_tasks)

    if auto_resolved_count > 0:
        print(f"Automaticky vybavených {auto_resolved_count} jednoslovných veršov/mien.")

    if skipped_count > 0:
        print(f"Načítaných {skipped_count} veršov z checkpointu (pokračujem od verša {skipped_count + 1}).")

    if total_to_translate > 0:
        print(f"Spúšťam paralelný preklad cez DeepL pre {total_to_translate} veršov ({num_threads} vlákna)...")

        executor = ThreadPoolExecutor(max_workers=num_threads)
        futures = {
            executor.submit(process_deepl_verse_task, task, translator): task
            for task in unprocessed_tasks
        }

        translation_interrupted = False
        try:
            for future in as_completed(futures):
                if stop_event.is_set():
                    translation_interrupted = True
                    break

                res = future.result()
                if res is None:
                    continue

                chap_num, v_num, v_key, v_sk_text = res
                checkpoint[v_key] = v_sk_text
                save_checkpoint_safe(checkpoint, checkpoint_file)

                translated_count += 1
                print(f"  [{skipped_count + translated_count}/{skipped_count + total_to_translate}] [OK] {book_code} {chap_num:>3}:{v_num:<3}")

        except (KeyboardInterrupt, SystemExit):
            translation_interrupted = True
            stop_event.set()
            print("\n  [PRERUŠENÉ] Preklad prerušený používateľom.")
        except Exception as e:
            translation_interrupted = True
            stop_event.set()
            print(f"\n  [CHYBA] Chyba počas paralelného prekladu: {e}")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if translation_interrupted:
            print(f"\nPreklad bol pozastavený. Úspešne uložených v checkpointe: {len(checkpoint)} veršov.")
            sys.exit(1)

    # Rekonštrukcia finálneho XML súboru v SEB štruktúre
    print("\nVytváram výsledný XML súbor v SEB formáte...")

    xml_root_sk = ET.Element("bible", attrib={
        "translation": f"Online Critical Pseudepigrapha ({book_info['name_sk']})",
        "status": "Oficiálny preklad cez DeepL API.",
        "link": book_info.get("url", "")
    })

    testament_elem = ET.SubElement(xml_root_sk, "testament", name="Old")
    book_elem = ET.SubElement(testament_elem, "book", name=book_info["name_sk"], code=book_code)

    for chap_num, verses in chapters_data.items():
        chapter_elem = ET.SubElement(book_elem, "chapter", number=str(chap_num))
        for v_num, _ in verses:
            v_key = f"{chap_num}_{v_num}"
            v_sk_text = checkpoint.get(v_key, "")

            verse_elem = ET.SubElement(chapter_elem, "verse", number=str(v_num))
            verse_elem.text = v_sk_text

    output_sk_xml.parent.mkdir(parents=True, exist_ok=True)

    rough_string = ET.tostring(xml_root_sk, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="    ", encoding="utf-8")

    with open(output_sk_xml, "wb") as f:
        f.write(pretty_xml)

    print("\n" + "=" * 70)
    print(f"Preklad pre {book_info['name_sk']} bol úspešne dokončený cez DeepL API!")
    print(f" - Celkovo veršov: {len(checkpoint)}")
    print(f" - Výsledné SEB XML: {output_sk_xml}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
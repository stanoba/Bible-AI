"""
Univerzálny skript na automatický dvojprechodový paralelný preklad apokryfných kníh 
(1Henoch, Jubileá, atď.) z OCP repozitára do čistej slovenčiny pomocou LM Studio.

Spracovanie prebieha paralelne vo viacero vláknach (nastaviteľné cez argument --threads):
  Pass 1: Hrubý preklad z angličtiny/latinčiny do slovenčiny.
  Pass 2: Jazyková a teologická korektúra (odstránenie čechizmov, oprava slovosledu a diakritiky).

Použitie:
  python scripts/07_translate_apocrypha.py --book 1En --threads 2
  python scripts/07_translate_apocrypha.py --book Jubi -t 1
  python scripts/07_translate_apocrypha.py --book 4Ezra

AKTUÁLNA KONFIGURÁCIA (LM Studio):
  - Model: Gemma 2 9B Instruct (gemma-2-9b-it)
  - Quantization: Q4_K_M / Q5_K_M
  - Context Length: 2048 tokens
  - Flash Attention: ON
  - Pass 1 (Translation): Preklad z EN/LA do SK
  - Pass 2 (Correction): Teologická a jazyková korektúra
"""

import argparse
import json
import os
import signal
import sys
import threading
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Pridanie koreňového adresára do sys.path pre import config
sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"

# Zámok na vláknovo bezpečný zápis checkpointu do JSON súboru
checkpoint_lock = threading.Lock()


def force_exit_on_ctrl_c(sig, frame):
    """Okamžite ukončí proces pri stlačení Ctrl+C bez čakania na blokované vlákna."""
    print("\n\n" + "!" * 70)
    print(" [PRERUŠENÉ] Preklad bol okamžite zastavený používateľom (Ctrl+C).")
    print(" Všetky doposiaľ preložené verše sú bezpečne uložené v checkpoint JSON súbore.")
    print("!" * 70 + "\n")
    os._exit(0)


# Registrácia signal handlera pre okamžitú reakciu na Ctrl+C (SIGINT)
signal.signal(signal.SIGINT, force_exit_on_ctrl_c)


# Katalóg nekanonických kníh z OCP
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
        "version_priority": ["Greek (English)", "English", "Greek"],
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


def ensure_input_file(book_code: str, book_info: dict) -> Path:
    """Skontroluje prítomnosť XML súboru v data/raw/, ak chýba, stiahne ho."""
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


def call_lmstudio_api(messages: list, temperature: float = 0.1, max_tokens: int = 200) -> str:
    """Univerzálne volanie API v LM Studio."""
    payload = {
        "model": "local-model",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    req = urllib.request.Request(
        LM_STUDIO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            content = res_data["choices"][0]["message"]["content"].strip()
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1].strip()
            return content
    except Exception as e:
        print(f"\n  [CHYBA API] Zlyhal preklad cez LM Studio: {e}")
        print("  Uistite sa, že v LM Studio beží Local Server (http://localhost:1234)!")
        sys.exit(1)


def translate_verse_twopass(text_en: str) -> str:
    """Dvojprechodový preklad: 1. Hrubý preklad, 2. Teologická a gramatická korektúra."""

    # --- PASS 1: HRUBÝ PREKLAD ---
    sys_pass1 = (
        "Si prekladateľ starovekých a biblických textov z angličtiny/latinčiny do slovenčiny. "
        "Prelož verš presne. Vráť IBA preložený slovenský text."
    )
    msg1 = [
        {"role": "system", "content": sys_pass1},
        {"role": "user", "content": f"Prelož do slovenčiny:\n{text_en}"},
    ]
    raw_sk = call_lmstudio_api(msg1, temperature=0.2, max_tokens=200)

# --- PASS 2: GRAMATICKÁ A TEOLOGICKÁ KOREKTÚRA ---
    sys_pass2 = "Si profesionálny slovenský teologický redaktor a jazykový korektor."
    rules_pass2 = (
        "Oprav a vyčisti nasledujúci slovenský preklad apokryfného verša.\n\n"
        "STRIKTNÉ PRAVIDLÁ KOREKTÚRY:\n"
        "1. Odstráň české slová a čechizmy (napr. 'pojďme' -> 'poďme', 'třásenie' -> 'chvenie', 'zrieť' -> 'hľadieť', 'budiž' -> 'nech je', 'moudrosť' -> 'múdrosť').\n"
        "2. Oprav chybné preklady (napr. 'dew' prelož ako 'rosa' [NIKDY NIE rosnička], 'all flesh' ako 'všetci ľudia' alebo 'všetko tvorstvo' [NIKDY NIE pokožka], 'curse' ako 'kliatba').\n"
        "3. Oprav nespisovné tvary, gramatiku a pádovanie (napr. 'Hermonovi hory' -> 'Hermonovej hory', 'zaklínačky' -> 'zaklínadlá', 'nepotrval' -> 'nevytrval si').\n"
        "4. Odstráň vymyslené slovesá a novotvary (napr. 'pochotili', 'zosvorený', 'hriechuť', 'trémať'), doplň chýbajúcu diakritiku a odstráň zdvojené zámená (napr. 'vybrať si si').\n"
        "5. Vráť IBA opravený finálny text verša bez akýchkoľvek poznámok, vysvetlení alebo úvodzoviek.\n\n"
        f"Slovenský text na korektúru:\n{raw_sk}"
    )

    msg2 = [
        {"role": "system", "content": sys_pass2},
        {"role": "user", "content": rules_pass2},
    ]
    clean_sk = call_lmstudio_api(msg2, temperature=0.1, max_tokens=200)

    return clean_sk


def process_single_verse_task(task_data):
    """Pomocná funkcia pre spracovanie jedného verša vo vlákne."""
    chap_num, v_num, raw_text, book_code = task_data
    v_key = f"{chap_num}_{v_num}"

    v_sk_text = translate_verse_twopass(raw_text)
    return chap_num, v_num, v_key, v_sk_text


def save_checkpoint_safe(checkpoint: dict, checkpoint_file: Path):
    """Vláknovo bezpečné uloženie checkpointu."""
    with checkpoint_lock:
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def parse_ocp_xml(root, version_priority):
    """Vyhľadá najvhodnejšiu verziu v OCP XML a vyextrahuje kapitoly a verše."""
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

    text_elem = target_version.find("text") or target_version
    chapters_data = {}

    for chap_div in text_elem.findall("./div"):
        chap_num = chap_div.attrib.get("number")
        if not chap_num:
            continue

        verse_list = []
        for verse_div in chap_div.findall("./div"):
            verse_num = verse_div.attrib.get("number")
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


def main():
    parser = argparse.ArgumentParser(description="Paralelný dvojprechodový prekladač OCP apokryfov do slovenčiny.")
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
        help="Počet paralelných vlákien pre preklad (predvolené: 2)",
    )
    args = parser.parse_args()

    book_code = args.book
    num_threads = max(1, args.threads)
    book_info = APOCRYPHA_BOOKS[book_code]

    print(f"--- Preklad apokryfu (Paralelný Two-Pass): {book_info['name_sk']} ({book_code}) ---")
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
                checkpoint = json.load(f)
        except Exception:
            checkpoint = {}

    unprocessed_tasks = []
    skipped_count = 0

    for chap_num, verses in chapters_data.items():
        for v_num, raw_text in verses:
            v_key = f"{chap_num}_{v_num}"
            if v_key in checkpoint:
                skipped_count += 1
            else:
                unprocessed_tasks.append((chap_num, v_num, raw_text, book_code))

    translated_count = 0
    total_to_translate = len(unprocessed_tasks)

    if skipped_count > 0:
        print(f"Načítaných {skipped_count} veršov z checkpointu.")

    if total_to_translate > 0:
        thread_label = "vlákno" if num_threads == 1 else ("vlákna" if 2 <= num_threads <= 4 else "vlákien")
        print(f"Spúšťam paralelný preklad pre {total_to_translate} veršov ({num_threads} {thread_label})...")

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {
                executor.submit(process_single_verse_task, task): task
                for task in unprocessed_tasks
            }

            for future in as_completed(futures):
                chap_num, v_num, v_key, v_sk_text = future.result()

                checkpoint[v_key] = v_sk_text
                save_checkpoint_safe(checkpoint, checkpoint_file)

                translated_count += 1
                print(f"  [{translated_count}/{total_to_translate}] [OK] {book_code} {chap_num:>3}:{v_num:<3}")

    # Rekonštrukcia finálneho XML súboru v správnom poradí kapitol a veršov
    print("\nVytváram výsledný XML súbor...")
    xml_root_sk = ET.Element("bible")
    book_elem = ET.SubElement(xml_root_sk, "b", n=book_info["name_sk"])

    for chap_num, verses in chapters_data.items():
        c_sk_elem = ET.SubElement(book_elem, "c", n=str(chap_num))
        for v_num, _ in verses:
            v_key = f"{chap_num}_{v_num}"
            v_sk_text = checkpoint.get(v_key, "")
            v_sk_elem = ET.SubElement(c_sk_elem, "v", n=str(v_num))
            v_sk_elem.text = v_sk_text

    output_sk_xml.parent.mkdir(parents=True, exist_ok=True)
    out_tree = ET.ElementTree(xml_root_sk)
    out_tree.write(output_sk_xml, encoding="utf-8", xml_declaration=True)

    print("\n" + "=" * 70)
    print(f"Preklad pre {book_info['name_sk']} bol úspešne dokončený!")
    print(f" - Novopreložených veršov: {translated_count}")
    print(f" - Načítaných z checkpointu: {skipped_count}")
    print(f" - Výsledné XML: {output_sk_xml}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
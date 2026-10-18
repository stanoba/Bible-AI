"""
Univerzálny skript na automatický dvojprechodový paralelný preklad apokryfných kníh 
(1Henoch, Jubileá, atď.) z OCP repozitára do čistej slovenčiny pomocou LM Studio.

Spracovanie prebieha paralelne vo viacero vláknach (nastaviteľné cez argument --threads):
  Pass 1: Hrubý preklad z angličtiny/latinčiny do slovenčiny.
  Pass 2: Jazyková a teologická korektúra (odstránenie čechizmov, oprava slovosledu a diakritiky).

Použitie:
  python scripts/07_translate_apocrypha.py --book 1En --threads 2
  python scripts/07_translate_apocrypha.py --book Jubi -t 1
  python scripts/07_translate_apocrypha.py --book AdamEve --timeout 180 --threads 2

AKTUÁLNA KONFIGURÁCIA (LM Studio):
  - Model: Gemma 2 9B Instruct (gemma-2-9b-it)
  - Quantization: Q4_K_M / Q5_K_M
  - Context Length: 2048+ tokens
  - Flash Attention: ON
  - Pass 1 (Translation): Preklad z EN/LA do SK
  - Pass 2 (Correction): Teologická a jazyková korektúra
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

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
LM_STUDIO_MODELS_URL = "http://localhost:1234/v1/models"

# Zámok na vláknovo bezpečný zápis checkpointu do JSON súboru
checkpoint_lock = threading.Lock()

# Globálny Event na okamžité bezpečné zastavenie všetkých vlákien pri chybe alebo prerušení
stop_event = threading.Event()


def force_exit_on_ctrl_c(sig, frame):
    """Okamžite ukončí proces pri stlačení Ctrl+C bez čakania na blokované vlákna."""
    stop_event.set()
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


# Slovník biblických mien a titulov pre automatický preklad jednoslovných veršov (bez volania LLM)
BIBLICAL_NAMES_SK = {
    # Anglické mená
    "Isaiah": "Izaiáš",
    "Jeremiah": "Jeremiáš",
    "Ezekiel": "Ezechiel",
    "Daniel": "Daniel",
    "Hosea": "Ozeáš",
    "Joel": "Joel",
    "Amos": "Ámos",
    "Obadiah": "Obadiáš",
    "Jonah": "Jonáš",
    "Micah": "Micheáš",
    "Nahum": "Nahum",
    "Habakkuk": "Habakuk",
    "Zephaniah": "Sofoniáš",
    "Haggai": "Aggeus",
    "Zechariah": "Zachariáš",
    "Malachi": "Malachiáš",
    "Nathan": "Nátan",
    "Ahijah": "Achijáš",
    "Ijoel": "Joel",
    "Azariah": "Azariáš",
    "Elijah": "Eliáš",
    "Elisha": "Elizeus",
    "Moses": "Mojžiš",
    "Aaron": "Áron",
    "Adam": "Adam",
    "Eve": "Eva",
    "Seth": "Šét",
    "Cain": "Kain",
    "Abel": "Ábel",
    "Enoch": "Henoch",
    "Methuselah": "Matuzalem",
    "Noah": "Noe",
    "Abraham": "Abrahám",
    "Isaac": "Izák",
    "Jacob": "Jakub",
    "Joseph": "Jozef",
    "David": "Dávid",
    "Solomon": "Šalamún",
    "Job": "Jób",
    "Baruch": "Baruch",
    "Ezra": "Ezdráš",
    "Nehemiah": "Nehemiáš",
    "Tobit": "Tobiáš",
    "Judith": "Judita",
    "Esther": "Ester",
    "Aseneth": "Asenet",
    # Grécke ekvivalenty
    "Ἡσαΐας": "Izaiáš",
    "Ἱερεμίας": "Jeremiáš",
    "Ἰεζεκιήλ": "Ezechiel",
    "Δανιήλ": "Daniel",
    "Ὡσηέ": "Ozeáš",
    "Ἀμώς": "Ámos",
    "Ἰωήλ": "Joel",
    "Ὀβδιού": "Obadiáš",
    "Ἰωνᾶς": "Jonáš",
    "Μιχαίας": "Micheáš",
    "Ναούμ": "Nahum",
    "Ἀμβακούμ": "Habakuk",
    "Σοφονίας": "Sofoniáš",
    "Ἁγγαῖος": "Aggeus",
    "Ζαχαρίας": "Zachariáš",
    "Μαλαχίας": "Malachiáš",
    "Νάθαν": "Nátan",
    "Ἀχιά": "Achijáš",
    "Ἀζαρίας": "Azariáš",
    "Ἠλίας": "Eliáš",
    "Ἐλισαιέ": "Elizeus",
}


def clean_single_word(word: str) -> str:
    """Preloží alebo vyčistí jedno samostatné slovo/meno/lakúnu bez volania LLM."""
    stripped = word.strip(".,;:!?()[]\"' ")
    if not stripped:
        return word.strip()
    return BIBLICAL_NAMES_SK.get(stripped, BIBLICAL_NAMES_SK.get(stripped.capitalize(), word.strip()))


def check_lmstudio_health(timeout: int = 5) -> bool:
    """Overí, či je LM Studio Local Server spustený a dostupný."""
    try:
        req = urllib.request.Request(LM_STUDIO_MODELS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


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


def call_lmstudio_api(
    messages: list,
    temperature: float = 0.1,
    max_tokens: int = 1000,
    timeout: int = 180,
    max_retries: int = 3,
) -> str:
    """
    Univerzálne volanie API v LM Studio s retry mechanizmom, spätným čakaním
    a bezpečným ošetrením chýb bez blokovania či nechceného behu vlákien na pozadí.
    """
    payload = {
        "model": "local-model",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req_data = json.dumps(payload).encode("utf-8")

    for attempt in range(1, max_retries + 1):
        if stop_event.is_set():
            raise RuntimeError("Operácia bola prerušená.")

        try:
            req = urllib.request.Request(
                LM_STUDIO_URL,
                data=req_data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_bytes = resp.read()
                res_data = json.loads(raw_bytes.decode("utf-8"))

                if "error" in res_data:
                    err_msg = res_data["error"].get("message", str(res_data["error"]))
                    raise RuntimeError(f"LM Studio API hlási chybu: {err_msg}")

                if "choices" not in res_data or not res_data["choices"]:
                    raise RuntimeError(f"Neočakávaná odpoveď z LM Studio (chýbajú 'choices'): {res_data}")

                content = res_data["choices"][0]["message"]["content"].strip()
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1].strip()
                return content

        except Exception as e:
            if stop_event.is_set():
                raise RuntimeError("Operácia bola prerušená.")

            if attempt < max_retries:
                backoff_sec = min(20, 2 ** attempt)
                print(f"\n  [POZOR] Dočasná chyba LM Studio ({type(e).__name__}: {e}). Pokus {attempt}/{max_retries}. Opakujem o {backoff_sec}s...")
                for _ in range(backoff_sec * 2):
                    if stop_event.is_set():
                        raise RuntimeError("Operácia bola prerušená počas čakania.")
                    time.sleep(0.5)
            else:
                stop_event.set()
                print(f"\n\n  [CHYBA API] Zlyhal preklad cez LM Studio po {max_retries} pokusoch: {e}")
                print("  Uistite sa, že v LM Studio beží Local Server (http://localhost:1234)!")
                raise RuntimeError(f"LM Studio API zlyhalo po {max_retries} pokusoch: {e}")


def translate_verse_twopass(
    text_en: str,
    timeout: int = 180,
    max_retries: int = 3,
    max_tokens: int = 1000,
) -> str:
    """Dvojprechodový preklad: 1. Hrubý preklad, 2. Prirodzená redakčná korektúra."""
    if stop_event.is_set():
        raise RuntimeError("Operácia bola prerušená.")

    # Ochrana: ak má text len 1 slovo alebo je prázdny, neposielame ho do LLM
    words = text_en.strip().split()
    if len(words) <= 1:
        return clean_single_word(words[0]) if words else text_en.strip()

    # --- PASS 1: HRUBÝ PREKLAD ---
    msg1 = [
        {"role": "system", "content": "Si prekladateľ biblických textov z angličtiny do slovenčiny. Prelož verš presne a doslovne. Vráť IBA preklad."},
        {"role": "user", "content": text_en},
    ]
    raw_sk = call_lmstudio_api(
        msg1,
        temperature=0.1,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )

    if stop_event.is_set():
        raise RuntimeError("Operácia bola prerušená.")

    # --- PASS 2: BILINGVÁLNA KOREKTÚRA ---
    rules_pass2 = (
        "Si slovenský teologický redaktor. Uprav a usmerni slovenský preklad tak, aby presne zodpovedal anglickému originálu a znel plynulo v spisovnej slovenčine.\n\n"
        "DÔLEŽITÉ PRAVIDLÁ:\n"
        "1. PRESNOSŤ VÝZNAMU: Prekladaj slovesá presne podľa anglického originálu. NEPOUŽÍVAJ dookola tie isté frázy (napr. 'zatúžili po', 'zviazať', 'kliatba'), ak nezodpovedajú anglickému slovesu vo vete!\n"
        "2. KONTROLA TEXTU: Nepridávaj do verša ŽIADNE vlastné vety, zhrnutia, mená anjelov ani komentáre, ktoré nie sú v origináli.\n"
        "3. GRAMATIKA A ČECHIZMY: Vždy používa 'kliatba' (NIE kletba), 'poďme' (NIE pojďme), 'Gabriel' (mužský rod). Oprav pádovanie, preklepy a zliate slová.\n"
        "4. Vráť LEN opravený finálny slovenský verš bez úvodzoviek.\n\n"
        f"Anglický originál:\n{text_en}\n\n"
        f"Slovenský preklad na úpravu:\n{raw_sk}"
    )
    msg2 = [
        {"role": "system", "content": "Si profesionálny slovenský jazykový a teologický redaktor."},
        {"role": "user", "content": rules_pass2},
    ]
    clean_sk = call_lmstudio_api(
        msg2,
        temperature=0.1,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )

    return clean_sk


def translate_verse_singlepass(
    text_en: str,
    timeout: int = 180,
    max_retries: int = 3,
    max_tokens: int = 1000,
) -> str:
    """Jednoprechodový preklad: rýchly a priamy preklad s integrovanými pravidlami."""
    if stop_event.is_set():
        raise RuntimeError("Operácia bola prerušená.")

    # Ochrana: ak má text len 1 slovo alebo je prázdny, neposielame ho do LLM
    words = text_en.strip().split()
    if len(words) <= 1:
        return clean_single_word(words[0]) if words else text_en.strip()

    rules = (
        "Prelož nasledujúci staroveký biblický/apokryfný text z angličtiny do spisovnej a vznešenej slovenčiny.\n\n"
        "DÔLEŽITÉ PRAVIDLÁ:\n"
        "1. Zachovaj presný teologický význam a kontext všetkých viet podľa originálu.\n"
        "2. Používaj čistú slovenčinu bez čechizmov (napr. kliatba [nie kletba], poďme [nie pojďme], Gabriel [mužský rod]).\n"
        "3. Nepridávaj do textu žiadne vlastné komentáre, vysvetlivky, zhrnutia ani úvodzovky.\n"
        "4. Vráť VÝHRADNE finálny slovenský text verša.\n\n"
        f"Originálny text na preklad:\n{text_en}"
    )
    msg = [
        {"role": "system", "content": "Si profesionálny prekladateľ biblických a starovekých textov do spisovnej slovenčiny."},
        {"role": "user", "content": rules},
    ]
    return call_lmstudio_api(
        msg,
        temperature=0.1,
        max_tokens=max_tokens,
        timeout=timeout,
        max_retries=max_retries,
    )


def process_single_verse_task(task_data):
    """Pomocná funkcia pre spracovanie jedného verša vo vlákne."""
    if stop_event.is_set():
        return None

    chap_num, v_num, raw_text, book_code, timeout, max_retries, max_tokens, single_pass = task_data
    v_key = f"{chap_num}_{v_num}"

    try:
        if single_pass:
            v_sk_text = translate_verse_singlepass(
                raw_text,
                timeout=timeout,
                max_retries=max_retries,
                max_tokens=max_tokens,
            )
        else:
            v_sk_text = translate_verse_twopass(
                raw_text,
                timeout=timeout,
                max_retries=max_retries,
                max_tokens=max_tokens,
            )
        return chap_num, v_num, v_key, v_sk_text
    except Exception as e:
        stop_event.set()
        raise e


def save_checkpoint_safe(checkpoint: dict, checkpoint_file: Path):
    """Vláknovo bezpečné a atomické uloženie checkpointu."""
    with checkpoint_lock:
        temp_file = checkpoint_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(checkpoint_file)


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
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Timeout pre jednu požiadavku na LM Studio v sekundách (predvolené: 180)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximálny počet pokusov pri výpadku / timeoute (predvolené: 3)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1000,
        help="Maximálny počet tokenov pre generovaný preklad (predvolené: 1000)",
    )
    parser.add_argument(
        "--single-pass",
        "-s",
        action="store_true",
        help="Rýchly jednoprechodový preklad namiesto dvojprechodového (2x rýchlejší, nižšie nároky na VRAM a kontext)",
    )
    args = parser.parse_args()

    book_code = args.book
    num_threads = max(1, args.threads)
    book_info = APOCRYPHA_BOOKS[book_code]

    pass_label = "Single-Pass" if args.single_pass else "Paralelný Two-Pass"
    print(f"--- Preklad apokryfu ({pass_label}): {book_info['name_sk']} ({book_code}) ---")

    # 1. Kontrola dostupnosti LM Studio pred začatím
    if not check_lmstudio_health():
        print("\n" + "!" * 70)
        print(" [CHYBA] LM Studio Local Server nie je spustený alebo neodpovedá!")
        print(" Uistite sa, že v LM Studio beží Local Server na http://localhost:1234")
        print(" a že je načítaný požadovaný model (napr. Gemma 2 9B Instruct).")
        print("!" * 70 + "\n")
        sys.exit(1)

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

            # Ak má verš len 1 slovo alebo je prázdny (napr. meno proroka, lakúna, symbol):
            # Nikdy ho neposielame do LLM, ale vyriešime priamo (alebo preložíme meno).
            if len(words) <= 1:
                existing_val = checkpoint.get(v_key, "").strip()
                # Ak hodnota chýba, alebo v checkpointe z predchádzajúceho behu zostala halucinácia (> 3 slová)
                if not existing_val or len(existing_val.split()) > 3:
                    resolved_text = clean_single_word(words[0]) if words else raw_clean
                    checkpoint[v_key] = resolved_text
                    save_checkpoint_safe(checkpoint, checkpoint_file)
                    auto_resolved_count += 1
                    print(f"  [AUTO] {book_code} {chap_num:>3}:{v_num:<3} (1 slovo): '{raw_clean}' -> '{resolved_text}'")
                skipped_count += 1
                continue

            if v_key in checkpoint:
                skipped_count += 1
            else:
                unprocessed_tasks.append(
                    (chap_num, v_num, raw_text, book_code, args.timeout, args.retries, args.max_tokens, args.single_pass)
                )

    translated_count = 0
    total_to_translate = len(unprocessed_tasks)

    if auto_resolved_count > 0:
        print(f"Automaticky vybavených {auto_resolved_count} jednoslovných veršov/mien bez volania LLM.")

    if skipped_count > 0:
        print(f"Načítaných {skipped_count} veršov z checkpointu.")

    if total_to_translate > 0:
        thread_label = "vlákno" if num_threads == 1 else ("vlákna" if 2 <= num_threads <= 4 else "vlákien")
        print(f"Spúšťam paralelný preklad pre {total_to_translate} veršov ({num_threads} {thread_label})...")
        print(f"Parametre: Timeout={args.timeout}s, Retries={args.retries}, Max-tokens={args.max_tokens}\n")

        executor = ThreadPoolExecutor(max_workers=num_threads)
        futures = {
            executor.submit(process_single_verse_task, task): task
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
                print(f"  [{translated_count}/{total_to_translate}] [OK] {book_code} {chap_num:>3}:{v_num:<3}")

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
            print("Pre pokračovanie znova spustite rovnaký príkaz:")
            print(f"  python scripts/07_translate_apocrypha.py --book {book_code} -t {num_threads}\n")
            sys.exit(1)

    # Overenie, či sú všetky verše preložené pred vygenerovaním XML
    missing_verses = []
    for chap_num, verses in chapters_data.items():
        for v_num, _ in verses:
            v_key = f"{chap_num}_{v_num}"
            if v_key not in checkpoint:
                missing_verses.append(v_key)

    if missing_verses:
        print(f"\n[UPOZORNENIE] V checkpointe chýba ešte {len(missing_verses)} veršov. Výsledné XML sa vygeneruje až po dokončení všetkých veršov.")
        sys.exit(0)

    # Rekonštrukcia finálneho XML súboru v SEB štruktúre
    print("\nVytváram výsledný XML súbor v SEB formáte...")
    
    xml_root_sk = ET.Element("bible", attrib={
        "translation": f"Online Critical Pseudepigrapha ({book_info['name_sk']})",
        "status": "Lokálny dvojprechodový preklad cez LM Studio.",
        "link": book_info.get("url", "")
    })
    
    # Zaradenie pod Starý zákon (alebo príslušný testament)
    testament_elem = ET.SubElement(xml_root_sk, "testament", name="Old")
    
    # Definícia knihy s atribútmi name a code
    book_elem = ET.SubElement(testament_elem, "book", name=book_info["name_sk"], code=book_code)

    for chap_num, verses in chapters_data.items():
        chapter_elem = ET.SubElement(book_elem, "chapter", number=str(chap_num))
        for v_num, _ in verses:
            v_key = f"{chap_num}_{v_num}"
            v_sk_text = checkpoint.get(v_key, "")
            
            verse_elem = ET.SubElement(chapter_elem, "verse", number=str(v_num))
            verse_elem.text = v_sk_text

    output_sk_xml.parent.mkdir(parents=True, exist_ok=True)
    
    # Pretty-print (pekné naformátovanie s odsadením) pomocou minidom
    rough_string = ET.tostring(xml_root_sk, encoding="utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="    ", encoding="utf-8")

    with open(output_sk_xml, "wb") as f:
        f.write(pretty_xml)

    print("\n" + "=" * 70)
    print(f"Preklad pre {book_info['name_sk']} bol úspešne dokončený!")
    print(f" - Celkovo veršov: {len(checkpoint)}")
    print(f" - Výsledné SEB XML: {output_sk_xml}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

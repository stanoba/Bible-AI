import os
import sys
from pathlib import Path

# Nastavenie kódovania konzoly na UTF-8 pre bezproblémové výpisy na Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Základné cesty
BASE_DIR = Path(__file__).parent.resolve()
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_AUDIO_DIR = BASE_DIR / "data" / "audio"
OUTPUTS_DIR = BASE_DIR / "outputs"

MARKDOWN_DIR = OUTPUTS_DIR / "markdown"
SQLITE_DIR = OUTPUTS_DIR / "sqlite"
JSONL_DIR = OUTPUTS_DIR / "jsonl"

# URL adresy externých zdrojov
URL_BIBLE_XML = "https://raw.githubusercontent.com/Beblia/Holy-Bible-XML-Format/refs/heads/master/SlovakianSEBBible.xml"
URL_CROSS_REFS = "https://a.openbible.info/data/cross-references.zip"
URL_GEOCODING = "https://raw.githubusercontent.com/openbibleinfo/Bible-Geocoding-Data/refs/heads/main/data/modern.jsonl"

# Súbory
FILE_BIBLE_XML = DATA_RAW_DIR / "SlovakianSEBBible.xml"
FILE_CROSS_REFS = DATA_RAW_DIR / "cross_references.csv"
FILE_GEOCODING = DATA_RAW_DIR / "modern.jsonl"
FILE_AUDIO_INDEX = DATA_RAW_DIR / "audio_index.json"
FILE_AUDIO_TIMESTAMPS = DATA_RAW_DIR / "audio_timestamps.json"

FILE_SQLITE_DB = SQLITE_DIR / "biblia.sqlite"
FILE_JSONL = JSONL_DIR / "biblia.jsonl"

# Mapovanie: OSIS kód -> Slovenská skratka
OSIS_TO_SK = {
    "Gen": "Gen", "Exod": "Ex", "Lev": "Lev", "Num": "Num", "Deut": "Dtp",
    "Josh": "Joz", "Judg": "Sdc", "Ruth": "Rút", "1Sam": "1 Sam", "2Sam": "2 Sam",
    "1Kings": "1 Kráľ", "2Kings": "2 Kráľ", "1Chron": "1 Kron", "2Chron": "2 Kron",
    "Ezra": "Ezd", "Neh": "Neh", "Esth": "Est", "Job": "Jób", "Ps": "Ž",
    "Prov": "Prís", "Eccl": "Kaz", "Song": "Pieseň", "Isa": "Iz", "Jer": "Jer",
    "Lam": "Plač", "Ezek": "Ez", "Dan": "Dan", "Hos": "Oz", "Joel": "Joel",
    "Amos": "Am", "Obad": "Abd", "Jonah": "Jon", "Mic": "Mik", "Nah": "Nah",
    "Hab": "Hab", "Zeph": "Sof", "Hag": "Ag", "Zech": "Zch", "Mal": "Mal",
    "Matt": "Mt", "Mark": "Mk", "Luke": "Lk", "John": "Ján", "Acts": "Sk",
    "Rom": "Rim", "1Cor": "1 Kor", "2Cor": "2 Kor", "Gal": "Gal", "Eph": "Ef",
    "Phil": "Flp", "Col": "Kol", "1Thess": "1 Sol", "2Thess": "2 Sol",
    "1Tim": "1 Tim", "2Tim": "2 Tim", "Titus": "Tit", "Philem": "Flm",
    "Heb": "Heb", "Jas": "Jak", "1Pet": "1 Pt", "2Pet": "2 Pt",
    "1John": "1 Ján", "2John": "2 Ján", "3John": "3 Ján", "Jude": "Júd", "Rev": "Zjv",
    "Tob": "Tob", "Jdt": "Jdt", "Wis": "Múd", "Sir": "Sir", "Bar": "Bar",
    "1Macc": "1 Mak", "2Macc": "2 Mak"
}

# Mapovanie: Názov v XML -> OSIS kód
SK_NAME_TO_OSIS = {
    "Genezis": "Gen", "Exodus": "Exod", "Levitikus": "Lev", "Numeri": "Num", "Deuteronómium": "Deut",
    "Jozua": "Josh", "Sudcovia": "Judg", "Rút": "Ruth", "Prvá kniha Samuelova": "1Sam", "Druhá kniha Samuelova": "2Sam",
    "Prvá kniha kráľov": "1Kings", "Druhá kniha kráľov": "2Kings", "Prvá kniha kroník": "1Chron", "Druhá kniha kroník": "2Chron",
    "Ezdráš": "Ezra", "Nehemiáš": "Neh", "Estera": "Esth", "Jób": "Job", "Žalmy": "Ps",
    "Príslovia": "Prov", "Kniha kazateľ": "Eccl", "Pieseň piesní": "Song", "Izaiáš": "Isa", "Jeremiáš": "Jer",
    "Plač": "Lam", "Ezechiel": "Ezek", "Daniel": "Dan", "Ozeáš": "Hos", "Joel": "Joel",
    "Amos": "Amos", "Abdiáš": "Obad", "Jonáš": "Jonah", "Micheáš": "Mic", "Naum": "Nah",
    "Habakuk": "Hab", "Sofoniáš": "Zeph", "Aggeus": "Hag", "Zachariáš": "Zech", "Malachiáš": "Mal",
    "Evanjelium podľa Matúša": "Matt", "Evanjelium podľa Marka": "Mark",
    "Evanjelium podľa Lukáša": "Luke", "Evanjelium podľa Jána": "John",
    "Skutky apoštolov": "Acts", "List Rimanom": "Rom", "Prvý list Korinťanom": "1Cor", "Druhý list Korinťanom": "2Cor",
    "List Galaťanom": "Gal", "List Efezanom": "Eph", "List Filipanom": "Phil", "List Kolosanom": "Col",
    "Prvý list Solúnčanom": "1Thess", "Druhý list Solúnčanom": "2Thess",
    "Prvý list Tímoteovi": "1Tim", "Druhý list Tímoteovi": "2Tim", "List Títovi": "Titus", "List Filemonovi": "Philem",
    "List Hebrejom": "Heb", "Jakubov list": "Jas", "Prvý Petrov list": "1Pet", "Druhý Petrov list": "2Pet",
    "Prvý Jánov list": "1John", "Druhý Jánov list": "2John", "Tretí Jánov list": "3John", "Júdov list": "Jude", "Zjavenie apoštola Jána": "Rev",
    "Tobiáš": "Tob", "Judita": "Jdt", "Kniha múdrosti": "Wis", "Kniha Sirachovcova": "Sir", "Baruch": "Bar",
    "Prvá kniha Makabejcov": "1Macc", "Druhá kniha Makabejcov": "2Macc"
}

# Poradie 66 biblických kníh podľa čísla (pre XML formáty, kde majú knihy iba number="1".."66")
BOOK_NUM_TO_INFO = {
    1: ("Genezis", "Gen"), 2: ("Exodus", "Exod"), 3: ("Levitikus", "Lev"), 4: ("Numeri", "Num"), 5: ("Deuteronómium", "Deut"),
    6: ("Jozua", "Josh"), 7: ("Sudcovia", "Judg"), 8: ("Rút", "Ruth"), 9: ("Prvá kniha Samuelova", "1Sam"), 10: ("Druhá kniha Samuelova", "2Sam"),
    11: ("Prvá kniha kráľov", "1Kings"), 12: ("Druhá kniha kráľov", "2Kings"), 13: ("Prvá kniha kroník", "1Chron"), 14: ("Druhá kniha kroník", "2Chron"),
    15: ("Ezdráš", "Ezra"), 16: ("Nehemiáš", "Neh"), 17: ("Estera", "Esth"), 18: ("Jób", "Job"), 19: ("Žalmy", "Ps"),
    20: ("Príslovia", "Prov"), 21: ("Kniha kazateľ", "Eccl"), 22: ("Pieseň piesní", "Song"), 23: ("Izaiáš", "Isa"), 24: ("Jeremiáš", "Jer"),
    25: ("Plač", "Lam"), 26: ("Ezechiel", "Ezek"), 27: ("Daniel", "Dan"), 28: ("Ozeáš", "Hos"), 29: ("Joel", "Joel"),
    30: ("Amos", "Amos"), 31: ("Abdiáš", "Obad"), 32: ("Jonáš", "Jonah"), 33: ("Micheáš", "Mic"), 34: ("Nahum", "Nah"),
    35: ("Habakuk", "Hab"), 36: ("Sofoniáš", "Zeph"), 37: ("Aggeus", "Hag"), 38: ("Zachariáš", "Zech"), 39: ("Malachiáš", "Mal"),
    40: ("Evanjelium podľa Matúša", "Matt"), 41: ("Evanjelium podľa Marka", "Mark"), 42: ("Evanjelium podľa Lukáša", "Luke"), 43: ("Evanjelium podľa Jána", "John"),
    44: ("Skutky apoštolov", "Acts"), 45: ("List Rimanom", "Rom"), 46: ("Prvý list Korinťanom", "1Cor"), 47: ("Druhý list Korinťanom", "2Cor"),
    48: ("List Galaťanom", "Gal"), 49: ("List Efezanom", "Eph"), 50: ("List Filipanom", "Phil"), 51: ("List Kolosanom", "Col"),
    52: ("Prvý list Solúnčanom", "1Thess"), 53: ("Druhý list Solúnčanom", "2Thess"), 54: ("Prvý list Tímoteovi", "1Tim"), 55: ("Druhý list Tímoteovi", "2Tim"),
    56: ("List Títovi", "Titus"), 57: ("List Filemonovi", "Philem"), 58: ("List Hebrejom", "Heb"), 59: ("Jakubov list", "Jas"),
    60: ("Prvý Petrov list", "1Pet"), 61: ("Druhý Petrov list", "2Pet"), 62: ("Prvý Jánov list", "1John"), 63: ("Druhý Jánov list", "2John"),
    64: ("Tretí Jánov list", "3John"), 65: ("Júdov list", "Jude"), 66: ("Zjavenie apoštola Jána", "Rev")
}

# Mapovanie MP3 adresárov na OSIS kód
FOLDER_TO_OSIS = {
    "01_genezis": "Gen", "02_exodus": "Exod", "03_levitikus": "Lev", "04_numeri": "Num", "05_deuternomium": "Deut",
    "06_jozua": "Josh", "07_kniha_sudcov": "Judg", "08_rut": "Ruth", "09_1sam": "1Sam", "10_2sam": "2Sam",
    "11_1kralov": "1Kings", "12_2kralov": "2Kings", "13_1kronik": "1Chron", "14_2kronik": "2Chron",
    "15_ezdras": "Ezra", "16_nehemias": "Neh", "17_ester": "Esth", "18_job": "Job", "19_zalmy": "Ps",
    "20_prislovia": "Prov", "21_kazatel": "Eccl", "22_velpiesen": "Song", "23_izaias": "Isa", "24_jeremias": "Jer",
    "25_nareky": "Lam", "26_ezechiel": "Ezek", "27_daniel": "Dan", "28_ozeas": "Hos", "29_joel": "Joel",
    "30_amos": "Amos", "31_abdias": "Obad", "32_jonas": "Jonah", "33_micheas": "Mic", "34_nahum": "Nah",
    "35_habakuk": "Hab", "36_sofonias": "Zeph", "37_aggeus": "Hag", "38_zacharias": "Zech", "39_malachias": "Mal",
    "40_evanjelium_podla_matusa": "Matt", "41_evanjelium_podla_marka": "Mark", "42_evanjelium_podla_lukasa": "Luke",
    "43_evanjelium_podla_jana": "John", "44_skutky_apostolov": "Acts", "45_list_rimanom": "Rom",
    "46_prvy_list_korintanom": "1Cor", "47_druhy_list_korintanom": "2Cor", "48_list_galatanom": "Gal",
    "49_list_efezanom": "Eph", "50_list_filipanom": "Phil", "51_list_kolosanom": "Col", "52_prvy_list_tesalonicanom": "1Thess",
    "53_druhy_list_tesalonicanom": "2Thess", "54_prvy_list_timotejovi": "1Tim", "55_druhy_list_timotejovi": "2Tim",
    "56_list_titovi": "Titus", "57_list_filemonovi": "Philem", "58_list_hebrejom": "Heb", "59_jakubov_list": "Jas",
    "60_prvy_petrov_list": "1Pet", "61_druhy_petrov_list": "2Pet", "62_prvy_janov_list": "1John",
    "63_druhy_janov_list": "2John", "64_treti_janov_list": "3John", "65_judov_list": "Jude", "66_zjavenie_jana": "Rev",
    "1_dt_tobias": "Tob", "2_dt_judita": "Jdt", "3_dt_ester_gretska": "Esth", "4_dt_kniha_mudrosti": "Wis",
    "5_dt_kniha_sirachovca": "Sir", "6_dt_baruch": "Bar", "7_dt_pridavky_daniel": "Dan",
    "8_dt_prva_makabejcov": "1Macc", "9_dt_druha_makabejcov": "2Macc"
}


def parse_bible_elements(root):
    """
    Univerzálny extraktor kníh, kapitol a veršov pre rôzne XML schémy:
    1. Schema Beblia (<b>, <c>, <v> s atribútom 'n')
    2. Schema SEB (<book>, <chapter>, <verse> s atribútom 'number')
    Vráti štruktúru: zoznam objektov {
        'book_name': ...,
        'osis_code': ...,
        'chapters': [
            {
                'chapter_num': int,
                'verses': [
                    {'verse_num': int, 'text': str}
                ]
            }
        ]
    }
    """
    books = root.findall(".//book")
    if not books:
        books = root.findall(".//b")

    result = []
    for b_idx, book_el in enumerate(books, start=1):
        # Názov a OSIS kód
        b_name = book_el.attrib.get("n", "").strip()
        b_num_str = book_el.attrib.get("number", "").strip()
        
        if b_name and b_name in SK_NAME_TO_OSIS:
            osis_code = SK_NAME_TO_OSIS[b_name]
        elif b_num_str and b_num_str.isdigit() and int(b_num_str) in BOOK_NUM_TO_INFO:
            b_name, osis_code = BOOK_NUM_TO_INFO[int(b_num_str)]
        elif b_idx in BOOK_NUM_TO_INFO:
            b_name, osis_code = BOOK_NUM_TO_INFO[b_idx]
        else:
            b_name = b_name or f"Kniha_{b_idx}"
            osis_code = SK_NAME_TO_OSIS.get(b_name, f"B{b_idx}")

        chap_elements = book_el.findall(".//chapter")
        if not chap_elements:
            chap_elements = book_el.findall(".//c")

        chapters_data = []
        for c_idx, chap_el in enumerate(chap_elements, start=1):
            c_num_str = chap_el.attrib.get("number") or chap_el.attrib.get("n") or str(c_idx)
            try:
                c_num = int(c_num_str)
            except ValueError:
                c_num = c_idx

            verse_elements = chap_el.findall(".//verse")
            if not verse_elements:
                verse_elements = chap_el.findall(".//v")

            verses_data = []
            for v_idx, verse_el in enumerate(verse_elements, start=1):
                v_num_str = verse_el.attrib.get("number") or verse_el.attrib.get("n") or str(v_idx)
                try:
                    v_num = int(v_num_str)
                except ValueError:
                    v_num = v_idx

                v_text = (verse_el.text or "").strip()
                verses_data.append({"verse_num": v_num, "text": v_text})

            chapters_data.append({"chapter_num": c_num, "verses": verses_data})

        result.append({
            "book_name": b_name,
            "osis_code": osis_code,
            "chapters": chapters_data
        })

    return result

# Bible AI Pipeline (Slovenská Biblia pre AI modely a e-čítačky)

![Bible AI Pipeline](title.jpg)

Automatizovaná dátová pipeline na predspracovanie a obohatenie textu Biblie (Slovenský ekumenický / katolícky preklad), apokryfných kníh (1En, Jubi, SibOr, LivPro, AdamEve atď.), krížových odkazov (OpenBible.info cross-references), geografických GPS dát, lokálnych MP3 audio nahrávok a generovanie plnohodnotných **EPUB3 e-kníh**.

Výsledné dáta sú pripravené pre:

1. **E-čítačky a Calibre** (Interaktívne EPUB3 e-knihy s krížovými odkazmi, automatickými obálkami z `assets/` a tirážou).
2. **Google NotebookLM** (štruktúrovaný Markdown rozdelený do súborov v limite 50 zdrojov).
3. **Antigravity / SQL agentov** (SQLite databáza s FTS5 full-textovým indexom).
4. **Vektorové databázy / RAG** (JSONL formát pripravený pre ChromaDB, Pinecone, Qdrant).

---

## ⚖️ Disclaimer & Autorské práva (Copyright)

Tento projekt je **bezplatný open-source** (vydaný pod licenciou MIT) vytvorený výhradne na výskumné, študijné, vzdelávacie a nekomerčné účely. Neobsahuje žiadne priame speňaženie a kód je verejne prístupný pre komunitu.

Pri používaní projektu a jeho dát, prosím, berte na vedomie nasledovné:

### 1. Autorské práva na texty a preklady

* **Slovenský ekumenický preklad (SEB):** Texty sú chránené autorským zákonom a patria ich príslušným držiteľom práv (Slovenská biblická spoločnosť). Surový XML súbor `SlovakianSEBBible.xml` ani MP3 nahrávky **nie sú priamou súčasťou tohto git repozitára** z dôvodu ochrany autorských práv. Pipeline je navrhnutá tak, aby si oprávnený používateľ stiahol/pripravil tieto súbory do svojho lokálneho prostredia sám (napr. cez `task download` z voľne dostupných internetových zdrojov alebo vlastným importom).
* **OCP Apokryfy / Pseudepigrafy (napr. 1En, Jubi, SibOr):** Sú prekladané z historických, verejne dostupných (public domain) anglických a kritických predlôh (Online Critical Pseudepigrapha). Slovenský preklad týchto apokryfov je generovaný AI modelmi alebo oficiálnym prekladateľským rozhraním pod **MIT licenciou** (*Copyright (c) 2026 Bible AI Contributors*).

### 2. Audio nahrávky

* MP3 súbory a CD nahrávky spomenuté v projekte sú chránené autorským právom ich autorov a vydavateľov. Tento repozitár slúži len ako nástroj (pipeline) na analýzu, indexáciu a generovanie časových značiek (alignment) pre lokálne súbory, ktoré používateľ už legálne vlastní.

### 3. Použitie AI (Umelá inteligencia) a Záruky

* Preklady apokryfov a obohatené metadáta sú generované prostredníctvom veľkých jazykových modelov (LLM) alebo prekladateľských API (DeepL). Hoci prebieha korektúra a kontrola, AI môže generovať nepresnosti alebo halucinácie.
* Tento softvér je poskytovaný „tak, ako je“ (as is), bez akejkoľvek záruky. Autori projektu nenesú žiadnu zodpovednosť za akékoľvek porušenie autorských práv tretích strán spôsobené nesprávnym alebo komerčným šírením dát získaných prostredníctvom tejto pipeline.

---

## 📁 Štruktúra projektu

```text
bible-ai/
├── Taskfile.yml                  # Automatizácia úloh (taskfile.dev)
├── config.py                     # Cesty, URL adresy a mapovania OSIS kódov
├── requirements.txt              # Závislosti (ebooklib, deepl, atď.)
├── assets/                       # Titulné obrázky/obálky pre EPUB e-knihy (SlovakianSEBBible.jpg, 1En_sk.jpg, SibOr_sk.jpg)
├── data/
│   ├── raw/                      # Surové stiahnuté dáta a prekladové checkpointy
│   │   ├── SlovakianSEBBible.xml # XML text Biblie
│   │   ├── cross_references.csv  # Krížové odkazy s váhami (OpenBible)
│   │   └── modern.jsonl          # GPS geokódovanie biblických miest
│   └── audio/                    # Priečinky s MP3 nahrávkami (CD 1 až 8 + Dt)
├── scripts/
│   ├── 01_download.py            # Stiahnutie XML Biblie, cross-references a geodát
│   ├── 02_parse_audio.py         # Preskenovanie MP3 súborov a namapovanie na knihy/kapitoly
│   ├── 03_build_markdown.py      # Generovanie Markdownu s odkazmi a mapami pre NotebookLM
│   ├── 04_build_sqlite.py        # Generovanie SQLite databázy s FTS5 indexom
│   ├── 05_build_jsonl.py         # Generovanie JSONL súboru pre vektorové vkladanie (embeddings)
│   ├── 06_align_audio.py         # Extrakcia časových značiek veršov z MP3 cez faster-whisper
│   ├── 07_translate_apocrypha.py # Paralelný dvojprechodový preklad OCP apokryfov cez LM Studio
│   ├── 08_build_epub.py          # Generovanie EPUB3 e-kníh s obálkami a krížovými odkazmi
│   ├── 09_translate_deepl.py     # Rýchly preklad OCP apokryfov cez DeepL API
│   └── 10_translate_gemini.py    # Priamy verný preklad z gréčtiny a latinčiny cez Google Gemini API
└── outputs/
    ├── markdown/                 # Markdown súbory (Biblia_Cast_01.md .. 07.md)
    ├── sqlite/                   # Databáza biblia.sqlite
    ├── jsonl/                    # Dataset biblia.jsonl
    └── epub/                     # Vygenerované EPUB e-knihy (SlovakianSEBBible.epub, SibOr_sk.epub...)

```

---

## 🚀 Rýchle spustenie

Celý proces riadi nástroj [Task](https://taskfile.dev/):

### Zoznam dostupných príkazov

```bash
task
# alebo
task --list

```

### Spustenie celej pipeline naraz

```bash
task build

```

Príkaz automaticky:

1. Skontroluje a stiahne chýbajúce externé zdroje (`data/raw/`).
2. Preskenuje a indexuje lokálne MP3 súbory (`data/audio/`).
3. Vygeneruje Markdown súbory v `outputs/markdown/`.
4. Vytvorí SQLite databázu v `outputs/sqlite/biblia.sqlite`.
5. Vygeneruje JSONL súbor v `outputs/jsonl/biblia.jsonl`.
6. Vygeneruje EPUB3 e-knihy v `outputs/epub/`.

---

## 🌐 Preklad apokryfov cez DeepL API (`scripts/09_translate_deepl.py`)

Pre dosiahnutie špičkovej štylistickej kvality prekladu v slovenčine a vysokú rýchlosť spracovania je v pipeline k dispozícii skript `09_translate_deepl.py`.

### Kľúčové vlastnosti prekladača:

* **Paralelné spracovanie:** Využíva viacvláknový `ThreadPoolExecutor` pre bleskový preklad celých kníh.
* **Resilience & Checkpointing:** Priebežne ukladá preložené verše do `data/raw/<BOOK>_checkpoint.json`. Pri prerušení alebo výpadku siete plynule nadviaže bez opätovného míňania znakového limitu.
* **Odolnosť voči zamknutým súborom na Windowse:** Atomický zápis s retrom bráni chybám typu `[WinError 5] Access is denied`.
* **Automatické ošetrenie Rate-Limitov:** Pri dočasnom preťažení serverov DeepL (HTTP 429) skript automaticky aplikuje stupňovité čakanie (exponential backoff) a pokus bezpečne zopakuje.

### Nastavenie API kľúča:

Získajte bezplatný API kľúč na stránke [DeepL API Free](https://www.deepl.com/pro-api) (obsahuje **500 000 znakov mesačne zadarmo**) a nastavte ho ako premennú prostredia:

* **Windows (PowerShell):** `$env:DEEPL_API_KEY="VÁŠ_DEEPL_API_KĽÚČ"`
* **Linux / macOS:** `export DEEPL_API_KEY="VÁŠ_DEEPL_API_KĽÚČ"`

### Príkazy na preklad:

```bash
# Preklad Sibiliných proroctiev (SibOr)
python scripts/09_translate_deepl.py --book SibOr -t 2

# Preklad 1. knihy Henochovej (1En)
python scripts/09_translate_deepl.py --book 1En -t 2

# Preklad Životov prorokov (LivPro)
python scripts/09_translate_deepl.py --book LivPro -t 2

```

---

## 📚 Generovanie EPUB e-kníh (`scripts/08_build_epub.py`)

Skript `08_build_epub.py` umožňuje vytvárať štandardizované **EPUB3 e-knihy** optimalizované pre čítačky **Kindle, Kobo, PocketBook, Apple Books a Calibre**.

### Kľúčové vlastnosti EPUB generátora:

* **Automatické priradenie obálky (Cover Art):** Ak sa v priečinku `assets/` nachádza obrázok zodpovedajúci názvu XML súboru (napr. `assets/SlovakianSEBBible.jpg` alebo `assets/SibOr_sk.jpg`), automaticky ho nastaví ako oficiálnu obálku balíčka a zároveň ho vloží ako prvá vizuálna strana e-knihy.
* **Podpora nečíselných kapitol:** Bezpečne spracováva aj prológy a textové identifikátory kapitol (napr. `number="Prologue"` v apokryfoch).
* **Interaktívne krížové odkazy:** Krížové referencie z OpenBible sa prevádzajú na klikateľné HTML hyperlinky (`<a href="matt.xhtml#v_2_1">Mt 2,1</a>`). Kliknutím v e-čítačke okamžite skočíte na cieľový verš.
* **Stromový obsah (TOC):** Pre celú SEB Bibliu vygeneruje trojúrovňový strom (Stará zmluva, Deuterokánonické knihy, Nová zmluva) s funkčnými kategóriami.
* **Automatická tiráž a licencia:** Každá e-kniha obsahuje stranu *O týmto vydaní* s informáciami o licencii (MIT pre AI preklady, autorské práva SEB pre Bibliu).

### Príkazy na vygenerovanie EPUB:

```bash
# Vygenerovanie štandardnej SEB Biblie
python scripts/08_build_epub.py

# Vygenerovanie apokryfnej knihy (napr. Sibiline proroctvá)
python scripts/08_build_epub.py --xml data/raw/SibOr_sk.xml

# Vygenerovanie 1. knihy Henochovej
python scripts/08_build_epub.py --xml data/raw/1En_sk.xml

```

---

## 🤖 Lokálny preklad cez LM Studio (`scripts/07_translate_apocrypha.py`)

Pre plne offline lokálny preklad pomocou vlastnej GPU karta je k dispozícii skript `07_translate_apocrypha.py`.

* **Odporúčaný model:** `gemma-2-9b-it` (Gemma 2 9B Instruct) alebo `Qwen2.5-32B-Instruct`
* **Kontextové okno:** `2048+`
* **GPU Offload:** `100 % (MAX)`
* **Temperature:** `0.1`

```bash
python scripts/07_translate_apocrypha.py --book 1En -t 2

```

---

## ⚡ Priamy preklad z gréčtiny a latinčiny cez Gemini API (`scripts/10_translate_gemini.py`)

Pre najvyššiu možnú teologickú a textovú vernosť slúži `10_translate_gemini.py`. Na rozdiel od sprostredkovaných prekladov z angličtiny (kde vznikajú nepresnosti a anachronizmy) prekladá model **priamo zo starovekej gréčtiny (Koine) alebo latinčiny** do bohatej slovenskej biblickej terminológie.

### Kľúčové výhody:
* **Jazyková priorita originálov:** Skript prioritne vyberá grécke a latinské texty OCP repozitára pred anglickými verziami.
* **Prirodzený biblický slovník:** Presne prekladá biblické idiómy (napr. *prepílený vo dvoje*, *archa zmluvy*, *vyvieranie Siloe*, *hadobijci*).
* **Dávkové spracovanie (Batching):** Prekladá text v dávkach po 50 veršov cez štruktúrovaný JSON, čo zaručuje bleskovú rýchlosť a ukladanie priebežného checkpointu.
* **Model:** Predvolene využíva najnovší **`gemini-3.8-flash`**.

### Nastavenie API kľúča:
Získajte bezplatný API kľúč na [Google AI Studio](https://aistudio.google.com/) a nastavte premennú:
* **Windows (PowerShell):** `$env:GEMINI_API_KEY="VÁŠ_GEMINI_API_KĽÚČ"`
* **Linux / macOS:** `export GEMINI_API_KEY="VÁŠ_GEMINI_API_KĽÚČ"`

### Príklady spustenia:
```bash
# Preklad Životov prorokov z gréckeho originálu
python scripts/10_translate_gemini.py --book LivPro

# Preklad Sibiliných proroctiev
python scripts/10_translate_gemini.py --book SibOr

# Preklad Prvej knihy Henochovej
python scripts/10_translate_gemini.py --book 1En --model gemini-3.8-flash
```

---

## 🛠️ Jednotlivé úlohy

| Úloha | Príkaz | Popis |
| --- | --- | --- |
| **Stiahnutie dát** | `task download` | Stiahne XML Biblie, zip krížových odkazov a súbor `modern.jsonl`. |
| **Indexovanie audia** | `task parse-audio` | Preskenuje MP3 súbory v `data/audio/` a vytvorí `audio_index.json`. |
| **Časové značky (Whisper)** | `task align-audio` | Vygeneruje časové značky veršov z MP3 cez faster-whisper. |
| **Generovanie MD** | `task markdown` | Vytvorí Markdown pre NotebookLM s odkazmi na verše, audio a Google Mapy. |
| **Generovanie SQLite** | `task sqlite` | Vytvorí `biblia.sqlite` s tabuľkou veršov a full-textovým vyhľadávaním (FTS5). |
| **Generovanie JSONL** | `task jsonl` | Vytvorí `biblia.jsonl` pre vektorové vyhľadávanie a trénovanie. |
| **Generovanie EPUB** | `task epub` | Vygeneruje EPUB3 e-knihu s obálkou, tirážou a krížovými odkazmi. |
| **Preklad cez Gemini API** | `python scripts/10_translate_gemini.py --book LivPro` | Priamy a najvernejší preklad z gréčtiny a latinčiny cez Google Gemini API. |
| **Preklad cez DeepL** | `python scripts/09_translate_deepl.py --book SibOr -t 2` | Rýchly preklad OCP apokryfu do slovenčiny cez oficiálne DeepL API. |
| **Preklad cez LM Studio** | `python scripts/07_translate_apocrypha.py --book 1En -t 2` | Offline dvojprechodový preklad OCP apokryfu cez lokálny LLM model. |
| **Kompletný proces (All)** | `task all` | Spustí end-to-end proces od nuly (clean -> download -> parse-audio -> align-audio -> build). |
| **Kompletné prečistenie** | `task clean` | Vymaže stiahnuté dáta v `data/raw/` aj výstupy v `outputs/` (audio v `data/audio/` a `audio_timestamps.json` ponechá). |
| **Prečistenie výstupov** | `task clean-outputs` | Vymaže iba priečinky v `outputs/` (ponechá surové XML, referencie, GPS, audio aj časové značky). |

---

## 🔍 Ako používovať výstupy

### 1. E-čítačky (Kindle / Kobo / Calibre)

* Otvorte súbory z `outputs/epub/` v aplikácii Calibre alebo ich nahrajte priamo do svojej čítačky.
* Kniha obsahuje plne funkčný systémový obsah kapitol (TOC), titulný cover, tiráž s licenciou a klikateľné krížové referencie medzi veršami.

### 2. Google NotebookLM

* Nahrajte vygenerované súbory z `outputs/markdown/` (cca 7 súborov, limit je 50 zdrojov).
* AI má v jednom textovom bloku samotný verš, krížové referencie *(porov. ...)*, lokáciu s GPS odkazom na Google Maps a cestu k lokálnej audio nahrávke.

### 3. Antigravity / SQLite

Databáza obsahuje tabuľku `verses` a virtuálnu tabuľku `verses_fts`:

```sql
-- Rýchle vyhľadanie podľa knihy, kapitoly a verša
SELECT * FROM verses WHERE osis_code = 'Matt' AND chapter = 2;

-- Full-textové vyhľadávanie
SELECT v.book, v.chapter, v.verse, v.text 
FROM verses_fts f
JOIN verses v ON f.rowid = v.id
WHERE verses_fts MATCH 'Betlehem';

```

### 4. Vektorové databázy (ChromaDB / LangChain)

Každý riadok v `outputs/jsonl/biblia.jsonl` predstavuje jeden verš s metadátami:

```json
{
  "id": "Matt_2_1",
  "book": "Evanjelium podľa Matúša",
  "code": "Mt",
  "osis": "Matt",
  "chapter": 2,
  "verse": 1,
  "text": "Keď sa Ježiš narodil v judskom Betleheme za čias kráľa Herodesa...",
  "audio_file": "data/audio/CD 7 Evanjelia a Skutky/mp3/40_evanjelium_podla_matusa/40_mt_02.mp3"
}

```

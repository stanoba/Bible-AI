import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from ebooklib import epub

# Pridáme koreňový adresár do sys.path pre import config
sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Vytvoríme reverzné mapovanie zo slovenských skratiek na OSIS kódy
SK_TO_OSIS = {}
if hasattr(config, "OSIS_TO_SK"):
    SK_TO_OSIS = {v: k for k, v in config.OSIS_TO_SK.items()}


def parse_universal_bible_xml(root):
    """
    Univerzálny parser podporujúci SEB Bibliu aj apokryfy (1En_sk.xml, Jubi_sk.xml).
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
                for chapter in book.findall("chapter") + book.findall("c"):
                    chap_num = int(chapter.attrib.get("number") or chapter.attrib.get("n", 1))

                    verses = []
                    for verse in chapter.findall("verse") + chapter.findall("v"):
                        v_num = int(verse.attrib.get("number") or verse.attrib.get("n", 1))
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


MIN_CROSS_REF_VOTES = 10


def load_cross_references():
    """Načíta krížové odkazy z CSV súboru do slovníka (filtruje hlasy ≥ MIN_CROSS_REF_VOTES)."""
    cross_refs = defaultdict(list)
    csv_path = config.FILE_CROSS_REFS

    if not csv_path.exists():
        print(f"Upozornenie: Súbor s krížovými odkazmi neexistuje: {csv_path}")
        return cross_refs

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                from_ref = row.get("From Verse", "").strip()
                to_ref = row.get("To Verse", "").strip()
                votes_str = row.get("Votes", "0").strip()
                try:
                    votes = int(votes_str)
                except ValueError:
                    votes = 0
                if from_ref and to_ref and votes >= MIN_CROSS_REF_VOTES:
                    cross_refs[from_ref].append(to_ref)
        print(f"  -> Načítaných {len(cross_refs)} veršov s krížovými odkazmi (min. hlasy: {MIN_CROSS_REF_VOTES}).")
    except Exception as e:
        print(f"Upozornenie: Nepodarilo sa načítať krížové odkazy: {e}")

    return cross_refs


def parse_osis_ref(osis_ref):
    """
    Rozloží OSIS referenciu (napr. 'Matt.2.1' alebo 'Gen.1.1-Gen.1.3') na OSIS kód, kapitolu a verš.
    """
    parts = osis_ref.split("-")[0].split(".")
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return parts[0], parts[1], "1"
    return None, None, None


def format_cross_ref_link(to_ref):
    """Vytvorí HTML interaktívny odkaz (<a href="...">) pre krížovú referenciu."""
    book_osis, chap, verse = parse_osis_ref(to_ref)
    if not book_osis:
        return to_ref

    sk_code = config.OSIS_TO_SK.get(book_osis, book_osis)
    filename = f"{book_osis.lower()}.xhtml"
    anchor = f"v_{chap}_{verse}"

    return f'<a href="{filename}#{anchor}" class="xref-link">{sk_code} {chap},{verse}</a>'


def get_standard_osis_code(book_info):
    """
    Zabezpečí prevod slovenskej skratky alebo kódovania knihy na oficiálny OSIS kód (napr. Gen, Matt).
    """
    code = book_info.get("osis_code", "")

    # 1. Priamy prevod zo slovenského kódovania (napr. 'Gn' -> 'Gen')
    if code in SK_TO_OSIS:
        return SK_TO_OSIS[code]

    # 2. Prevod podľa OSIS_TO_SK (ak kód je už OSIS kľúčom)
    if hasattr(config, "OSIS_TO_SK") and code in config.OSIS_TO_SK:
        return code

    return code


def create_epub_style():
    """Vytvorí CSS štýl pre typografiu, titulný obrázok a odkazovanie v e-knihe."""
    style = """
    @namespace epub "http://www.idpf.org/2007/ops";
    body {
        font-family: Georgia, "Times New Roman", serif;
        padding: 0 5%;
        line-height: 1.5;
    }
    .cover-container {
        text-align: center;
        margin: 0;
        padding: 0;
        height: 100vh;
    }
    .cover-image {
        max-width: 100%;
        max-height: 100%;
        height: auto;
        width: auto;
    }
    .about-page {
        padding: 1em 0;
    }
    .about-page h2 {
        border-bottom: 2px solid #8b0000;
        padding-bottom: 0.3em;
        margin-top: 1.5em;
    }
    .about-page p {
        margin-bottom: 1em;
        text-align: justify;
    }
    .disclaimer-box {
        background-color: #f8f9fa;
        border-left: 4px solid #8b0000;
        padding: 0.8em 1em;
        margin: 1.5em 0;
        font-size: 0.95em;
    }
    h1 {
        text-align: center;
        text-transform: uppercase;
        margin-top: 2em;
        margin-bottom: 1em;
        color: #1a1a1a;
    }
    h2 {
        text-align: center;
        font-size: 1.2em;
        margin-top: 1.5em;
        margin-bottom: 0.8em;
        border-bottom: 1px solid #ccc;
        padding-bottom: 0.2em;
        color: #333333;
    }
    p.verse-para {
        text-indent: 0;
        margin-bottom: 0.5em;
        text-align: justify;
    }
    sup.v-num {
        font-size: 0.75em;
        font-weight: bold;
        color: #8b0000;
        margin-right: 0.3em;
    }
    span.cross-refs {
        font-size: 0.85em;
        color: #555555;
        font-style: italic;
        margin-left: 0.4em;
    }
    a.xref-link {
        color: #0056b3;
        text-decoration: none;
        border-bottom: 1px dotted #0056b3;
    }
    a.xref-link:hover {
        text-decoration: underline;
    }
    """
    return epub.EpubItem(
        uid="style_nav",
        file_name="style/style.css",
        media_type="text/css",
        content=style
    )


def find_cover_image(stem_name):
    """
    Hľadá titulný obrázok v adresári assets/ pre daný názov XML (napr. assets/SlovakianSEBBible.jpg).
    """
    assets_dir = config.BASE_DIR / "assets"
    if not assets_dir.exists():
        return None

    extensions = [".jpg", ".jpeg", ".png"]
    for ext in extensions:
        cover_file = assets_dir / f"{stem_name}{ext}"
        if cover_file.exists():
            return cover_file
    return None


def create_about_page(stem_name, title, style_item):
    """
    Vytvorí stranu s informáciami o vydaní, autorských právach a licencii.
    """
    about_item = epub.EpubHtml(
        title="O tomto vydaní",
        file_name="about_page.xhtml",
        lang="sk"
    )
    about_item.add_item(style_item)

    if stem_name == "SlovakianSEBBible":
        html_content = f"""
        <div class="about-page">
            <h2>Informácie o vydaní a autorských právach</h2>
            <p><strong>Titul:</strong> {title}</p>
            <p><strong>Preklad:</strong> Slovenský ekumenický preklad (SEB)</p>
            <p><strong>Autorské práva k prekladu:</strong> © Slovenská biblická spoločnosť. Všetky práva vyhradené.</p>
            
            <div class="disclaimer-box">
                <p><strong>Upozornenie o použití:</strong> Tento digitálny súbor bol vygenerovaný pre osobnú potrebu, štúdium a akademický výskum pomocou automatizovanej dátovej pipeline projektu <strong>Bible AI</strong>. Tento súbor nie je určený na komerčné šírenie ani predaj.</p>
            </div>

            <h2>Kód a nástroje</h2>
            <p>Dátové skripty a konverzný kód sú licencované pod <strong>MIT License</strong> (<em>Copyright (c) 2026 Bible AI Contributors</em>).</p>
            <p>Vytvorené pomocou projektu <a href="https://github.com/stanoba/bible-ai">Bible AI</a>.</p>
        </div>
        """
    else:
        html_content = f"""
        <div class="about-page">
            <h2>Informácie o vydaní a licencii</h2>
            <p><strong>Titul:</strong> {title}</p>
            <p><strong>Pôvodný text:</strong> Public Domain (voľné dielo)</p>
            <p><strong>Slovenský preklad:</strong> Vygenerované pomocou umelej inteligencie (AI) z anglických, latinských a gréckych prameňov v rámci projektu <strong>Bible AI</strong>.</p>

            <div class="disclaimer-box">
                <p><strong>Upozornenie:</strong> Preklad bol spracovaný automatizovanými modelmi AI a je určený predovšetkým na študijné, výskumné a osobné účely. Mnoho pasáží môže obsahovať štylistické alebo terminologické nepresnosti.</p>
            </div>

            <h2>Licencia</h2>
            <p>Tento slovenský preklad a sprievodný kód sú licencované pod <strong>MIT License</strong>:</p>
            <p><em>Copyright (c) 2026 Bible AI Contributors</em></p>
            <p>Vytvorené pomocou projektu <a href="https://github.com/stanoba/bible-ai">Bible AI</a>.</p>
        </div>
        """

    about_item.content = html_content
    return about_item


def main():
    parser = argparse.ArgumentParser(description="Generovanie EPUB e-knihy s krížovými odkazmi.")
    parser.add_argument(
        "--xml",
        type=str,
        default=str(config.FILE_BIBLE_XML),
        help="Cesta k XML súboru (predvolené: štandardná Biblia)"
    )
    args = parser.parse_args()

    xml_path = Path(args.xml)
    print(f"--- 8. Generovanie EPUB (vstup: {xml_path.name}) ---")

    epub_dir = config.BASE_DIR / "outputs" / "epub"
    epub_dir.mkdir(parents=True, exist_ok=True)

    if not xml_path.exists():
        print(f"Chyba: Súbor {xml_path} neexistuje!")
        return

    tree = ET.parse(xml_path)
    root = tree.getroot()

    books_data = parse_universal_bible_xml(root)
    if not books_data:
        print("Chyba: Nepodarilo sa parsovať žiadne knihy zo zadaného XML.")
        return

    # Načítanie krížových odkazov
    cross_refs = load_cross_references()

    # Určenie presného názvu výstupného súboru
    output_filename = f"{xml_path.stem}.epub"
    output_filepath = epub_dir / output_filename

    # Názov knižného diela
    if xml_path.stem == "SlovakianSEBBible":
        title = "Slovenská Biblia (SEB)"
    else:
        book_title = books_data[0]["book_name"] if books_data else xml_path.stem
        title = f"{book_title} (Slovenský preklad)"

    # Inicializácia EPUB objektu
    book = epub.EpubBook()
    book.set_identifier(f"bible-ai-{xml_path.stem.lower()}")
    book.set_title(title)
    book.set_language("sk")
    book.add_author("Slovenská biblická spoločnosť / OCP / Bible AI")

    # Pridanie CSS štýlov
    style_item = create_epub_style()
    book.add_item(style_item)

    # Pridanie titulnej obálky (ak existuje v assets/)
    cover_file = find_cover_image(xml_path.stem)
    cover_html_item = None

    if cover_file:
        print(f"  -> Pridávam titulnú obálku z: {cover_file}")
        with open(cover_file, "rb") as cf:
            cover_bytes = cf.read()
            cover_filename = f"cover_img{cover_file.suffix}"
            book.set_cover(cover_filename, cover_bytes)

        cover_html_item = epub.EpubHtml(
            title="Obálka",
            file_name="title_page.xhtml",
            lang="sk"
        )
        cover_html_item.add_item(style_item)
        cover_html_item.content = f"""
        <div class="cover-container">
            <img src="{cover_filename}" alt="Obálka" class="cover-image" />
        </div>
        """
        book.add_item(cover_html_item)

    # Pridanie tirážnej strany "O tomto vydaní"
    about_item = create_about_page(xml_path.stem, title, style_item)
    book.add_item(about_item)

    epub_chapters = []
    toc = [about_item]

    print(f"Spracovávam {len(books_data)} kníh do EPUB formátu...")

    for book_info in books_data:
        book_name = book_info["book_name"]
        osis_code = get_standard_osis_code(book_info)

        html_filename = f"{osis_code.lower()}.xhtml"
        epub_chap = epub.EpubHtml(
            title=book_name,
            file_name=html_filename,
            lang="sk"
        )
        epub_chap.add_item(style_item)

        content = [f"<h1>{book_name}</h1>"]

        for chapter in book_info["chapters"]:
            chap_num = chapter["chapter_num"]
            chapter_title = f"{book_name} {chap_num}"
            content.append(f'<h2 id="chap_{chap_num}">{chapter_title}</h2>')

            for verse in chapter["verses"]:
                v_num = verse["verse_num"]
                v_text = verse["text"]

                osis_key = f"{osis_code}.{chap_num}.{v_num}"
                refs_list = cross_refs.get(osis_key, [])

                refs_html = ""
                if refs_list:
                    formatted_links = [format_cross_ref_link(r) for r in refs_list[:5]]
                    refs_html = f' <span class="cross-refs">(porov. {", ".join(formatted_links)})</span>'

                verse_id = f"v_{chap_num}_{v_num}"
                content.append(
                    f'<p class="verse-para" id="{verse_id}"><sup class="v-num">{v_num}</sup>{v_text}{refs_html}</p>'
                )

        epub_chap.content = "".join(content)
        book.add_item(epub_chap)
        epub_chapters.append(epub_chap)
        toc.append(epub_chap)

    # Nastavenie obsahu (TOC) a navigácie
    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Nastavenie poradia čítania (spine): Obálka -> O tomto vydaní -> Navigácia -> Kapitoly
    spine_items = []
    if cover_html_item:
        spine_items.append(cover_html_item)
    spine_items.append(about_item)
    spine_items.extend(["nav"] + epub_chapters)
    book.spine = spine_items

    # Zápis výstupného EPUB súboru
    epub.write_epub(output_filepath, book, {})

    print(f"  [OK] EPUB súbor bol úspešne vygenerovaný: {output_filepath}\n")


if __name__ == "__main__":
    main()
    
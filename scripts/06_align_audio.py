"""
Skript na extrakciu časových značiek (timestamps) veršov z MP3 audio nahrávok pomocou Whisperu (faster-whisper).

Použitie:
  python scripts/06_align_audio.py --book Gen --chapter 1
  python scripts/06_align_audio.py --book Matt --chapter 1 --model small
  python scripts/06_align_audio.py --all --limit 5
"""

import argparse
import difflib
import json
import re
import sys
import xml.etree.ElementTree as ET
import os
from pathlib import Path

# Vypnutie varovania o symlinkoch na Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Kompatibilita pre novšie verzie PyAV (av>=14), kde bol odstránený parameter metadata_errors
try:
    import av
    _orig_av_open = av.open
    def _patched_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)
    av.open = _patched_av_open
except ImportError:
    pass

# Pridanie koreňového adresára do sys.path pre import config
sys.path.append(str(Path(__file__).parent.parent.resolve()))
import config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def format_timestamp(seconds: float) -> str:
    """Prevedie sekundy (float) na formát MM:SS.ss alebo HH:MM:SS.ss."""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{int(h):02d}:{int(m):02d}:{s:05.2f}"
    return f"{int(m):02d}:{s:05.2f}"


def normalize_word(text: str) -> str:
    """Odstráni interpunkciu a prevedie na malé písmená pre porovnanie."""
    return re.sub(r"[^\w\s]", "", text).lower().strip()


def load_bible_verses():
    """Načíta verše Biblie z XML rozdelené podľa kľúča (osis_code, chapter_num)."""
    if not config.FILE_BIBLE_XML.exists():
        print(f"Chyba: Súbor {config.FILE_BIBLE_XML} neexistuje! Najprv spustite 'task download'.")
        sys.exit(1)

    tree = ET.parse(config.FILE_BIBLE_XML)
    root = tree.getroot()
    books = config.parse_bible_elements(root)

    verses_by_chapter = {}
    for book in books:
        osis = book["osis_code"]
        for chap in book["chapters"]:
            c_num = chap["chapter_num"]
            key = f"{osis}_{c_num}"
            verses_by_chapter[key] = {
                "book_name": book["book_name"],
                "osis_code": osis,
                "chapter_num": c_num,
                "verses": chap["verses"]  # list of {'verse_num': ..., 'text': ...}
            }
    return verses_by_chapter


def align_transcription_to_verses(transcribed_words, expected_verses):
    """
    Zarovná prúd prepísaných slov z Whisperu s očakávanými veršami kapitoly.
    transcribed_words: list dictov {'word': str, 'start': float, 'end': float}
    expected_verses: list dictov {'verse_num': int, 'text': str}
    """
    clean_transcribed = [
        {"word": normalize_word(w["word"]), "raw": w["word"], "start": w["start"], "end": w["end"]}
        for w in transcribed_words
        if normalize_word(w["word"])
    ]

    aligned_results = {}
    t_idx = 0
    total_t_words = len(clean_transcribed)

    for v_idx, v in enumerate(expected_verses):
        v_num = v["verse_num"]
        v_text = v["text"]
        v_words = [normalize_word(w) for w in v_text.split() if normalize_word(w)]

        if not v_words or t_idx >= total_t_words:
            # Fallback ak už nie sú slová
            last_end = clean_transcribed[-1]["end"] if clean_transcribed else 0.0
            aligned_results[str(v_num)] = {
                "verse_num": v_num,
                "text": v_text,
                "start": round(last_end, 2),
                "end": round(last_end, 2),
                "start_formatted": format_timestamp(last_end),
                "end_formatted": format_timestamp(last_end),
                "confidence": 0.0
            }
            continue

        # Nájdeme najlepšiu začiatočnú pozíciu pre daný verš v okne od t_idx
        anchor_len = min(4, len(v_words))
        anchor_tokens = v_words[:anchor_len]

        best_pos = t_idx
        best_score = 0.0

        # Prehľadávame dopredu v okne nasledujúcich slov
        search_window = min(total_t_words, t_idx + 80)
        for cand_pos in range(t_idx, search_window):
            window_tokens = [clean_transcribed[k]["word"] for k in range(cand_pos, min(total_t_words, cand_pos + anchor_len))]
            ratio = difflib.SequenceMatcher(None, " ".join(anchor_tokens), " ".join(window_tokens)).ratio()
            if ratio > best_score:
                best_score = ratio
                best_pos = cand_pos
                if ratio > 0.8:
                    break

        # Nastavíme štart na nájdenú pozíciu
        verse_start_idx = best_pos if best_score >= 0.4 else t_idx
        verse_start_time = clean_transcribed[verse_start_idx]["start"]

        # Odhadneme koniec verša podľa počtu slov
        est_words = len(v_words)
        verse_end_idx = min(total_t_words - 1, verse_start_idx + est_words - 1)

        # Spresnenie konca pomocou posledných slov verša
        tail_len = min(4, len(v_words))
        tail_tokens = v_words[-tail_len:]
        tail_best_pos = verse_end_idx
        tail_best_score = 0.0

        tail_search_start = max(verse_start_idx, verse_end_idx - 10)
        tail_search_end = min(total_t_words, verse_end_idx + 15)

        for cand_end in range(tail_search_start, tail_search_end):
            window_tail = [clean_transcribed[k]["word"] for k in range(max(0, cand_end - tail_len + 1), cand_end + 1)]
            ratio = difflib.SequenceMatcher(None, " ".join(tail_tokens), " ".join(window_tail)).ratio()
            if ratio > tail_best_score:
                tail_best_score = ratio
                tail_best_pos = cand_end
                if ratio > 0.8:
                    break

        if tail_best_score >= 0.4:
            verse_end_idx = tail_best_pos

        verse_end_time = clean_transcribed[verse_end_idx]["end"]
        if verse_end_time < verse_start_time:
            verse_end_time = verse_start_time + 1.0

        aligned_results[str(v_num)] = {
            "verse_num": v_num,
            "text": v_text,
            "start": round(verse_start_time, 2),
            "end": round(verse_end_time, 2),
            "start_formatted": format_timestamp(verse_start_time),
            "end_formatted": format_timestamp(verse_end_time),
            "confidence": round((best_score + tail_best_score) / 2 if tail_best_score else best_score, 2)
        }

        # Posunieme index pre ďalší verš
        t_idx = max(t_idx + 1, verse_end_idx + 1)

    return aligned_results


def process_chapter(model, key: str, audio_rel_path: str, chapter_data: dict):
    """Spracuje jednu kapitolu cez faster-whisper a vráti štruktúru časových značiek."""
    audio_full_path = config.BASE_DIR / audio_rel_path
    if not audio_full_path.exists():
        print(f"  [CHYBA] Audio súbor neexistuje: {audio_full_path}")
        return None

    print(f"\n>> Spracovávam: {chapter_data['book_name']} {chapter_data['chapter_num']} ({key})")
    print(f"   Audio: {audio_rel_path}")

    # Spustenie Whisperu s word timestamps
    segments, info = model.transcribe(
        str(audio_full_path),
        language="sk",
        task="transcribe",
        word_timestamps=True,
        vad_filter=True
    )

    all_words = []
    full_text_segments = []
    for segment in segments:
        full_text_segments.append(segment.text.strip())
        if segment.words:
            for w in segment.words:
                all_words.append({
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": getattr(w, "probability", 1.0)
                })

    print(f"   Prepísaných {len(all_words)} slov, celková dĺžka: {format_timestamp(info.duration)}")

    # Zarovnanie slov s očakávanými veršami
    expected_verses = chapter_data["verses"]
    aligned_verses = align_transcription_to_verses(all_words, expected_verses)

    return {
        "book": chapter_data["book_name"],
        "osis_code": chapter_data["osis_code"],
        "chapter": chapter_data["chapter_num"],
        "audio_file": audio_rel_path,
        "duration_seconds": round(info.duration, 2),
        "duration_formatted": format_timestamp(info.duration),
        "total_verses": len(expected_verses),
        "verses": aligned_verses
    }


def main():
    parser = argparse.ArgumentParser(description="Extrakcia časových značiek veršov z MP3 cez faster-whisper.")
    parser.add_argument("--book", "-b", help="OSIS kód alebo názov knihy (napr. Gen, Matt, Genezis)")
    parser.add_argument("--chapter", "-c", type=int, help="Číslo kapitoly")
    parser.add_argument("--model", "-m", default="base", choices=["tiny", "base", "small", "medium", "large-v3"], help="Veľkosť Whisper modelu (predvolené: base)")
    parser.add_argument("--device", "-d", default="auto", choices=["auto", "cuda", "cpu"], help="Zariadenie (auto, cuda, cpu)")
    parser.add_argument("--all", action="store_true", help="Spracovať všetky dostupné kapitoly")
    parser.add_argument("--limit", "-l", type=int, default=None, help="Limit na počet spracovaných kapitol")
    parser.add_argument("--output", "-o", default=str(config.FILE_AUDIO_TIMESTAMPS), help="Cesta k výslednému JSON súboru")

    args = parser.parse_args()

    # Kontrola dostupnosti faster_whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("\n" + "=" * 70)
        print("CHYBA: Knižnica 'faster-whisper' nie je nainštalovaná.")
        print("Pre extrakciu časových značiek ju nainštalujte príkazom:")
        print("    pip install faster-whisper")
        print("=" * 70 + "\n")
        sys.exit(1)

    # Načítanie audio indexu a textov Biblie
    if not config.FILE_AUDIO_INDEX.exists():
        print("Audio index neexistuje! Spúšťam '02_parse_audio.py'...")
        import subprocess
        subprocess.run([sys.executable, str(config.BASE_DIR / "scripts" / "02_parse_audio.py")], check=True)

    with open(config.FILE_AUDIO_INDEX, "r", encoding="utf-8") as f:
        audio_index = json.load(f)

    verses_by_chapter = load_bible_verses()

    # Filtrovanie kapitol na spracovanie
    targets = []
    target_osis = None
    if args.book:
        target_osis = config.SK_NAME_TO_OSIS.get(args.book, args.book)

    for key, audio_path in audio_index.items():
        osis_code, chap_num_str = key.split("_")
        chap_num = int(chap_num_str)

        if target_osis and osis_code != target_osis:
            continue
        if args.chapter and chap_num != args.chapter:
            continue
        if key in verses_by_chapter:
            targets.append((key, audio_path, verses_by_chapter[key]))

    if not targets:
        print(f"Nenašli sa žiadne kapitoly pre zadané parametre (book={args.book}, chapter={args.chapter}).")
        return

    if args.limit:
        targets = targets[:args.limit]

    print(f"Spúšťam extrakciu časových značiek pre {len(targets)} kapitol pomocou faster-whisper (model: {args.model})...")

    # Inicializácia modelu
    compute_type = "float16" if args.device == "cuda" else "int8"
    model = WhisperModel(args.model, device=args.device, compute_type=compute_type)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Načítame doterajšie značky (aby sme neprepísali už skôr spracované kapitoly)
    existing_timestamps = {}
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing_timestamps = json.load(f)
        except Exception:
            existing_timestamps = {}

    processed_count = 0
    for key, audio_path, chap_data in targets:
        result = process_chapter(model, key, audio_path, chap_data)
        if result:
            existing_timestamps[key] = result
            processed_count += 1

            # Ukážka prvých troch veršov na konzole
            print(f"   [OK] Zarovnaných {len(result['verses'])} veršov:")
            for v_num in list(result["verses"].keys())[:3]:
                v_info = result["verses"][v_num]
                print(f"        Verš {v_num:>2}: {v_info['start_formatted']} -> {v_info['end_formatted']} ({v_info['text'][:40]}...)")

            # Ukladanie priebežne po každej kapitole
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(existing_timestamps, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(f"Hotovo! Spracovaných {processed_count} kapitol.")
    print(f"Časové značky boli uložené do: {output_path}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

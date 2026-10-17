"""
Skript na extrakciu časových značiek (timestamps) veršov z MP3 audio nahrávok pomocou Whisperu (faster-whisper).

Použitie:
  python scripts/06_align_audio.py --book Gen --chapter 1
  python scripts/06_align_audio.py --book Matt --chapter 1 --model small
  python scripts/06_align_audio.py --all --limit 5
  python scripts/06_align_audio.py --all --force
"""

import argparse
import difflib
import json
import os
import re
import site
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Vypnutie varovania o symlinkoch na Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Automatické pridanie CUDA DLL z pip balíčkov do PATH na Windowse (nvidia-cublas-cu12, nvidia-cudnn-cu12)
if os.name == "nt":
    for site_pkg in site.getsitepackages():
        cublas_path = os.path.join(site_pkg, "nvidia", "cublas", "bin")
        cudnn_path = os.path.join(site_pkg, "nvidia", "cudnn", "bin")
        if os.path.exists(cublas_path):
            os.add_dll_directory(cublas_path)
            os.environ["PATH"] += os.pathsep + cublas_path
        if os.path.exists(cudnn_path):
            os.add_dll_directory(cudnn_path)
            os.environ["PATH"] += os.pathsep + cudnn_path

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

        anchor_len = min(4, len(v_words))
        anchor_tokens = v_words[:anchor_len]

        best_pos = t_idx
        best_score = 0.0

        search_window = min(total_t_words, t_idx + 80)
        for cand_pos in range(t_idx, search_window):
            window_tokens = [clean_transcribed[k]["word"] for k in range(cand_pos, min(total_t_words, cand_pos + anchor_len))]
            ratio = difflib.SequenceMatcher(None, " ".join(anchor_tokens), " ".join(window_tokens)).ratio()
            if ratio > best_score:
                best_score = ratio
                best_pos = cand_pos
                if ratio > 0.8:
                    break

        verse_start_idx = best_pos if best_score >= 0.4 else t_idx
        verse_start_time = clean_transcribed[verse_start_idx]["start"]

        est_words = len(v_words)
        verse_end_idx = min(total_t_words - 1, verse_start_idx + est_words - 1)

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

    # Spustenie Whisperu s word timestamps a beam_size=1 pre 2x-3x rýchlejší prepis
    segments, info = model.transcribe(
        str(audio_full_path),
        language="sk",
        task="transcribe",
        word_timestamps=True,
        vad_filter=True,
        beam_size=1
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
    parser.add_argument("--workers", "-w", type=int, default=None, help="Počet paralelných vlákien (predvolené: 4 pre GPU, 2 pre CPU)")
    parser.add_argument("--all", action="store_true", help="Spracovať všetky dostupné kapitoly")
    parser.add_argument("--limit", "-l", type=int, default=None, help="Limit na počet spracovaných kapitol")
    parser.add_argument("--force", "-f", action="store_true", help="Vynútiť spracovanie aj pre už existujúce kapitoly v JSON")
    parser.add_argument("--output", "-o", default=str(config.FILE_AUDIO_TIMESTAMPS), help="Cesta k výslednému JSON súboru")

    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("\n" + "=" * 70)
        print("CHYBA: Knižnica 'faster-whisper' nie je nainštalovaná.")
        print("Pre extrakciu časových značiek ju nainštalujte príkazom:")
        print("    pip install faster-whisper")
        print("=" * 70 + "\n")
        sys.exit(1)

    if not config.FILE_AUDIO_INDEX.exists():
        print("Audio index neexistuje! Spúšťam '02_parse_audio.py'...")
        import subprocess
        subprocess.run([sys.executable, str(config.BASE_DIR / "scripts" / "02_parse_audio.py")], check=True)

    with open(config.FILE_AUDIO_INDEX, "r", encoding="utf-8") as f:
        audio_index = json.load(f)

    verses_by_chapter = load_bible_verses()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Načítanie doterajších výstupov pre možnosť nadviazania na prerušený proces
    existing_timestamps = {}
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing_timestamps = json.load(f)
        except Exception:
            existing_timestamps = {}

    targets = []
    target_osis = None
    if args.book:
        target_osis = config.SK_NAME_TO_OSIS.get(args.book, args.book)

    skipped_count = 0
    for key, audio_path in audio_index.items():
        osis_code, chap_num_str = key.split("_")
        chap_num = int(chap_num_str)

        if target_osis and osis_code != target_osis:
            continue
        if args.chapter and chap_num != args.chapter:
            continue
        if key in verses_by_chapter:
            # Ak kapitola už v JSON existuje a nezadali sme --force, preskočíme ju
            if key in existing_timestamps and not args.force:
                skipped_count += 1
                continue
            targets.append((key, audio_path, verses_by_chapter[key]))

    if skipped_count > 0:
        print(f"[INFO] Preskočených {skipped_count} už spracovaných kapitol.")

    if not targets:
        print("Všetky požadované kapitoly sú už spracované! (Pre opätovné spracovanie použite parameter --force)")
        return

    if args.limit:
        targets = targets[:args.limit]

    requested_device = args.device
    if requested_device == "auto":
        requested_device = "cuda"

    if args.workers:
        workers = args.workers
    else:
        workers = 4 if requested_device == "cuda" else 2

    # Načítanie modelu s fallbackom na CPU
    try:
        compute_type = "float16" if requested_device == "cuda" else "int8"
        print(f"Pripravujem Whisper model '{args.model}' na zariadení: {requested_device} ({workers} workerov)...")
        model = WhisperModel(
            args.model,
            device=requested_device,
            compute_type=compute_type,
            num_workers=workers
        )
    except Exception as e:
        if requested_device == "cuda":
            print(f"\n[INFO] Akcelerácia CUDA zlyhala alebo chýbajú knižnice ({e}). Prepínam na CPU...")
            workers = args.workers if args.workers else 2
            model = WhisperModel(
                args.model,
                device="cpu",
                compute_type="int8",
                num_workers=workers
            )
        else:
            raise e

    def worker_task(target):
        key, audio_path, chap_data = target
        return key, process_chapter(model, key, audio_path, chap_data)

    print(f"Spúšťam extrakciu časových značiek pre {len(targets)} kapitol v {workers} paralelných vláknach...")

    processed_count = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker_task, t) for t in targets]
        for future in futures:
            key, result = future.result()
            if result:
                existing_timestamps[key] = result
                processed_count += 1

                print(f"   [OK] Zarovnaných {len(result['verses'])} veršov pre {key}:")
                for v_num in list(result["verses"].keys())[:2]:
                    v_info = result["verses"][v_num]
                    print(f"        Verš {v_num:>2}: {v_info['start_formatted']} -> {v_info['end_formatted']} ({v_info['text'][:40]}...)")

                # Priebežné ukladanie po každej kapitole
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(existing_timestamps, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(f"Hotovo! Novospracovaných {processed_count} kapitol.")
    print(f"Časové značky boli uložené do: {output_path}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
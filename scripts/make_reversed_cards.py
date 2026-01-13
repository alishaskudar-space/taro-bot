from pathlib import Path
from PIL import Image

def main():
    cards_dir = Path("cards")  # <-- если у тебя папка с картами не ./cards, поменяй здесь
    if not cards_dir.exists():
        raise SystemExit(f"Folder not found: {cards_dir.resolve()}")

    exts = {".jpg", ".jpeg", ".png", ".webp"}
    src_files = [
        p for p in cards_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in exts
        and not p.stem.lower().endswith("_rev")
    ]

    made = 0
    for src in src_files:
        dst = src.with_name(f"{src.stem}_rev{src.suffix.lower()}")

        # не перезаписываем, если уже есть
        if dst.exists():
            continue

        with Image.open(src) as im:
            im = im.rotate(180, expand=True)

            # если JPEG, сохраняем с нормальным качеством
            if dst.suffix.lower() in {".jpg", ".jpeg"}:
                im.save(dst, quality=92, optimize=True, progressive=True)
            else:
                im.save(dst)

        made += 1

    print(f"Source files: {len(src_files)}")
    print(f"Created rev : {made}")

if __name__ == "__main__":
    main()

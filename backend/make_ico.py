"""
Конвертер PNG/JPG -> ICO для ярлыка Windows.

Пример:
    cd backend
    python make_ico.py assets\\logo.png assets\\maltruand.ico
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python make_ico.py <input.png/jpg> <output.ico>")
        return 2

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if not src.exists():
        print(f"Input not found: {src}")
        return 1

    try:
        from PIL import Image
    except Exception as e:
        print("Pillow is not installed. Install: pip install Pillow")
        print(e)
        return 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGBA")
    # Набор размеров для Windows-иконок
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(dst, format="ICO", sizes=sizes)
    print(f"✅ ICO saved: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



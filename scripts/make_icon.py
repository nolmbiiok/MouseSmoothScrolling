from pathlib import Path

from PIL import Image, ImageDraw


ROOT_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT_DIR / "assets"
ICON_PATH = ASSETS_DIR / "mousesmoothwheel.ico"


def make_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    scale = size / 32

    # Background
    draw.rounded_rectangle(
        [
            int(1 * scale),
            int(1 * scale),
            int(31 * scale),
            int(31 * scale),
        ],
        radius=int(7 * scale),
        fill=(37, 99, 235, 255),
    )

    # Mouse body
    draw.rounded_rectangle(
        [
            int(10 * scale),
            int(5 * scale),
            int(22 * scale),
            int(27 * scale),
        ],
        radius=int(6 * scale),
        outline=(255, 255, 255, 255),
        width=max(1, int(2 * scale)),
    )

    # Wheel
    draw.line(
        [
            int(16 * scale),
            int(8 * scale),
            int(16 * scale),
            int(13 * scale),
        ],
        fill=(255, 255, 255, 255),
        width=max(1, int(2 * scale)),
    )

    # Smooth scroll waves
    draw.arc(
        [
            int(4 * scale),
            int(16 * scale),
            int(15 * scale),
            int(27 * scale),
        ],
        start=250,
        end=70,
        fill=(125, 211, 252, 255),
        width=max(1, int(2 * scale)),
    )

    draw.arc(
        [
            int(17 * scale),
            int(16 * scale),
            int(28 * scale),
            int(27 * scale),
        ],
        start=110,
        end=290,
        fill=(125, 211, 252, 255),
        width=max(1, int(2 * scale)),
    )

    return image


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    icon_16 = make_icon(16)
    icon_32 = make_icon(32)
    icon_48 = make_icon(48)
    icon_64 = make_icon(64)

    icon_64.save(
        ICON_PATH,
        format="ICO",
        sizes=[
            (16, 16),
            (32, 32),
            (48, 48),
            (64, 64),
        ],
        append_images=[
            icon_16,
            icon_32,
            icon_48,
        ],
    )

    print(f"Created: {ICON_PATH}")


if __name__ == "__main__":
    main()
from __future__ import annotations

import argparse
import random
from pathlib import Path

import cv2


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def yolo_to_xyxy(
    x_center: float,
    y_center: float,
    box_width: float,
    box_height: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    x1 = int((x_center - box_width / 2.0) * image_width)
    y1 = int((y_center - box_height / 2.0) * image_height)
    x2 = int((x_center + box_width / 2.0) * image_width)
    y2 = int((y_center + box_height / 2.0) * image_height)

    x1 = max(0, min(x1, image_width - 1))
    y1 = max(0, min(y1, image_height - 1))
    x2 = max(0, min(x2, image_width - 1))
    y2 = max(0, min(y2, image_height - 1))

    return x1, y1, x2, y2


def draw_yolo_boxes(image_path: Path, label_path: Path, class_name: str = "people"):
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"Could not read image: {image_path}")

    image_height, image_width = image.shape[:2]

    if label_path.exists():
        for raw_line in label_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            try:
                _, x_center, y_center, box_width, box_height = map(float, parts[:5])
            except ValueError:
                continue

            x1, y1, x2, y2 = yolo_to_xyxy(
                x_center, y_center, box_width, box_height, image_width, image_height
            )

            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                image,
                class_name,
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

    return image


def collect_images(dataset_dir: Path, split: str) -> list[Path]:
    image_dir = dataset_dir / split / "images"
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir}")

    images = [
        path
        for path in sorted(image_dir.iterdir())
        if path.suffix.lower() in IMAGE_EXTENSIONS and path.is_file()
    ]
    if not images:
        raise ValueError(f"No images found in: {image_dir}")

    return images


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="View a YOLO dataset split with bounding boxes."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("combined_dataset"),
        help="Path to combined dataset",
    )
    parser.add_argument(
        "--split",
        choices=["train", "valid", "test"],
        default="train",
        help="Dataset split",
    )
    parser.add_argument("--shuffle", action="store_true", help="Shuffle image order")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    images = collect_images(args.dataset, args.split)
    if args.shuffle:
        random.shuffle(images)

    window_name = f"Dataset Viewer ({args.split})"
    index = 0

    while True:
        image_path = images[index]
        label_path = args.dataset / args.split / "labels" / f"{image_path.stem}.txt"

        image = draw_yolo_boxes(image_path, label_path)
        status = f"{args.split} | {index + 1}/{len(images)} | {image_path.name}"

        cv2.putText(
            image,
            status,
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

        cv2.imshow(window_name, image)
        key = cv2.waitKey(0) & 0xFF

        if key in (ord("q"), 27):
            break
        if key in (ord("n"), ord("d"), 83):
            index = (index + 1) % len(images)
            continue
        if key in (ord("p"), ord("a"), 81):
            index = (index - 1) % len(images)
            continue

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

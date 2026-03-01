from __future__ import annotations

import argparse
import ast
import shutil
from dataclasses import dataclass
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
DATASET_CLASS_FILTERS = {"prjc.v1i.yolo26": "head"}


@dataclass
class DatasetValidation:
    path: Path
    class_names: list[str]
    class_ids: set[int]
    valid: bool
    keep_class_name: str | None = None
    keep_class_id: int | None = None
    reason: str = ""


def _parse_dataset_yaml(dataset_dir: Path) -> tuple[int | None, list[str]]:
    yaml_path = dataset_dir / "data.yaml"
    if not yaml_path.exists():
        return None, []

    nc_value: int | None = None
    names_value: list[str] = []

    for line in yaml_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("nc:"):
            raw = stripped.split(":", 1)[1].strip()
            try:
                nc_value = int(raw)
            except ValueError:
                nc_value = None
        elif stripped.startswith("names:"):
            raw = stripped.split(":", 1)[1].strip()
            try:
                parsed = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                parsed = []

            if isinstance(parsed, list):
                names_value = [str(item) for item in parsed]
            elif isinstance(parsed, dict):
                names_value = [str(parsed[k]) for k in sorted(parsed)]
            else:
                names_value = []

    return nc_value, names_value


def _extract_class_ids(label_file: Path) -> set[int]:
    class_ids: set[int] = set()
    for line in label_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        first_token = stripped.split()[0]
        try:
            class_ids.add(int(float(first_token)))
        except ValueError:
            continue
    return class_ids


def validate_dataset(
    dataset_dir: Path, keep_class_name: str | None = None
) -> DatasetValidation:
    nc, names = _parse_dataset_yaml(dataset_dir)
    label_files = sorted(dataset_dir.glob("**/labels/*.txt"))

    class_ids: set[int] = set()
    for label_file in label_files:
        class_ids.update(_extract_class_ids(label_file))

    if nc is None:
        return DatasetValidation(
            path=dataset_dir,
            class_names=names,
            class_ids=class_ids,
            valid=False,
            keep_class_name=keep_class_name,
            reason="missing or invalid nc in data.yaml",
        )

    if keep_class_name is not None:
        if keep_class_name not in names:
            return DatasetValidation(
                path=dataset_dir,
                class_names=names,
                class_ids=class_ids,
                valid=False,
                keep_class_name=keep_class_name,
                reason=f"target class '{keep_class_name}' not found in names",
            )

        keep_class_id = names.index(keep_class_name)
        max_allowed_class_id = len(names) - 1
        out_of_range_ids = sorted(
            class_id
            for class_id in class_ids
            if class_id < 0 or class_id > max_allowed_class_id
        )
        if out_of_range_ids:
            return DatasetValidation(
                path=dataset_dir,
                class_names=names,
                class_ids=class_ids,
                valid=False,
                keep_class_name=keep_class_name,
                keep_class_id=keep_class_id,
                reason=f"label files contain out-of-range class ids {out_of_range_ids}",
            )

        return DatasetValidation(
            path=dataset_dir,
            class_names=names,
            class_ids=class_ids,
            valid=True,
            keep_class_name=keep_class_name,
            keep_class_id=keep_class_id,
            reason=f"keeping only class '{keep_class_name}'",
        )

    if nc != 1:
        return DatasetValidation(
            path=dataset_dir,
            class_names=names,
            class_ids=class_ids,
            valid=False,
            keep_class_name=keep_class_name,
            reason=f"nc is {nc}, expected 1",
        )

    if len(names) != 1:
        return DatasetValidation(
            path=dataset_dir,
            class_names=names,
            class_ids=class_ids,
            valid=False,
            keep_class_name=keep_class_name,
            reason=f"names has {len(names)} items, expected 1",
        )

    if class_ids and class_ids != {0}:
        return DatasetValidation(
            path=dataset_dir,
            class_names=names,
            class_ids=class_ids,
            valid=False,
            keep_class_name=keep_class_name,
            reason=f"label files contain class ids {sorted(class_ids)}, expected only 0",
        )

    return DatasetValidation(
        path=dataset_dir,
        class_names=names,
        class_ids=class_ids,
        valid=True,
        keep_class_name=keep_class_name,
    )


def _rewrite_label_to_people(
    source_label: Path, destination_label: Path, keep_class_id: int | None = None
) -> None:
    rewritten_lines: list[str] = []
    for line in source_label.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            rewritten_lines.append("")
            continue

        tokens = stripped.split()
        if not tokens:
            rewritten_lines.append("")
            continue

        if keep_class_id is not None:
            try:
                class_id = int(float(tokens[0]))
            except ValueError:
                continue
            if class_id != keep_class_id:
                continue

        tokens[0] = "0"
        rewritten_lines.append(" ".join(tokens))

    destination_label.write_text(
        "\n".join(rewritten_lines) + ("\n" if rewritten_lines else ""), encoding="utf-8"
    )


def merge_datasets(
    raw_data_dir: Path,
    output_dir: Path,
    split_names: tuple[str, ...] = ("train", "valid", "test"),
    skip_invalid: bool = False,
) -> None:
    dataset_dirs = sorted(path for path in raw_data_dir.iterdir() if path.is_dir())
    validations = [
        validate_dataset(
            dataset_dir, keep_class_name=DATASET_CLASS_FILTERS.get(dataset_dir.name)
        )
        for dataset_dir in dataset_dirs
    ]

    invalid = [item for item in validations if not item.valid]
    if invalid and not skip_invalid:
        details = "\n".join(f"- {item.path.name}: {item.reason}" for item in invalid)
        raise ValueError(
            "One or more datasets are not single-class. "
            "Fix them first or rerun with --skip-invalid.\n"
            f"{details}"
        )

    selected = [item for item in validations if item.valid]
    skipped = [item for item in validations if not item.valid]

    if not selected:
        raise ValueError("No valid single-class datasets found to merge.")

    if output_dir.exists():
        shutil.rmtree(output_dir)

    for split in split_names:
        (output_dir / split / "images").mkdir(parents=True, exist_ok=True)
        (output_dir / split / "labels").mkdir(parents=True, exist_ok=True)

    copied = {split: 0 for split in split_names}

    for validation in selected:
        dataset_dir = validation.path
        prefix = dataset_dir.name.replace(" ", "_")

        for split in split_names:
            source_images = dataset_dir / split / "images"
            source_labels = dataset_dir / split / "labels"
            if not source_images.exists():
                continue

            for image_file in sorted(source_images.iterdir()):
                if (
                    not image_file.is_file()
                    or image_file.suffix.lower() not in IMAGE_EXTENSIONS
                ):
                    continue

                merged_stem = f"{prefix}__{image_file.stem}"
                destination_image = (
                    output_dir
                    / split
                    / "images"
                    / f"{merged_stem}{image_file.suffix.lower()}"
                )
                destination_label = output_dir / split / "labels" / f"{merged_stem}.txt"

                shutil.copy2(image_file, destination_image)

                source_label = source_labels / f"{image_file.stem}.txt"
                if source_label.exists():
                    _rewrite_label_to_people(
                        source_label,
                        destination_label,
                        keep_class_id=validation.keep_class_id,
                    )
                else:
                    destination_label.write_text("", encoding="utf-8")

                copied[split] += 1

    data_yaml = (
        "train: ../train/images\n"
        "val: ../valid/images\n"
        "test: ../test/images\n\n"
        "nc: 1\n"
        "names: ['people']\n"
    )
    (output_dir / "data.yaml").write_text(data_yaml, encoding="utf-8")

    print("Validation results:")
    for result in validations:
        status = "OK" if result.valid else "SKIP"
        print(
            f"- [{status}] {result.path.name} | names={result.class_names} "
            f"| class_ids={sorted(result.class_ids)} | keep_class={result.keep_class_name}"
        )
        if result.reason:
            print(f"    reason: {result.reason}")

    print("\nMerge complete")
    for split in split_names:
        print(f"- {split}: {copied[split]} images")
    print(f"- output: {output_dir}")
    if skipped:
        print(f"- skipped datasets: {len(skipped)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine YOLO datasets from raw_data into one single-class dataset."
    )
    parser.add_argument(
        "--raw-data",
        type=Path,
        default=Path("raw_data"),
        help="Path to the raw_data directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("combined_dataset"),
        help="Output directory for the merged dataset",
    )
    parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Skip datasets that are not single-class instead of failing",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    merge_datasets(
        raw_data_dir=args.raw_data,
        output_dir=args.output,
        skip_invalid=args.skip_invalid,
    )


if __name__ == "__main__":
    main()

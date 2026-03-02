# Dataset Combination Utility

Use this project to combine all YOLO-format datasets in `raw_data/` into one merged dataset.

The script will:

- verify each dataset is single-class (`nc: 1`, one `names` entry, and labels using only class id `0`)
- apply a dataset-specific rule for `prjc.v1i.yolo26`: keep only `head` labels and drop the original `people` labels
- rewrite all merged labels so class id is `0`
- set the merged class name to `people`
- write output in YOLO layout (`train/`, `valid/`, `test/`) with a new `data.yaml`

## Run

Strict mode (fails if any dataset is not single-class):

```bash
uv run combine_raw_datasets.py
```

Skip invalid datasets and still merge valid ones:

```bash
uv run combine_raw_datasets.py --skip-invalid
```

Custom output path:

```bash
uv run combine_raw_datasets.py --output combined_dataset_v2
```

After run, the merged dataset is in `combined_dataset/` (unless `--output` is changed).

## Visualize labels and boxes

Use the viewer script to inspect the merged dataset with bounding boxes drawn.

```bash
uv run view_combined_dataset.py --dataset combined_dataset --split train
```

Optional shuffle:

```bash
uv run view_combined_dataset.py --dataset combined_dataset --split valid --shuffle
```

Controls:

- `n` or right arrow: next image
- `p` or left arrow: previous image
- `q` or `Esc`: quit

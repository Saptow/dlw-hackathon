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

# Frontend setup

## 🚀 Getting Started

1. **Change directory:**
    ```bash
    cd crowd-dashboard
    ```
2. **Install Dependencies:**
    ```bash
    npm install
    ```
3. **Run the Development Server:**
    ```bash
    npm run dev
    ```
4. Open `http://localhost:5173` in your browser.

# Server setup

## 🚀 Getting Started

1. **Change directory:**
    ```bash
    cd server
    ```
2. **Install Dependencies:**
   Install docker and docker-compose, then run:
    ```bash
    docker-compose up --build
    ```
3. The server will be available at `http://localhost:8080`.

# Edge Device setup

## 🚀 Getting Started

1. **Change directory:**
    ```bash
    cd edge_device
    ```
2. **Install Dependencies:**
   Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run:
    ```bash
    uv sync
    ```
3. **Run Edge Inference in Mock Mode:**
    ```bash
    ./run_parallel_cameras.sh
    ```
4. To run a single camera in live mode:
    ```bash
    uv run run_edge_inference.py \
      --model path/to/your_face_model.pt \
      --source 0 \
      --device-id DEV-001 \
      --server-url http://localhost:8080 \
      --location-label "North Gate Area" \
      --preview
    ```

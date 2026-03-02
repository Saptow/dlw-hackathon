# Edge Device Inference Script

Script: `run_edge_inference.py`

This script:

- runs a YOLO model on a video feed
- treats one class (default class `0`) as face detections
- estimates scene scale from median face bounding-box width
- estimates crowd density in people/square-meter
- computes a crowd-crush risk score on `[0, 1]`
- posts updates to backend every random `10-15s` by default

````

## Run in testing mode (no model required)

Use mock mode to randomize bounding-box widths and validate backend integration:

```bash
uv run edge_device/run_edge_inference.py \
  --mock-mode \
  --device-id DEV-TEST-001 \
  --server-url http://localhost:8080 \
  --location-label "Test Camera" \
  --post-min-s 10 \
  --post-max-s 15
````

Optional tuning for mock behavior:

- `--mock-face-mean` / `--mock-face-sd`
- `--mock-min-box-width-px` / `--mock-max-box-width-px`
- `--mock-frame-width-px` / `--mock-frame-height-px`

Defaults use Gaussian face counts with mean `35` and standard deviation `10`.

## Calibration graph helper

Generate a graph to pick realistic mock widths and understand width → distance → density:

```bash
uv run edge_device/plot_mock_calibration.py \
  --mock-face-mean 35 \
  --mock-face-sd 10 \
  --width-min-px 16 \
  --width-max-px 200 \
  --out edge_device/mock_calibration.png
```

This plots:

- median box width vs estimated distance (using pinhole approximation)
- median box width vs density for `mean-sd`, `mean`, and `mean+sd` face counts

Tune with `--focal-length-px`, `--frame-width-px`, `--frame-height-px`, and
`--face-width-m` to match your camera.

## Run 4 cameras in parallel (3 mock + 1 switchable)

From project root:

```bash
./edge_device/run_parallel_cameras.sh
```

This starts:

- `cam1`, `cam2`, `cam3` in mock mode
- `cam4` in mock mode by default, but can be switched to live

To switch camera 4 to live mode:

```bash
CAM4_MODE=live \
CAM4_MODEL=path/to/your_face_model.pt \
CAM4_SOURCE=0 \
./edge_device/run_parallel_cameras.sh
```

Useful environment variables:

- `SERVER_URL` (default `http://localhost:8080`)
- `POST_MIN_S`, `POST_MAX_S` (default `10`, `15`)
- `CAM1_DEVICE_ID` ... `CAM4_DEVICE_ID`
- `CAM1_LOCATION` ... `CAM4_LOCATION`
- `LOG_DIR` (default `edge_device/logs`)

## Run

From project root:

```bash
uv run edge_device/run_edge_inference.py \
  --model path/to/your_face_model.pt \
  --source 0 \
  --device-id DEV-001 \
  --server-url http://localhost:8080 \
  --location-label "North Gate Area" \
  --preview
```

## Common sources

- Webcam: `--source 0`
- RTSP stream: `--source rtsp://user:pass@camera-ip/stream`
- Video file: `--source path/to/video.mp4`

## API behavior

- If `--location-label` is provided, script first calls `POST /devices/location`.
- Every `10-15s` (configurable), script calls `POST /db/push` with:
    - `device_id`
    - current UTC `timestamp`
    - status (`active`, `warning`, `critical`)
    - metrics: `people_count`, `crowd_density` (people/sqm), `threshold` (risk score)

## Tunable parameters

- `--conf`: detection confidence threshold (default `0.35`)
- `--class-id`: class index considered as face class (default `0`)
- `--assumed-face-width-m`: average face width for scale estimation (default `0.16`)
- `--focal-length-px`: focal length in pixels for distance/FOV area estimation (default `900`)
- `--min-person-space-sqm`: minimum occupied area per person (default `0.35`)
- `--post-min-s` and `--post-max-s`: posting interval range (default `10` to `15`)
- `--mock-mode`: bypass model + video and generate randomized detections for testing

## Notes

Density and risk are heuristic estimates from 2D detections and should be calibrated per camera angle and scene geometry for production use.

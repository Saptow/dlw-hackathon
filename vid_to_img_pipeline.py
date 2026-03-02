import argparse
import os
from pathlib import Path
import cv2
from tqdm import tqdm

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".m4v", ".ts"}

def safe_mkdir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def extract_frames(
    video_path: Path,
    out_dir: Path,
    fps_out: float,
    resize_w: int | None,
    resize_h: int | None,
    prefix: str,
    jpg_quality: int,
):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps_in = cap.get(cv2.CAP_PROP_FPS)
    if fps_in is None or fps_in <= 0:
        fps_in = 25.0  # fallback

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(int(round(fps_in / fps_out)), 1)  # sample every 'step' frames

    base = video_path.stem
    video_out = out_dir / base
    safe_mkdir(video_out)

    pbar = tqdm(total=total_frames if total_frames > 0 else None, desc=f"Extract {base}", unit="frame")
    idx = 0
    saved = 0

    # OpenCV jpeg quality control:
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(jpg_quality)]

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if idx % step == 0:
            if resize_w and resize_h:
                frame = cv2.resize(frame, (resize_w, resize_h), interpolation=cv2.INTER_AREA)

            # Timestamp in seconds (approx)
            t_sec = idx / fps_in
            # name like: GT_cam01_00001234_t00012.34.jpg
            filename = f"{prefix}{base}_{idx:08d}_t{t_sec:08.2f}.jpg"
            out_path = video_out / filename
            cv2.imwrite(str(out_path), frame, encode_params)
            saved += 1

        idx += 1
        pbar.update(1)

    pbar.close()
    cap.release()
    return saved, fps_in, step, video_out

def iter_videos(input_path: Path):
    if input_path.is_file():
        yield input_path
        return
    for p in sorted(input_path.rglob("*")):
        if p.suffix.lower() in VIDEO_EXTS:
            yield p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Video file or folder containing videos")
    ap.add_argument("--out", required=True, help="Output root folder for frames")
    ap.add_argument("--fps", type=float, default=2.0, help="Extract frames at this FPS (e.g., 2.0)")
    ap.add_argument("--resize", type=str, default="", help="Optional resize WxH, e.g. 640x360 (leave blank to keep)")
    ap.add_argument("--prefix", type=str, default="", help="Optional filename prefix, e.g. GT_")
    ap.add_argument("--jpg_quality", type=int, default=95, help="JPEG quality 1-100")
    args = ap.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out)
    safe_mkdir(out_dir)

    resize_w = resize_h = None
    if args.resize.strip():
        w, h = args.resize.lower().split("x")
        resize_w, resize_h = int(w), int(h)

    videos = list(iter_videos(input_path))
    if not videos:
        raise SystemExit(f"No videos found in: {input_path}")

    print(f"Found {len(videos)} video(s). Extracting at {args.fps} fps...")

    for v in videos:
        saved, fps_in, step, folder = extract_frames(
            v, out_dir, args.fps, resize_w, resize_h, args.prefix, args.jpg_quality
        )
        print(f"- {v.name}: input_fps={fps_in:.2f}, step={step}, saved={saved} frames -> {folder}")

if __name__ == "__main__":
    main()
import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import torch
import torchvision.transforms as transforms
from PIL import Image

EDGE_DEVICE_DIR = Path(__file__).resolve().parent
if str(EDGE_DEVICE_DIR) not in sys.path:
    sys.path.insert(0, str(EDGE_DEVICE_DIR))

import net as _sanet_net  # noqa: F401

from vid_to_img_pipeline import extract_frames, safe_mkdir

Point = Tuple[float, float]
Polygon = Sequence[Point]

CHECKPOINT_PATH = Path(__file__).resolve().parent / "checkpoints" / "model_rate.pkl"


def _polygon_area_px2(poly: Polygon) -> float:
    pts = np.asarray(poly, dtype=float)
    if len(pts) < 3:
        return 0.0
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _points_in_poly(points_xy: np.ndarray, poly: Polygon) -> np.ndarray:
    poly_np = np.asarray(poly, dtype=float)
    if len(poly_np) < 3:
        return np.zeros((points_xy.shape[0],), dtype=bool)

    x = points_xy[:, 0]
    y = points_xy[:, 1]
    xp = poly_np[:, 0]
    yp = poly_np[:, 1]

    inside = np.zeros_like(x, dtype=bool)
    j = len(poly_np) - 1
    for i in range(len(poly_np)):
        xi, yi = xp[i], yp[i]
        xj, yj = xp[j], yp[j]
        intersect = ((yi > y) != (yj > y)) & (
            x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
        )
        inside ^= intersect
        j = i
    return inside


def crowd_count_from_density_map(density_map: np.ndarray) -> float:
    return float(np.sum(density_map))


def crowd_density_from_density_map(
    density_map: np.ndarray,
    *,
    region: str = "image",
    roi_polygon: Optional[Polygon] = None,
    units: str = "per_mpx",
) -> float:
    h, w = density_map.shape[:2]
    if region == "image":
        count = crowd_count_from_density_map(density_map)
        area_px2 = float(h * w)
    elif region == "roi":
        if roi_polygon is None:
            raise ValueError("region='roi' requires roi_polygon.")
        area_px2 = float(_polygon_area_px2(roi_polygon))
        if area_px2 <= 0:
            return 0.0

        xx, yy = np.meshgrid(np.arange(w), np.arange(h))
        points = np.stack([xx.ravel(), yy.ravel()], axis=1)
        mask = _points_in_poly(points, roi_polygon).reshape(h, w)
        count = float(np.sum(density_map[mask]))
    else:
        raise ValueError("region must be 'image' or 'roi'.")

    if area_px2 <= 0:
        return 0.0
    if units == "per_px2":
        return float(count) / area_px2
    if units == "per_mpx":
        return float(count) / (area_px2 / 1e6)
    raise ValueError("units must be 'per_px2' or 'per_mpx'.")


def crowd_density_grid_from_density_map(
    density_map: np.ndarray,
    *,
    grid: Tuple[int, int] = (10, 10),
) -> np.ndarray:
    h, w = density_map.shape[:2]
    gy, gx = int(grid[0]), int(grid[1])
    if gy <= 0 or gx <= 0:
        raise ValueError("grid must be positive (rows, cols).")

    cell_sums = np.zeros((gy, gx), dtype=np.float32)
    for iy in range(gy):
        y0 = int(round(iy * h / gy))
        y1 = int(round((iy + 1) * h / gy))
        for ix in range(gx):
            x0 = int(round(ix * w / gx))
            x1 = int(round((ix + 1) * w / gx))
            cell_sums[iy, ix] = float(np.sum(density_map[y0:y1, x0:x1]))
    return cell_sums


def _parse_grid(raw: str) -> Tuple[int, int]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 2:
        raise ValueError("grid must be 'rows,cols'.")
    return int(parts[0]), int(parts[1])


def _parse_roi(raw: Optional[str]) -> Optional[list[Point]]:
    if raw is None:
        return None
    points: list[Point] = []
    for pair in raw.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        xy = [v.strip() for v in pair.split(",")]
        if len(xy) != 2:
            raise ValueError("ROI format must be 'x1,y1;x2,y2;...'.")
        points.append((float(xy[0]), float(xy[1])))
    return points if points else None


def _prepare_eval_patches(
    image_path: Path,
) -> tuple[Image.Image, torch.Tensor, int, int]:
    image = Image.open(image_path).convert("RGB")
    image_tensor = transforms.ToTensor()(image)
    _, h, w = image_tensor.shape
    patch_height = int(h / 4)
    patch_width = int(w / 4)
    if patch_height <= 0 or patch_width <= 0:
        raise ValueError("Image is too small for SANet patch inference.")

    valid_h = patch_height * 4
    valid_w = patch_width * 4
    image = image.crop((0, 0, valid_w, valid_h))
    image_tensor = image_tensor[:, :valid_h, :valid_w]
    image_tensor = transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225))(
        image_tensor
    )

    patches = []
    for i in range(7):
        for j in range(7):
            start_h = int(patch_height / 2) * i
            start_w = int(patch_width / 2) * j
            patches.append(
                image_tensor[
                    :, start_h : start_h + patch_height, start_w : start_w + patch_width
                ]
            )
    eval_x = torch.stack(patches)
    return image, eval_x, patch_height, patch_width


def _predict_density_map(
    net: torch.nn.Module,
    eval_x: torch.Tensor,
    patch_height: int,
    patch_width: int,
    device_obj: torch.device,
):
    with torch.no_grad():
        first_pred = net(eval_x[0:1].to(device_obj))
        out_h, out_w = int(first_pred.shape[-2]), int(first_pred.shape[-1])
        qh, qw = int(out_h / 4), int(out_w / 4)

        prediction_map = torch.zeros(1, 1, out_h * 4, out_w * 4, device=device_obj)

        for i in range(7):
            for j in range(7):
                if i == 0 and j == 0:
                    eval_prediction = first_pred
                else:
                    eval_x_sample = eval_x[i * 7 + j : i * 7 + j + 1].to(device_obj)
                    eval_prediction = net(eval_x_sample)

                start_h = qh
                start_w = qw
                valid_h = int(out_h / 2)
                valid_w = int(out_w / 2)
                h_pred = 3 * qh + 2 * qh * (i - 1)
                w_pred = 3 * qw + 2 * qw * (j - 1)
                if i == 0:
                    valid_h = out_h - qh
                    start_h = 0
                    h_pred = 0
                elif i == 6:
                    valid_h = out_h - qh

                if j == 0:
                    valid_w = out_w - qw
                    start_w = 0
                    w_pred = 0
                elif j == 6:
                    valid_w = out_w - qw

                dst_h0 = max(h_pred, 0)
                dst_w0 = max(w_pred, 0)
                dst_h1 = min(h_pred + valid_h, prediction_map.shape[-2])
                dst_w1 = min(w_pred + valid_w, prediction_map.shape[-1])
                if dst_h1 <= dst_h0 or dst_w1 <= dst_w0:
                    continue

                src_h0 = start_h + (dst_h0 - h_pred)
                src_w0 = start_w + (dst_w0 - w_pred)
                src_h1 = src_h0 + (dst_h1 - dst_h0)
                src_w1 = src_w0 + (dst_w1 - dst_w0)

                src_h1 = min(src_h1, eval_prediction.shape[-2])
                src_w1 = min(src_w1, eval_prediction.shape[-1])
                dst_h1 = dst_h0 + (src_h1 - src_h0)
                dst_w1 = dst_w0 + (src_w1 - src_w0)

                if src_h1 <= src_h0 or src_w1 <= src_w0:
                    continue

                prediction_map[:, :, dst_h0:dst_h1, dst_w0:dst_w1] += eval_prediction[
                    :, :, src_h0:src_h1, src_w0:src_w1
                ]
    return np.squeeze(prediction_map.permute(0, 2, 3, 1).cpu().numpy())


def _load_model(device_obj: torch.device):
    net = torch.load(CHECKPOINT_PATH, map_location=device_obj, weights_only=False).to(
        device_obj
    )
    net.eval()
    return net


def predict_image(
    image_path: Path | str,
    *,
    grid: Tuple[int, int] | str = (8, 12),
    roi: Optional[Polygon | str] = None,
    units: str = "per_mpx",
    print_grid: bool = False,
    show_plot: bool = False,
    device: Optional[str] = None,
    _model: Optional[torch.nn.Module] = None,
):
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if units not in {"per_px2", "per_mpx"}:
        raise ValueError("units must be 'per_px2' or 'per_mpx'.")

    image_path = Path(image_path)
    grid = _parse_grid(grid) if isinstance(grid, str) else (int(grid[0]), int(grid[1]))
    roi_polygon = _parse_roi(roi) if isinstance(roi, str) else roi
    device_obj = torch.device(device)

    image, eval_x, patch_height, patch_width = _prepare_eval_patches(image_path)
    net = _model if _model is not None else _load_model(device_obj)
    pred_map_2d = _predict_density_map(
        net, eval_x, patch_height, patch_width, device_obj
    )

    pred_count = crowd_count_from_density_map(pred_map_2d)
    pred_density_image = crowd_density_from_density_map(
        pred_map_2d, region="image", units=units
    )
    pred_density_roi = (
        crowd_density_from_density_map(
            pred_map_2d, region="roi", roi_polygon=roi_polygon, units=units
        )
        if roi_polygon is not None
        else None
    )
    pred_grid = crowd_density_grid_from_density_map(pred_map_2d, grid=grid)

    if show_plot:
        _, (origin, dm_pred) = plt.subplots(1, 2, figsize=(14, 4))
        origin.imshow(image)
        origin.set_title("Origin Image")
        dm_pred.imshow(pred_map_2d, cmap="jet")
        dm_pred.set_title("Prediction Density Map")
        plt.suptitle("SANet prediction: {}".format(image_path.name))
        plt.show()

    sys.stdout.write(
        "Pred count: {:.3f}, Pred density({}): {:.6f}".format(
            pred_count, units, pred_density_image
        )
    )
    if pred_density_roi is not None:
        sys.stdout.write(
            ", Pred ROI density({}): {:.6f}".format(units, pred_density_roi)
        )
    sys.stdout.write("\n")
    if print_grid:
        sys.stdout.write("Pred grid density map:\n{}\n".format(pred_grid))
    sys.stdout.flush()

    return {
        "image_path": str(image_path),
        "model_path": str(CHECKPOINT_PATH),
        "pred_count": float(pred_count),
        "pred_density_image": float(pred_density_image),
        "pred_density_roi": (
            None if pred_density_roi is None else float(pred_density_roi)
        ),
        "grid": [int(grid[0]), int(grid[1])],
        "grid_counts": pred_grid.tolist(),
        "units": units,
        "prediction_map_shape": list(pred_map_2d.shape),
    }


def predict_video(
    video_path: Path | str,
    *,
    frames_out_root: Optional[Path | str] = None,
    fps: float = 2.0,
    resize: Optional[Tuple[int, int]] = None,
    prefix: str = "",
    jpg_quality: int = 95,
    grid: Tuple[int, int] | str = (8, 12),
    roi: Optional[Polygon | str] = None,
    units: str = "per_mpx",
    print_grid: bool = False,
    show_plot: bool = False,
    device: Optional[str] = None,
):
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device_obj = torch.device(device)

    video_path = Path(video_path)
    if frames_out_root is None:
        frames_out_root = (
            Path(__file__).resolve().parent.parent / "runs" / "sanet_frames"
        )
    frames_out_root = Path(frames_out_root)
    safe_mkdir(frames_out_root)

    resize_w = resize_h = None
    if resize is not None:
        resize_w, resize_h = int(resize[0]), int(resize[1])

    saved, fps_in, step, frame_dir = extract_frames(
        video_path=video_path,
        out_dir=frames_out_root,
        fps_out=float(fps),
        resize_w=resize_w,
        resize_h=resize_h,
        prefix=prefix,
        jpg_quality=int(jpg_quality),
    )

    frame_paths = sorted(frame_dir.glob("*.jpg"))
    model = _load_model(device_obj)
    frame_stats = []
    for frame_path in frame_paths:
        frame_stats.append(
            predict_image(
                frame_path,
                grid=grid,
                roi=roi,
                units=units,
                print_grid=print_grid,
                show_plot=show_plot,
                device=device,
                _model=model,
            )
        )

    counts = [s["pred_count"] for s in frame_stats]
    densities = [s["pred_density_image"] for s in frame_stats]
    return {
        "video_path": str(video_path),
        "frames_dir": str(frame_dir),
        "saved_frames": int(saved),
        "processed_frames": len(frame_stats),
        "input_fps": float(fps_in),
        "sample_step": int(step),
        "avg_pred_count": float(np.mean(counts)) if counts else 0.0,
        "avg_pred_density_image": float(np.mean(densities)) if densities else 0.0,
        "units": units,
        "frames": frame_stats,
    }


def main(
    image_path: Path | str,
    grid: Tuple[int, int] | str = (8, 12),
    roi: Optional[Polygon | str] = None,
    units: str = "per_mpx",
    print_grid: bool = False,
    show_plot: bool = False,
    device: Optional[str] = None,
):
    return predict_image(
        image_path=image_path,
        grid=grid,
        roi=roi,
        units=units,
        print_grid=print_grid,
        show_plot=show_plot,
        device=device,
    )


def _parse_resize(raw: Optional[str]) -> Optional[Tuple[int, int]]:
    if raw is None:
        return None
    text = raw.strip().lower()
    if not text:
        return None
    if "x" not in text:
        raise ValueError("resize must be in 'WIDTHxHEIGHT' format, e.g. '1280x720'.")
    width, height = text.split("x", 1)
    return int(width), int(height)


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run SANet crowd prediction on an image or video."
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--image", type=str, help="Path to an input image.")
    mode_group.add_argument("--video", type=str, help="Path to an input video.")

    parser.add_argument(
        "--grid",
        type=str,
        default="8,12",
        help="Grid rows,cols for per-cell counts. Example: 8,12",
    )
    parser.add_argument(
        "--roi", type=str, default=None, help="ROI polygon in 'x1,y1;x2,y2;...' format."
    )
    parser.add_argument(
        "--units",
        type=str,
        default="per_mpx",
        choices=["per_px2", "per_mpx"],
        help="Density units.",
    )
    parser.add_argument(
        "--device", type=str, default=None, help="Torch device, e.g. cpu, cuda, cuda:0"
    )
    parser.add_argument(
        "--print-grid", action="store_true", help="Print grid count matrix."
    )
    parser.add_argument(
        "--show-plot",
        action="store_true",
        help="Show matplotlib prediction plot per frame/image.",
    )

    parser.add_argument(
        "--fps", type=float, default=2.0, help="Video frame sampling rate."
    )
    parser.add_argument(
        "--frames-out-root",
        type=str,
        default=None,
        help="Directory to store extracted frames.",
    )
    parser.add_argument(
        "--resize",
        type=str,
        default=None,
        help="Optional video frame resize, format WIDTHxHEIGHT.",
    )
    parser.add_argument(
        "--prefix", type=str, default="", help="Filename prefix for extracted frames."
    )
    parser.add_argument(
        "--jpg-quality",
        type=int,
        default=95,
        help="JPEG quality for extracted frames (1-100).",
    )

    parser.add_argument(
        "--save-json",
        type=str,
        default=None,
        help="Optional path to save full prediction result as JSON.",
    )
    return parser


def _cli_main() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()

    resize = _parse_resize(args.resize)

    if args.image:
        result = predict_image(
            image_path=args.image,
            grid=args.grid,
            roi=args.roi,
            units=args.units,
            print_grid=args.print_grid,
            show_plot=args.show_plot,
            device=args.device,
        )
    else:
        result = predict_video(
            video_path=args.video,
            frames_out_root=args.frames_out_root,
            fps=args.fps,
            resize=resize,
            prefix=args.prefix,
            jpg_quality=args.jpg_quality,
            grid=args.grid,
            roi=args.roi,
            units=args.units,
            print_grid=args.print_grid,
            show_plot=args.show_plot,
            device=args.device,
        )

    if args.save_json:
        save_path = Path(args.save_json)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(result, indent=2))
        print(f"Saved prediction JSON: {save_path}")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())

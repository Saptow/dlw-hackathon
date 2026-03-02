import json
from pathlib import Path

from model.predict import predict_video


def main():
    root = Path(__file__).resolve().parent
    video_path = root / "855749-hd_1920_1080_30fps.mp4"

    stats = predict_video(
        video_path=video_path,
        frames_out_root=root / "runs" / "sanet_frames",
        fps=2.0,
        grid=(8, 12),
        units="per_mpx",
        print_grid=False,
        show_plot=False,
        device=None,
    )

    summary = {
        "video_path": stats["video_path"],
        "frames_dir": stats["frames_dir"],
        "saved_frames": stats["saved_frames"],
        "processed_frames": stats["processed_frames"],
        "input_fps": stats["input_fps"],
        "sample_step": stats["sample_step"],
        "avg_pred_count": stats["avg_pred_count"],
        "avg_pred_density_image": stats["avg_pred_density_image"],
        "units": stats["units"],
    }
    print(json.dumps(summary, indent=2))

    out_path = root / "runs" / "sanet_video_metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Saved full metrics to: {out_path}")


if __name__ == "__main__":
    main()

import argparse

import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot calibration curves for mock-mode box width vs distance and density"
        )
    )
    parser.add_argument(
        "--face-width-m",
        type=float,
        default=0.16,
        help="Assumed real-world face width in meters",
    )
    parser.add_argument(
        "--focal-length-px",
        type=float,
        default=320.0,
        help="Approximate camera focal length in pixels for distance curve",
    )
    parser.add_argument(
        "--frame-width-px",
        type=int,
        default=1280,
        help="Frame width used in density estimate",
    )
    parser.add_argument(
        "--frame-height-px",
        type=int,
        default=720,
        help="Frame height used in density estimate",
    )
    parser.add_argument(
        "--width-min-px",
        type=float,
        default=3.0,
        help="Minimum box width to include in plot",
    )
    parser.add_argument(
        "--width-max-px",
        type=float,
        default=200.0,
        help="Maximum box width to include in plot",
    )
    parser.add_argument(
        "--mock-face-mean",
        type=float,
        default=55.0,
        help="Mean faces used in density plot",
    )
    parser.add_argument(
        "--mock-face-sd",
        type=float,
        default=20.0,
        help="Standard deviation used in density plot",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional output image path (e.g. edge_device/mock_calibration.png)",
    )
    return parser.parse_args()


def distance_from_box_width(
    box_width_px: np.ndarray, face_width_m: float, focal_length_px: float
) -> np.ndarray:
    return (focal_length_px * face_width_m) / np.maximum(box_width_px, 1e-6)


def density_from_box_width(
    box_width_px: np.ndarray,
    people_count: float,
    frame_width_px: int,
    frame_height_px: int,
    face_width_m: float,
    focal_length_px: float,  # Added this
) -> np.ndarray:
    # 1. Estimate distance to the plane where the faces are
    distance_m = (focal_length_px * face_width_m) / np.maximum(box_width_px, 1e-6)

    # 2. Calculate the real-world dimensions of the camera's FOV at that distance
    # Based on similar triangles: Scene_W / distance = Frame_W_px / focal_length_px
    scene_width_m = (distance_m * frame_width_px) / focal_length_px
    scene_height_m = (distance_m * frame_height_px) / focal_length_px

    scene_area_m2 = scene_width_m * scene_height_m

    return people_count / np.maximum(scene_area_m2, 1e-6)


def main() -> None:
    args = parse_args()

    if args.width_min_px <= 0 or args.width_max_px <= args.width_min_px:
        raise ValueError("Invalid width range")
    if args.face_width_m <= 0 or args.focal_length_px <= 0:
        raise ValueError("face width and focal length must be > 0")
    if args.frame_width_px <= 0 or args.frame_height_px <= 0:
        raise ValueError("frame dimensions must be > 0")
    if args.mock_face_mean < 0 or args.mock_face_sd < 0:
        raise ValueError("mock mean/sd must be >= 0")

    widths = np.linspace(args.width_min_px, args.width_max_px, 300)
    distances_m = distance_from_box_width(
        widths, args.face_width_m, args.focal_length_px
    )

    face_counts = [
        max(0.0, args.mock_face_mean - args.mock_face_sd),
        args.mock_face_mean,
        args.mock_face_mean + args.mock_face_sd,
    ]
    density_curves = [
        density_from_box_width(
            widths,
            count,
            args.frame_width_px,
            args.frame_height_px,
            args.face_width_m,
            args.focal_length_px,
        )
        for count in face_counts
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))

    axes[0].plot(widths, distances_m, color="tab:blue", linewidth=2)
    axes[0].set_title("Box Width vs Estimated Distance")
    axes[0].set_xlabel("Median face box width (px)")
    axes[0].set_ylabel("Estimated distance (m)")
    axes[0].grid(alpha=0.25)

    colors = ["tab:green", "tab:orange", "tab:red"]
    labels = [
        f"faces={face_counts[0]:.1f} (mean-sd)",
        f"faces={face_counts[1]:.1f} (mean)",
        f"faces={face_counts[2]:.1f} (mean+sd)",
    ]

    for curve, color, label in zip(density_curves, colors, labels, strict=True):
        axes[1].plot(widths, curve, color=color, linewidth=2, label=label)

    axes[1].set_title("Box Width vs Density")
    axes[1].set_xlabel("Median face box width (px)")
    axes[1].set_ylabel("Density (people / sqm)")
    axes[1].grid(alpha=0.25)
    axes[1].legend()

    fig.suptitle("Mock Calibration Curves", fontsize=12)
    fig.tight_layout()

    if args.out:
        fig.savefig(args.out, dpi=150)
        print(f"Saved: {args.out}")
    else:
        plt.show()


if __name__ == "__main__":
    main()

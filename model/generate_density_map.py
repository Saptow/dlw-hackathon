import argparse
from pathlib import Path

import cv2
import numpy as np
import scipy
import scipy.io as scio
from PIL import Image


def get_density_map_gaussian(N, M, points, adaptive_kernel=False, fixed_value=15):
    density_map = np.zeros([N, M], dtype=np.float32)
    h, w = density_map.shape[:2]
    num_gt = np.squeeze(points).shape[0]
    if num_gt == 0:
        return density_map

    if adaptive_kernel:
        # Referred from https://github.com/vlad3996/computing-density-maps/blob/master/make_ShanghaiTech.ipynb
        leafsize = 2048
        tree = scipy.spatial.KDTree(points.copy(), leafsize=leafsize)
        distances = tree.query(points, k=4)[0]

    for idx, p in enumerate(points):
        p = np.round(p).astype(int)
        p[0], p[1] = min(h - 1, p[1]), min(w - 1, p[0])
        if num_gt > 1:
            if adaptive_kernel:
                sigma = int(np.sum(distances[idx][1:4]) // 3 * 0.3)
            else:
                sigma = fixed_value
        else:
            sigma = fixed_value
        sigma = max(1, sigma)

        gaussian_radius = sigma * 3
        gaussian_map = np.multiply(
            cv2.getGaussianKernel(gaussian_radius * 2 + 1, sigma),
            cv2.getGaussianKernel(gaussian_radius * 2 + 1, sigma).T,
        )
        x_left, x_right, y_up, y_down = 0, gaussian_map.shape[1], 0, gaussian_map.shape[0]
        if p[1] < 0 or p[0] < 0:
            continue
        if p[1] < gaussian_radius:
            x_left = gaussian_radius - p[1]
        if p[0] < gaussian_radius:
            y_up = gaussian_radius - p[0]
        if p[1] + gaussian_radius >= w:
            x_right = gaussian_map.shape[1] - (gaussian_radius + p[1] - w) - 1
        if p[0] + gaussian_radius >= h:
            y_down = gaussian_map.shape[0] - (gaussian_radius + p[0] - h) - 1
        density_map[
            max(0, p[0] - gaussian_radius):min(density_map.shape[0], p[0] + gaussian_radius + 1),
            max(0, p[1] - gaussian_radius):min(density_map.shape[1], p[1] + gaussian_radius + 1),
        ] += gaussian_map[y_up:y_down, x_left:x_right]
    return density_map


def parse_args():
    parser = argparse.ArgumentParser(description="Generate density maps from ShanghaiTech point annotations.")
    parser.add_argument("--image-dir", type=Path, required=True, help="Directory containing IMG_*.jpg files.")
    parser.add_argument("--ground-truth-dir", type=Path, required=True, help="Directory containing GT_IMG_*.mat files.")
    parser.add_argument("--output-gt-dir", type=Path, required=True, help="Directory to save GT_IMG_*.npy files.")
    parser.add_argument(
        "--num-images",
        type=int,
        default=None,
        help="Number of images to process. If omitted, inferred from IMG_*.jpg files.",
    )
    parser.add_argument("--fixed-sigma", type=int, default=5, help="Fixed Gaussian sigma.")
    parser.add_argument("--adaptive-kernel", action="store_true", help="Use adaptive Gaussian kernel.")
    return parser.parse_args()


def main():
    args = parse_args()
    args.output_gt_dir.mkdir(parents=True, exist_ok=True)

    if args.num_images is None:
        image_paths = sorted(args.image_dir.glob("IMG_*.jpg"))
        num_images = len(image_paths)
    else:
        num_images = args.num_images

    for i in range(num_images):
        img_path = args.image_dir / f"IMG_{i + 1}.jpg"
        gt_path = args.ground_truth_dir / f"GT_IMG_{i + 1}.mat"
        if not img_path.exists() or not gt_path.exists():
            continue

        img = Image.open(img_path)
        height = img.size[1]
        width = img.size[0]
        points = scio.loadmat(gt_path)["image_info"][0][0][0][0][0]
        gt = get_density_map_gaussian(height, width, points, args.adaptive_kernel, args.fixed_sigma)
        gt = np.reshape(gt, [height, width])
        np.save(args.output_gt_dir / f"GT_IMG_{i + 1}", gt)
        print("complete:", i + 1)


if __name__ == "__main__":
    main()

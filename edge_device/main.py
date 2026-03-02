import argparse
import random
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from DataConstructor import DatasetConstructor
from metrics import AEBatch, SEBatch
from net import SANet
from ssim_loss import SANetLoss
from utils import show


def parse_args():
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Train SANet with local dataset directories.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=base_dir / "part_B_final",
        help="Dataset root containing train_data/ and test_data/ subfolders.",
    )
    parser.add_argument(
        "--checkpoints-dir",
        type=Path,
        default=base_dir / "checkpoints",
        help="Directory where model checkpoints will be saved.",
    )
    parser.add_argument("--train-num", type=int, default=400, help="Number of training images.")
    parser.add_argument("--test-num", type=int, default=316, help="Number of test images.")
    parser.add_argument("--validate-num", type=int, default=50, help="Validation samples per eval.")
    parser.add_argument("--batch-size", type=int, default=4, help="Training batch size.")
    parser.add_argument("--epochs", type=int, default=10000, help="Number of training epochs.")
    parser.add_argument("--eval-every", type=int, default=100, help="Run eval every N train steps.")
    parser.add_argument("--show-every", type=int, default=2000, help="Show one eval sample every N train steps.")
    parser.add_argument(
        "--device",
        type=str,
        default="cuda" if torch.cuda.is_available() else "cpu",
        help='PyTorch device, e.g. "cuda", "cuda:0", or "cpu".',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    mae_best = 10240000
    mse_best = 10240000
    rate_best = 10000000

    img_dir = args.data_root / "train_data" / "images"
    gt_dir = args.data_root / "train_data" / "gt_map"
    img_dir_t = args.data_root / "test_data" / "images"
    gt_dir_t = args.data_root / "test_data" / "gt_map"

    dataset = DatasetConstructor(str(img_dir), str(gt_dir), args.train_num, args.validate_num)
    test_data_set = DatasetConstructor(str(img_dir_t), str(gt_dir_t), args.test_num, args.validate_num, False)
    train_loader = torch.utils.data.DataLoader(dataset=dataset, batch_size=args.batch_size)
    eval_loader = torch.utils.data.DataLoader(dataset=test_data_set, batch_size=1)

    device = torch.device(args.device)
    args.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    net = SANet().to(device)
    criterion = SANetLoss(1).to(device)
    optimizer = torch.optim.Adam(net.parameters(), 1e-6)
    ae_batch = AEBatch().to(device)
    se_batch = SEBatch().to(device)

    step = 0
    for epoch_index in range(args.epochs):
        dataset = dataset.shuffle()
        for train_img_index, train_img, train_gt, data_ptc in train_loader:
            if step % args.eval_every == 0:
                net.eval()
                test_data_set = test_data_set.shuffle()
                loss_ = []
                mae_list = []
                mse_list = []
                difference_rates = []
                rand_number = random.randint(0, max(0, args.validate_num - 1))
                counter = 0

                for eval_img_index, eval_img, eval_gt, eval_data_ptc in eval_loader:
                    image_shape = eval_img.shape
                    patch_height = int(image_shape[3])
                    patch_width = int(image_shape[4])
                    eval_x = eval_img.view(49, 3, patch_height, patch_width)
                    eval_y = eval_gt.view(1, 1, patch_height * 4, patch_width * 4).to(device)
                    prediction_map = torch.zeros(1, 1, patch_height * 4, patch_width * 4, device=device)
                    for i in range(7):
                        for j in range(7):
                            eval_x_sample = eval_x[i * 7 + j:i * 7 + j + 1].to(device)
                            eval_prediction = net(eval_x_sample)
                            start_h = int(patch_height / 4)
                            start_w = int(patch_width / 4)
                            valid_h = int(patch_height / 2)
                            valid_w = int(patch_width / 2)
                            h_pred = 3 * int(patch_height / 4) + 2 * int(patch_height / 4) * (i - 1)
                            w_pred = 3 * int(patch_width / 4) + 2 * int(patch_width / 4) * (j - 1)
                            if i == 0:
                                valid_h = int((3 * patch_height) / 4)
                                start_h = 0
                                h_pred = 0
                            elif i == 6:
                                valid_h = int((3 * patch_height) / 4)

                            if j == 0:
                                valid_w = int((3 * patch_width) / 4)
                                start_w = 0
                                w_pred = 0
                            elif j == 6:
                                valid_w = int((3 * patch_width) / 4)

                            prediction_map[:, :, h_pred:h_pred + valid_h, w_pred:w_pred + valid_w] += eval_prediction[
                                :, :, start_h:start_h + valid_h, start_w:start_w + valid_w
                            ]

                    eval_loss = criterion(prediction_map, eval_y).data.cpu().numpy()
                    batch_ae = ae_batch(prediction_map, eval_y).data.cpu().numpy()
                    batch_se = se_batch(prediction_map, eval_y).data.cpu().numpy()

                    validate_pred_map = np.squeeze(prediction_map.permute(0, 2, 3, 1).data.cpu().numpy())
                    validate_gt_map = np.squeeze(eval_y.permute(0, 2, 3, 1).data.cpu().numpy())
                    gt_counts = np.sum(validate_gt_map)
                    pred_counts = np.sum(validate_pred_map)

                    if rand_number == counter and step % args.show_every == 0:
                        image_index = eval_img_index.numpy()[0]
                        origin_image = Image.open(img_dir_t / f"IMG_{image_index}.jpg")
                        show(origin_image, validate_gt_map, validate_pred_map, image_index)
                        sys.stdout.write(
                            "The gt counts of the above sample:{}, and the pred counts:{}\n".format(
                                gt_counts, pred_counts
                            )
                        )

                    difference_rates.append(np.abs(gt_counts - pred_counts) / gt_counts)
                    loss_.append(eval_loss)
                    mae_list.append(batch_ae)
                    mse_list.append(batch_se)
                    counter += 1

                loss_ = np.reshape(loss_, [-1])
                mae_list = np.reshape(mae_list, [-1])
                mse_list = np.reshape(mse_list, [-1])

                validate_loss = np.mean(loss_)
                validate_mae = np.mean(mae_list)
                validate_rmse = np.sqrt(np.mean(mse_list))
                validate_rate = np.mean(difference_rates)

                sys.stdout.write(
                    "In step {}, epoch {}, with loss {}, rate = {}, MAE = {}, MSE = {}\n".format(
                        step, epoch_index + 1, validate_loss, validate_rate, validate_mae, validate_rmse
                    )
                )
                sys.stdout.flush()

                if rate_best > validate_rate:
                    rate_best = validate_rate
                    torch.save(net, args.checkpoints_dir / "model_1_rate.pkl")

                if mae_best > validate_mae:
                    mae_best = validate_mae
                    torch.save(net, args.checkpoints_dir / "model_1_mae.pkl")

                if mse_best > validate_rmse:
                    mse_best = validate_rmse
                    torch.save(net, args.checkpoints_dir / "model_1_mse.pkl")

                torch.save(net, args.checkpoints_dir / "model_1_in_time.pkl")

            net.train()
            optimizer.zero_grad()
            x = train_img.to(device)
            y = train_gt.to(device)
            prediction = net(x)
            loss = criterion(prediction, y)
            loss.backward()
            optimizer.step()
            step += 1


if __name__ == "__main__":
    main()

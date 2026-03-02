import argparse
import json
import random
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from typing import Iterable
from urllib import error, request

import cv2
import numpy as np
from ultralytics import YOLO


@dataclass
class DensityEstimate:
    people_count: int
    scene_area_sqm: float
    occupied_area_sqm: float
    available_area_sqm: float
    crowd_density_ppsqm: float
    risk_score: float


class EdgeDeviceRunner:
    def __init__(
        self,
        model_path: str,
        source: str,
        device_id: str,
        server_base_url: str,
        location_label: str | None,
        confidence: float,
        class_id: int,
        assumed_face_width_m: float,
        min_person_space_sqm: float,
        post_min_interval_s: float,
        post_max_interval_s: float,
        show_preview: bool,
        mock_mode: bool,
        mock_min_faces: int,
        mock_max_faces: int,
        mock_min_box_width_px: float,
        mock_max_box_width_px: float,
        mock_frame_width_px: int,
        mock_frame_height_px: int,
    ) -> None:
        self.model = None if mock_mode else YOLO(model_path)
        self.source = source
        self.device_id = device_id
        self.server_base_url = server_base_url.rstrip("/")
        self.location_label = location_label
        self.confidence = confidence
        self.class_id = class_id
        self.assumed_face_width_m = assumed_face_width_m
        self.min_person_space_sqm = min_person_space_sqm
        self.post_min_interval_s = post_min_interval_s
        self.post_max_interval_s = post_max_interval_s
        self.show_preview = show_preview
        self.mock_mode = mock_mode
        self.mock_min_faces = mock_min_faces
        self.mock_max_faces = mock_max_faces
        self.mock_min_box_width_px = mock_min_box_width_px
        self.mock_max_box_width_px = mock_max_box_width_px
        self.mock_frame_width_px = mock_frame_width_px
        self.mock_frame_height_px = mock_frame_height_px
        self._running = True

    def run(self) -> None:
        self._register_signal_handlers()

        if self.location_label:
            self._register_device_location()

        if self.mock_mode:
            self._run_mock_loop()
            return

        capture = self._open_capture(self.source)
        next_post_at = time.time() + self._random_post_interval()

        while self._running:
            ok, frame = capture.read()
            if not ok:
                print("Video stream ended or frame read failed.")
                break

            face_widths = self._infer_face_widths(frame)
            estimate = self._estimate_density(frame.shape, face_widths)

            if self.show_preview:
                annotated = self._annotate_frame(frame.copy(), face_widths, estimate)
                cv2.imshow("edge-device", annotated)
                key = cv2.waitKey(1)
                if key in (27, ord("q")):
                    self._running = False

            now = time.time()
            if now >= next_post_at:
                self._post_update(estimate)
                next_post_at = now + self._random_post_interval()

        capture.release()
        if self.show_preview:
            cv2.destroyAllWindows()

    def _run_mock_loop(self) -> None:
        frame_shape = (self.mock_frame_height_px, self.mock_frame_width_px, 3)
        next_post_at = time.time() + self._random_post_interval()

        while self._running:
            face_widths = self._generate_mock_face_widths()
            estimate = self._estimate_density(frame_shape, face_widths)

            if self.show_preview:
                frame = np.zeros(frame_shape, dtype=np.uint8)
                annotated = self._annotate_frame(frame, face_widths, estimate)
                cv2.imshow("edge-device-mock", annotated)
                key = cv2.waitKey(1)
                if key in (27, ord("q")):
                    self._running = False

            now = time.time()
            if now >= next_post_at:
                self._post_update(estimate)
                next_post_at = now + self._random_post_interval()

            time.sleep(0.05)

        if self.show_preview:
            cv2.destroyAllWindows()

    def _generate_mock_face_widths(self) -> list[float]:
        face_count = random.randint(self.mock_min_faces, self.mock_max_faces)
        return [
            random.uniform(self.mock_min_box_width_px, self.mock_max_box_width_px)
            for _ in range(face_count)
        ]

    def _infer_face_widths(self, frame: np.ndarray) -> list[float]:
        if self.model is None:
            return []

        results = self.model.predict(
            frame,
            conf=self.confidence,
            verbose=False,
            classes=[self.class_id],
        )
        if not results:
            return []

        boxes = results[0].boxes
        if boxes is None or boxes.xyxy is None:
            return []

        xyxy_raw = boxes.xyxy
        cpu_method = getattr(xyxy_raw, "cpu", None)
        if callable(cpu_method):
            tensor_like: Any = cpu_method()
            xyxy = np.asarray(tensor_like.numpy())
        else:
            xyxy = np.asarray(xyxy_raw)
        widths = [max(0.0, float(x2 - x1)) for x1, _, x2, _ in xyxy if x2 > x1]
        return widths

    def _estimate_density(
        self, frame_shape: tuple[int, ...], face_widths_px: Iterable[float]
    ) -> DensityEstimate:
        height_px, width_px = frame_shape[:2]
        widths = [w for w in face_widths_px if w > 1.0]
        people_count = len(widths)

        if people_count == 0:
            return DensityEstimate(
                people_count=0,
                scene_area_sqm=0.0,
                occupied_area_sqm=0.0,
                available_area_sqm=0.0,
                crowd_density_ppsqm=0.0,
                risk_score=0.0,
            )

        median_face_width_px = float(np.median(np.array(widths, dtype=np.float32)))
        meters_per_pixel = self.assumed_face_width_m / max(median_face_width_px, 1.0)

        scene_area_sqm = max(
            (width_px * meters_per_pixel) * (height_px * meters_per_pixel), 1e-6
        )
        occupied_area_sqm = people_count * self.min_person_space_sqm
        available_area_sqm = max(scene_area_sqm - occupied_area_sqm, 0.0)
        crowd_density_ppsqm = people_count / scene_area_sqm
        risk_score = self._compute_risk(
            crowd_density_ppsqm, available_area_sqm, scene_area_sqm
        )

        return DensityEstimate(
            people_count=people_count,
            scene_area_sqm=scene_area_sqm,
            occupied_area_sqm=occupied_area_sqm,
            available_area_sqm=available_area_sqm,
            crowd_density_ppsqm=crowd_density_ppsqm,
            risk_score=risk_score,
        )

    @staticmethod
    def _compute_risk(
        density_ppsqm: float, available_sqm: float, scene_sqm: float
    ) -> float:
        safe_density = 1.5
        dangerous_density = 5.5
        density_component = (density_ppsqm - safe_density) / (
            dangerous_density - safe_density
        )
        density_component = float(np.clip(density_component, 0.0, 1.0))

        if scene_sqm <= 1e-6:
            available_ratio = 0.0
        else:
            available_ratio = available_sqm / scene_sqm
        crowding_component = 1.0 - float(np.clip(available_ratio, 0.0, 1.0))

        risk = 0.75 * density_component + 0.25 * crowding_component
        return float(np.clip(risk, 0.0, 1.0))

    def _post_update(self, estimate: DensityEstimate) -> None:
        status = "active"
        
        payload = {
            "device_id": self.device_id,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": status,
            "metrics": {
                "people_count": estimate.people_count,
                "crowd_density": round(estimate.crowd_density_ppsqm, 6),
                "threshold": round(estimate.risk_score, 6),
            },
        }

        url = f"{self.server_base_url}/db/push"
        self._post_json(url, payload)
        print(
            "Posted update:",
            json.dumps(
                {
                    "people_count": estimate.people_count,
                    "crowd_density_ppsqm": round(estimate.crowd_density_ppsqm, 3),
                    "risk": round(estimate.risk_score, 3),
                    "available_area_sqm": round(estimate.available_area_sqm, 2),
                }
            ),
        )

    def _register_device_location(self) -> None:
        payload = {
            "device_id": self.device_id,
            "location_label": self.location_label,
        }
        url = f"{self.server_base_url}/devices/location"
        self._post_json(url, payload)
        print(f"Registered location for {self.device_id}: {self.location_label}")

    @staticmethod
    def _open_capture(source: str) -> cv2.VideoCapture:
        capture: cv2.VideoCapture
        if source.isdigit():
            capture = cv2.VideoCapture(int(source))
        else:
            capture = cv2.VideoCapture(source)

        if not capture.isOpened():
            raise RuntimeError(f"Failed to open video source: {source}")
        return capture

    @staticmethod
    def _post_json(url: str, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with request.urlopen(req, timeout=5) as response:
                if response.status >= 300:
                    raise RuntimeError(f"HTTP {response.status} from {url}")
        except error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"Request failed ({exc.code}) {url}: {response_body}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Request failed {url}: {exc.reason}") from exc

    def _random_post_interval(self) -> float:
        return random.uniform(self.post_min_interval_s, self.post_max_interval_s)

    def _register_signal_handlers(self) -> None:
        def _handle_stop(_signum: int, _frame: object) -> None:
            self._running = False

        signal.signal(signal.SIGINT, _handle_stop)
        signal.signal(signal.SIGTERM, _handle_stop)

    @staticmethod
    def _annotate_frame(
        frame: np.ndarray, widths_px: list[float], estimate: DensityEstimate
    ) -> np.ndarray:
        overlay = [
            f"Faces: {estimate.people_count}",
            f"Density: {estimate.crowd_density_ppsqm:.2f} ppl/sqm",
            f"Risk: {estimate.risk_score:.2f}",
            f"Avail area: {estimate.available_area_sqm:.2f} sqm",
        ]

        y = 30
        for text in overlay:
            cv2.putText(
                frame, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2
            )
            y += 28

        if widths_px:
            med = float(np.median(np.array(widths_px, dtype=np.float32)))
            cv2.putText(
                frame,
                f"Median bbox width(px): {med:.1f}",
                (16, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 255),
                2,
            )
        return frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Edge device crowd-risk estimator using YOLO detections"
    )
    parser.add_argument("--model", default="", help="Path to YOLO model weights (.pt)")
    parser.add_argument(
        "--source",
        default="0",
        help="Video source: webcam index, RTSP URL, or video file path",
    )
    parser.add_argument("--device-id", required=True, help="Device ID used by backend")
    parser.add_argument(
        "--server-url", default="http://localhost:8080", help="Backend base URL"
    )
    parser.add_argument(
        "--location-label",
        default=None,
        help="Optional location; if set, auto-register via API",
    )
    parser.add_argument(
        "--class-id", type=int, default=0, help="Detection class id to treat as faces"
    )
    parser.add_argument(
        "--conf", type=float, default=0.35, help="Detection confidence threshold"
    )
    parser.add_argument(
        "--assumed-face-width-m",
        type=float,
        default=0.16,
        help="Assumed real-world average face width in meters",
    )
    parser.add_argument(
        "--min-person-space-sqm",
        type=float,
        default=0.35,
        help="Minimum area occupied per person in square meters",
    )
    parser.add_argument(
        "--post-min-s",
        type=float,
        default=10.0,
        help="Minimum posting interval in seconds",
    )
    parser.add_argument(
        "--post-max-s",
        type=float,
        default=15.0,
        help="Maximum posting interval in seconds",
    )
    parser.add_argument(
        "--preview", action="store_true", help="Show annotated preview window"
    )
    parser.add_argument(
        "--mock-mode",
        action="store_true",
        help="Run without model/video by randomizing bounding-box widths",
    )
    parser.add_argument(
        "--mock-min-faces",
        type=int,
        default=5,
        help="Minimum randomized face detections per cycle in mock mode",
    )
    parser.add_argument(
        "--mock-max-faces",
        type=int,
        default=80,
        help="Maximum randomized face detections per cycle in mock mode",
    )
    parser.add_argument(
        "--mock-min-box-width-px",
        type=float,
        default=24.0,
        help="Minimum randomized face box width in pixels in mock mode",
    )
    parser.add_argument(
        "--mock-max-box-width-px",
        type=float,
        default=110.0,
        help="Maximum randomized face box width in pixels in mock mode",
    )
    parser.add_argument(
        "--mock-frame-width-px",
        type=int,
        default=1280,
        help="Mock frame width for density estimation",
    )
    parser.add_argument(
        "--mock-frame-height-px",
        type=int,
        default=720,
        help="Mock frame height for density estimation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if (
        args.post_min_s <= 0
        or args.post_max_s <= 0
        or args.post_min_s > args.post_max_s
    ):
        raise ValueError("Invalid post interval bounds")

    if not args.mock_mode and not args.model:
        raise ValueError("--model is required unless --mock-mode is enabled")
    if args.mock_min_faces < 0 or args.mock_max_faces < args.mock_min_faces:
        raise ValueError("Invalid mock face count bounds")
    if (
        args.mock_min_box_width_px <= 0
        or args.mock_max_box_width_px < args.mock_min_box_width_px
    ):
        raise ValueError("Invalid mock box width bounds")
    if args.mock_frame_width_px <= 0 or args.mock_frame_height_px <= 0:
        raise ValueError("Invalid mock frame size")

    runner = EdgeDeviceRunner(
        model_path=args.model,
        source=args.source,
        device_id=args.device_id,
        server_base_url=args.server_url,
        location_label=args.location_label,
        confidence=args.conf,
        class_id=args.class_id,
        assumed_face_width_m=args.assumed_face_width_m,
        min_person_space_sqm=args.min_person_space_sqm,
        post_min_interval_s=args.post_min_s,
        post_max_interval_s=args.post_max_s,
        show_preview=args.preview,
        mock_mode=args.mock_mode,
        mock_min_faces=args.mock_min_faces,
        mock_max_faces=args.mock_max_faces,
        mock_min_box_width_px=args.mock_min_box_width_px,
        mock_max_box_width_px=args.mock_max_box_width_px,
        mock_frame_width_px=args.mock_frame_width_px,
        mock_frame_height_px=args.mock_frame_height_px,
    )
    runner.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)

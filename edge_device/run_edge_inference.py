import argparse
import math
import json
import random
import signal
import sys
import time
from collections import deque
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


@dataclass
class MotionMetrics:
    primary_flow_deg: float
    counterflow_ratio: float
    counterflow_flag: bool
    shockwave_score: float
    shockwave_flag: bool
    acceleration_variance: float
    lateral_displacement_spike_ratio: float
    microsurge_score: float
    turbulence_index: float


@dataclass
class TrackState:
    centroid: tuple[float, float]
    velocity: tuple[float, float]
    previous_velocity: tuple[float, float]
    last_seen_at: float


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
        focal_length_px: float,
        min_person_space_sqm: float,
        post_min_interval_s: float,
        post_max_interval_s: float,
        show_preview: bool,
        mock_mode: bool,
        mock_face_mean: float,
        mock_face_sd: float,
        mock_min_box_width_px: float,
        mock_max_box_width_px: float,
        mock_frame_width_px: int,
        mock_frame_height_px: int,
        track_max_match_px: float,
        track_ttl_s: float,
        min_track_speed_px_s: float,
        counterflow_ratio_threshold: float,
        min_counterflow_tracks: int,
        shockwave_velocity_drop_ratio: float,
        shockwave_cluster_ratio: float,
        lateral_spike_ratio_threshold: float,
    ) -> None:
        self.model = None if mock_mode else YOLO(model_path)
        self.source = source
        self.device_id = device_id
        self.server_base_url = server_base_url.rstrip("/")
        self.location_label = location_label
        self.confidence = confidence
        self.class_id = class_id
        self.assumed_face_width_m = assumed_face_width_m
        self.focal_length_px = focal_length_px
        self.min_person_space_sqm = min_person_space_sqm
        self.post_min_interval_s = post_min_interval_s
        self.post_max_interval_s = post_max_interval_s
        self.show_preview = show_preview
        self.mock_mode = mock_mode
        self.mock_face_mean = mock_face_mean
        self.mock_face_sd = mock_face_sd
        self.mock_min_box_width_px = mock_min_box_width_px
        self.mock_max_box_width_px = mock_max_box_width_px
        self.mock_frame_width_px = mock_frame_width_px
        self.mock_frame_height_px = mock_frame_height_px
        self.track_max_match_px = track_max_match_px
        self.track_ttl_s = track_ttl_s
        self.min_track_speed_px_s = min_track_speed_px_s
        self.counterflow_ratio_threshold = counterflow_ratio_threshold
        self.min_counterflow_tracks = min_counterflow_tracks
        self.shockwave_velocity_drop_ratio = shockwave_velocity_drop_ratio
        self.shockwave_cluster_ratio = shockwave_cluster_ratio
        self.lateral_spike_ratio_threshold = lateral_spike_ratio_threshold

        self._tracks: dict[int, TrackState] = {}
        self._next_track_id = 1
        self._previous_gray: np.ndarray | None = None
        self._previous_velocity_mean: float | None = None
        self._acceleration_var_history: deque[float] = deque(maxlen=30)
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
        last_estimate = DensityEstimate(0, 0.0, 0.0, 0.0, 0.0, 0.0)
        last_motion_metrics = self._zero_motion_metrics()
        last_enhanced_risk = 0.0

        while self._running:
            ok, frame = capture.read()
            if not ok:
                print("Video stream ended or frame read failed.")
                break

            detections = self._infer_detections(frame)
            face_widths = [max(0.0, float(x2 - x1)) for x1, _, x2, _ in detections]
            estimate = self._estimate_density(frame.shape, face_widths)
            motion_metrics = self._compute_motion_metrics(frame, detections)
            enhanced_risk = self._compute_enhanced_risk(
                estimate.risk_score, motion_metrics
            )
            status = "active"
            last_estimate = estimate
            last_motion_metrics = motion_metrics
            last_enhanced_risk = enhanced_risk

            if self.show_preview:
                annotated = self._annotate_frame(
                    frame.copy(),
                    face_widths,
                    estimate,
                    motion_metrics,
                    enhanced_risk,
                    status,
                )
                cv2.imshow("edge-device", annotated)
                key = cv2.waitKey(1)
                if key in (27, ord("q")):
                    self._running = False

            now = time.time()
            if now >= next_post_at:
                self._post_update(estimate, enhanced_risk, status, motion_metrics)
                next_post_at = now + self._random_post_interval()

        capture.release()
        self._post_inactive_update(
            last_estimate, last_enhanced_risk, last_motion_metrics
        )
        if self.show_preview:
            cv2.destroyAllWindows()

    def _run_mock_loop(self) -> None:
        frame_shape = (self.mock_frame_height_px, self.mock_frame_width_px, 3)
        next_post_at = time.time() + self._random_post_interval()
        last_estimate = DensityEstimate(0, 0.0, 0.0, 0.0, 0.0, 0.0)
        last_motion_metrics = self._zero_motion_metrics()
        last_enhanced_risk = 0.0

        while self._running:
            face_widths = self._generate_mock_face_widths()
            estimate = self._estimate_density(frame_shape, face_widths)
            motion_metrics = self._zero_motion_metrics()
            enhanced_risk = self._compute_enhanced_risk(
                estimate.risk_score, motion_metrics
            )
            status = "active"
            last_estimate = estimate
            last_motion_metrics = motion_metrics
            last_enhanced_risk = enhanced_risk

            if self.show_preview:
                frame = np.zeros(frame_shape, dtype=np.uint8)
                annotated = self._annotate_frame(
                    frame,
                    face_widths,
                    estimate,
                    motion_metrics,
                    enhanced_risk,
                    status,
                )
                cv2.imshow("edge-device-mock", annotated)
                key = cv2.waitKey(1)
                if key in (27, ord("q")):
                    self._running = False

            now = time.time()
            if now >= next_post_at:
                self._post_update(estimate, enhanced_risk, status, motion_metrics)
                next_post_at = now + self._random_post_interval()

            time.sleep(0.05)

        self._post_inactive_update(
            last_estimate, last_enhanced_risk, last_motion_metrics
        )
        if self.show_preview:
            cv2.destroyAllWindows()

    def _generate_mock_face_widths(self) -> list[float]:
        sampled_faces = random.gauss(self.mock_face_mean, self.mock_face_sd)
        face_count = max(0, int(round(sampled_faces)))
        return [
            random.uniform(self.mock_min_box_width_px, self.mock_max_box_width_px)
            for _ in range(face_count)
        ]

    def _infer_detections(
        self, frame: np.ndarray
    ) -> list[tuple[float, float, float, float]]:
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
        detections: list[tuple[float, float, float, float]] = []
        for x1, y1, x2, y2 in xyxy:
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append((float(x1), float(y1), float(x2), float(y2)))
        return detections

    @staticmethod
    def _centroid(box: tuple[float, float, float, float]) -> tuple[float, float]:
        x1, y1, x2, y2 = box
        return ((x1 + x2) * 0.5, (y1 + y2) * 0.5)

    @staticmethod
    def _angle_deg(vector_x: float, vector_y: float) -> float:
        return float((math.degrees(math.atan2(vector_y, vector_x)) + 360.0) % 360.0)

    @staticmethod
    def _vector_speed(vector: tuple[float, float]) -> float:
        return float(math.hypot(vector[0], vector[1]))

    def _track_vectors(
        self,
        detections: list[tuple[float, float, float, float]],
        now: float,
    ) -> tuple[list[tuple[float, float]], list[float]]:
        self._tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if (now - track.last_seen_at) <= self.track_ttl_s
        }

        centroids = [self._centroid(box) for box in detections]
        unmatched_detection_ids = set(range(len(centroids)))
        matched_track_ids: set[int] = set()
        current_vectors: list[tuple[float, float]] = []
        normalized_accelerations: list[float] = []

        for track_id, track in list(self._tracks.items()):
            nearest_detection_id = None
            nearest_distance = float("inf")
            for detection_id in unmatched_detection_ids:
                centroid_x, centroid_y = centroids[detection_id]
                delta_x = centroid_x - track.centroid[0]
                delta_y = centroid_y - track.centroid[1]
                distance = float(math.hypot(delta_x, delta_y))
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_detection_id = detection_id

            if (
                nearest_detection_id is None
                or nearest_distance > self.track_max_match_px
            ):
                continue

            matched_track_ids.add(track_id)
            unmatched_detection_ids.discard(nearest_detection_id)

            previous_centroid = track.centroid
            centroid_x, centroid_y = centroids[nearest_detection_id]
            time_delta = max(now - track.last_seen_at, 1e-3)
            velocity = (
                (centroid_x - previous_centroid[0]) / time_delta,
                (centroid_y - previous_centroid[1]) / time_delta,
            )
            speed = self._vector_speed(velocity)

            acceleration_x = (velocity[0] - track.velocity[0]) / time_delta
            acceleration_y = (velocity[1] - track.velocity[1]) / time_delta
            acceleration_norm = float(math.hypot(acceleration_x, acceleration_y)) / (
                speed + 1e-6
            )

            track.previous_velocity = track.velocity
            track.velocity = velocity
            track.centroid = (centroid_x, centroid_y)
            track.last_seen_at = now

            if speed >= self.min_track_speed_px_s:
                current_vectors.append(velocity)
                normalized_accelerations.append(acceleration_norm)

        for detection_id in unmatched_detection_ids:
            centroid = centroids[detection_id]
            self._tracks[self._next_track_id] = TrackState(
                centroid=centroid,
                velocity=(0.0, 0.0),
                previous_velocity=(0.0, 0.0),
                last_seen_at=now,
            )
            self._next_track_id += 1

        if len(normalized_accelerations) >= 2:
            acceleration_variance = float(np.var(np.array(normalized_accelerations)))
        else:
            acceleration_variance = 0.0

        self._acceleration_var_history.append(acceleration_variance)
        return current_vectors, list(normalized_accelerations)

    def _compute_motion_metrics(
        self,
        frame: np.ndarray,
        detections: list[tuple[float, float, float, float]],
    ) -> MotionMetrics:
        now = time.time()
        track_vectors, _ = self._track_vectors(detections, now)

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._previous_gray is None:
            self._previous_gray = gray_frame
            return self._zero_motion_metrics()

        initial_flow = np.zeros(
            (gray_frame.shape[0], gray_frame.shape[1], 2), dtype=np.float32
        )
        flow = cv2.calcOpticalFlowFarneback(
            self._previous_gray,
            gray_frame,
            initial_flow,
            0.5,
            3,
            15,
            3,
            5,
            1.2,
            0,
        )
        self._previous_gray = gray_frame

        flow_x = flow[..., 0]
        flow_y = flow[..., 1]
        magnitude = cv2.magnitude(flow_x, flow_y)

        if track_vectors:
            average_vector_x = float(np.mean([vec[0] for vec in track_vectors]))
            average_vector_y = float(np.mean([vec[1] for vec in track_vectors]))
            primary_flow_deg = self._angle_deg(average_vector_x, average_vector_y)
            primary_unit = np.array(
                [average_vector_x, average_vector_y], dtype=np.float32
            )
            primary_norm = float(np.linalg.norm(primary_unit))
            if primary_norm > 1e-6:
                primary_unit = primary_unit / primary_norm
            else:
                primary_unit = np.array([1.0, 0.0], dtype=np.float32)
        else:
            median_index = np.unravel_index(np.argmax(magnitude), magnitude.shape)
            flow_vector = np.array(
                [
                    float(flow_x[median_index]),
                    float(flow_y[median_index]),
                ],
                dtype=np.float32,
            )
            norm = float(np.linalg.norm(flow_vector))
            if norm <= 1e-6:
                primary_unit = np.array([1.0, 0.0], dtype=np.float32)
                primary_flow_deg = 0.0
            else:
                primary_unit = flow_vector / norm
                primary_flow_deg = self._angle_deg(
                    float(primary_unit[0]), float(primary_unit[1])
                )

        opposing_count = 0
        for vector_x, vector_y in track_vectors:
            vector_norm = float(math.hypot(vector_x, vector_y))
            if vector_norm <= self.min_track_speed_px_s:
                continue
            cosine_similarity = (
                (vector_x * float(primary_unit[0]))
                + (vector_y * float(primary_unit[1]))
            ) / (vector_norm + 1e-6)
            if cosine_similarity < -0.5:
                opposing_count += 1

        valid_track_count = len(track_vectors)
        counterflow_ratio = (
            float(opposing_count) / float(valid_track_count)
            if valid_track_count > 0
            else 0.0
        )
        counterflow_flag = (
            opposing_count >= self.min_counterflow_tracks
            and counterflow_ratio >= self.counterflow_ratio_threshold
        )

        if detections:
            velocity_samples: list[float] = []
            low_velocity_count = 0
            total_sample_count = 0
            for x1, y1, x2, y2 in detections:
                left = max(int(x1), 0)
                top = max(int(y1), 0)
                right = min(int(x2), magnitude.shape[1] - 1)
                bottom = min(int(y2), magnitude.shape[0] - 1)
                if right <= left or bottom <= top:
                    continue
                region = magnitude[top:bottom, left:right]
                if region.size == 0:
                    continue
                mean_region_velocity = float(np.mean(region))
                velocity_samples.append(mean_region_velocity)
                low_velocity_count += int(np.sum(region < mean_region_velocity * 0.5))
                total_sample_count += int(region.size)
            velocity_mean = (
                float(np.mean(np.array(velocity_samples)))
                if velocity_samples
                else float(np.mean(magnitude))
            )
            low_velocity_ratio = (
                float(low_velocity_count) / float(total_sample_count)
                if total_sample_count > 0
                else 0.0
            )
        else:
            velocity_mean = float(np.mean(magnitude))
            low_velocity_ratio = float(np.mean(magnitude < (velocity_mean * 0.5)))

        if self._previous_velocity_mean is None:
            drop_ratio = 0.0
        else:
            drop_ratio = max(
                (self._previous_velocity_mean - velocity_mean)
                / max(self._previous_velocity_mean, 1e-6),
                0.0,
            )

        self._previous_velocity_mean = velocity_mean
        shockwave_score = float(np.clip(drop_ratio, 0.0, 1.0))
        shockwave_flag = (
            drop_ratio >= self.shockwave_velocity_drop_ratio
            and low_velocity_ratio >= self.shockwave_cluster_ratio
        )

        if valid_track_count >= 2:
            speeds = np.array(
                [self._vector_speed(vector) for vector in track_vectors],
                dtype=np.float32,
            )
            speed_scale = float(np.mean(speeds)) + 1e-6
            acceleration_variance = float(np.var(speeds / speed_scale))
        else:
            acceleration_variance = 0.0

        lateral_unit = np.array([-primary_unit[1], primary_unit[0]], dtype=np.float32)
        lateral_spikes = 0
        for vector_x, vector_y in track_vectors:
            speed = float(math.hypot(vector_x, vector_y))
            if speed <= self.min_track_speed_px_s:
                continue
            lateral_component = abs(
                vector_x * float(lateral_unit[0]) + vector_y * float(lateral_unit[1])
            )
            lateral_ratio = lateral_component / (speed + 1e-6)
            if lateral_ratio >= self.lateral_spike_ratio_threshold:
                lateral_spikes += 1

        lateral_displacement_spike_ratio = (
            float(lateral_spikes) / float(valid_track_count)
            if valid_track_count > 0
            else 0.0
        )

        magnitude_flat = magnitude.reshape(-1)
        median_velocity = float(np.median(magnitude_flat))
        high_quantile_velocity = float(np.percentile(magnitude_flat, 90))
        microsurge_score = float(
            np.clip(
                (high_quantile_velocity - median_velocity)
                / max(3.0 * median_velocity, 1e-6),
                0.0,
                1.0,
            )
        )

        acceleration_norm = float(np.clip(acceleration_variance / 0.25, 0.0, 1.0))
        turbulence_index = float(
            np.clip(
                0.35 * acceleration_norm
                + 0.30 * lateral_displacement_spike_ratio
                + 0.20 * microsurge_score
                + 0.15 * shockwave_score,
                0.0,
                1.0,
            )
        )

        return MotionMetrics(
            primary_flow_deg=primary_flow_deg,
            counterflow_ratio=counterflow_ratio,
            counterflow_flag=counterflow_flag,
            shockwave_score=shockwave_score,
            shockwave_flag=shockwave_flag,
            acceleration_variance=acceleration_variance,
            lateral_displacement_spike_ratio=lateral_displacement_spike_ratio,
            microsurge_score=microsurge_score,
            turbulence_index=turbulence_index,
        )

    @staticmethod
    def _zero_motion_metrics() -> MotionMetrics:
        return MotionMetrics(
            primary_flow_deg=0.0,
            counterflow_ratio=0.0,
            counterflow_flag=False,
            shockwave_score=0.0,
            shockwave_flag=False,
            acceleration_variance=0.0,
            lateral_displacement_spike_ratio=0.0,
            microsurge_score=0.0,
            turbulence_index=0.0,
        )

    @staticmethod
    def _compute_enhanced_risk(
        density_risk: float,
        motion_metrics: MotionMetrics,
    ) -> float:
        flow_conflict = max(
            motion_metrics.counterflow_ratio,
            motion_metrics.shockwave_score,
        )
        enhanced_risk = (
            0.60 * density_risk
            + 0.20 * flow_conflict
            + 0.20 * motion_metrics.turbulence_index
        )
        return float(np.clip(enhanced_risk, 0.0, 1.0))

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
        distance_m = (self.focal_length_px * self.assumed_face_width_m) / max(
            median_face_width_px, 1.0
        )
        scene_width_m = (distance_m * width_px) / max(self.focal_length_px, 1e-6)
        scene_height_m = (distance_m * height_px) / max(self.focal_length_px, 1e-6)
        scene_area_sqm = max(scene_width_m * scene_height_m, 1e-6)
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

    def _post_update(
        self,
        estimate: DensityEstimate,
        enhanced_risk: float,
        status: str,
        motion_metrics: MotionMetrics,
    ) -> None:
        payload = {
            "device_id": self.device_id,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": status,
            "metrics": {
                "people_count": estimate.people_count,
                "crowd_density": round(estimate.crowd_density_ppsqm, 6),
                "threshold": round(enhanced_risk, 6),
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
                    "risk": round(enhanced_risk, 3),
                    "available_area_sqm": round(estimate.available_area_sqm, 2),
                    "status": status,
                    "primary_flow_deg": round(motion_metrics.primary_flow_deg, 1),
                    "counterflow_ratio": round(motion_metrics.counterflow_ratio, 3),
                    "shockwave_score": round(motion_metrics.shockwave_score, 3),
                    "turbulence_index": round(motion_metrics.turbulence_index, 3),
                }
            ),
        )

    def _post_inactive_update(
        self,
        estimate: DensityEstimate,
        enhanced_risk: float,
        motion_metrics: MotionMetrics,
    ) -> None:
        try:
            self._post_update(estimate, enhanced_risk, "inactive", motion_metrics)
        except Exception as exc:
            print(f"Failed to post inactive update: {exc}")

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
        frame: np.ndarray,
        widths_px: list[float],
        estimate: DensityEstimate,
        motion_metrics: MotionMetrics,
        enhanced_risk: float,
        status: str,
    ) -> np.ndarray:
        overlay = [
            f"Faces: {estimate.people_count}",
            f"Density: {estimate.crowd_density_ppsqm:.2f} ppl/sqm",
            f"Risk: {enhanced_risk:.2f}",
            f"Camera: {status}",
            f"Avail area: {estimate.available_area_sqm:.2f} sqm",
            f"Primary flow: {motion_metrics.primary_flow_deg:.1f} deg",
            f"Counterflow: {motion_metrics.counterflow_ratio:.2f}",
            f"Shockwave: {motion_metrics.shockwave_score:.2f}",
            f"Turbulence idx: {motion_metrics.turbulence_index:.2f}",
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
        "--focal-length-px",
        type=float,
        default=320.0,
        help="Camera focal length in pixels for distance/FOV density geometry",
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
        default=1.0,
        help="Minimum posting interval in seconds",
    )
    parser.add_argument(
        "--post-max-s",
        type=float,
        default=3.0,
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
        "--mock-face-mean",
        type=float,
        default=500.0,
        help="Mean face detections per cycle in mock mode (Gaussian)",
    )
    parser.add_argument(
        "--mock-face-sd",
        type=float,
        default=80.0,
        help="Standard deviation of face detections per cycle in mock mode (Gaussian)",
    )
    parser.add_argument(
        "--mock-min-box-width-px",
        type=float,
        default=3.0,
        help="Minimum randomized face box width in pixels in mock mode",
    )
    parser.add_argument(
        "--mock-max-box-width-px",
        type=float,
        default=20.0,
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
    parser.add_argument(
        "--track-max-match-px",
        type=float,
        default=120.0,
        help="Maximum centroid distance for matching detections across frames",
    )
    parser.add_argument(
        "--track-ttl-s",
        type=float,
        default=1.0,
        help="Track time-to-live in seconds without new detections",
    )
    parser.add_argument(
        "--min-track-speed-px-s",
        type=float,
        default=8.0,
        help="Minimum track speed to count as directional movement",
    )
    parser.add_argument(
        "--counterflow-ratio-threshold",
        type=float,
        default=0.25,
        help="Ratio threshold to flag dangerous opposing flow",
    )
    parser.add_argument(
        "--min-counterflow-tracks",
        type=int,
        default=4,
        help="Minimum number of opposing tracks before counterflow alert",
    )
    parser.add_argument(
        "--shockwave-velocity-drop-ratio",
        type=float,
        default=0.35,
        help="Relative velocity drop threshold for stop-start shockwave detection",
    )
    parser.add_argument(
        "--shockwave-cluster-ratio",
        type=float,
        default=0.40,
        help="Fraction of low-velocity pixels needed to confirm shockwave",
    )
    parser.add_argument(
        "--lateral-spike-ratio-threshold",
        type=float,
        default=0.60,
        help="Lateral-to-total motion ratio above which motion is a displacement spike",
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
    if args.focal_length_px <= 0:
        raise ValueError("--focal-length-px must be > 0")
    if args.mock_face_mean < 0:
        raise ValueError("--mock-face-mean must be >= 0")
    if args.mock_face_sd < 0:
        raise ValueError("--mock-face-sd must be >= 0")
    if (
        args.mock_min_box_width_px <= 0
        or args.mock_max_box_width_px < args.mock_min_box_width_px
    ):
        raise ValueError("Invalid mock box width bounds")
    if args.mock_frame_width_px <= 0 or args.mock_frame_height_px <= 0:
        raise ValueError("Invalid mock frame size")
    if args.track_max_match_px <= 0:
        raise ValueError("--track-max-match-px must be > 0")
    if args.track_ttl_s <= 0:
        raise ValueError("--track-ttl-s must be > 0")
    if args.min_track_speed_px_s < 0:
        raise ValueError("--min-track-speed-px-s must be >= 0")
    if not (0.0 <= args.counterflow_ratio_threshold <= 1.0):
        raise ValueError("--counterflow-ratio-threshold must be within [0, 1]")
    if args.min_counterflow_tracks < 1:
        raise ValueError("--min-counterflow-tracks must be >= 1")
    if not (0.0 <= args.shockwave_velocity_drop_ratio <= 1.0):
        raise ValueError("--shockwave-velocity-drop-ratio must be within [0, 1]")
    if not (0.0 <= args.shockwave_cluster_ratio <= 1.0):
        raise ValueError("--shockwave-cluster-ratio must be within [0, 1]")
    if not (0.0 <= args.lateral_spike_ratio_threshold <= 1.0):
        raise ValueError("--lateral-spike-ratio-threshold must be within [0, 1]")

    runner = EdgeDeviceRunner(
        model_path=args.model,
        source=args.source,
        device_id=args.device_id,
        server_base_url=args.server_url,
        location_label=args.location_label,
        confidence=args.conf,
        class_id=args.class_id,
        assumed_face_width_m=args.assumed_face_width_m,
        focal_length_px=args.focal_length_px,
        min_person_space_sqm=args.min_person_space_sqm,
        post_min_interval_s=args.post_min_s,
        post_max_interval_s=args.post_max_s,
        show_preview=args.preview,
        mock_mode=args.mock_mode,
        mock_face_mean=args.mock_face_mean,
        mock_face_sd=args.mock_face_sd,
        mock_min_box_width_px=args.mock_min_box_width_px,
        mock_max_box_width_px=args.mock_max_box_width_px,
        mock_frame_width_px=args.mock_frame_width_px,
        mock_frame_height_px=args.mock_frame_height_px,
        track_max_match_px=args.track_max_match_px,
        track_ttl_s=args.track_ttl_s,
        min_track_speed_px_s=args.min_track_speed_px_s,
        counterflow_ratio_threshold=args.counterflow_ratio_threshold,
        min_counterflow_tracks=args.min_counterflow_tracks,
        shockwave_velocity_drop_ratio=args.shockwave_velocity_drop_ratio,
        shockwave_cluster_ratio=args.shockwave_cluster_ratio,
        lateral_spike_ratio_threshold=args.lateral_spike_ratio_threshold,
    )
    runner.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)

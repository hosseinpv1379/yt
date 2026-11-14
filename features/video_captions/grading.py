"""CPU person segmentation and temporally smoothed color grading."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GradeSettings:
    background_brightness: float = 0.55
    background_saturation: float = 0.80
    subject_saturation: float = 1.25
    contrast: float = 1.10
    mask_smoothing: float = 0.75
    mask_blur: float = 13.0
    minimum_subject: float = 0.01


class Grader:
    def __init__(self, settings: GradeSettings = GradeSettings()):
        import mediapipe as mp
        self.settings = settings
        self.segmenter = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0)
        self.previous = None

    def close(self):
        self.segmenter.close()

    def frame(self, frame):
        import cv2
        import numpy as np
        config = self.settings
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mask = self.segmenter.process(rgb).segmentation_mask.astype(np.float32)
        mask = cv2.GaussianBlur(mask, (0, 0), config.mask_blur)
        self.previous = mask if self.previous is None else (
            config.mask_smoothing * self.previous + (1 - config.mask_smoothing) * mask
        )
        mask = np.clip((self.previous - 0.2) / 0.6, 0, 1)[..., None]
        image = frame.astype(np.float32) / 255.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)[..., None]
        vivid = np.clip((image - 0.5) * config.contrast + 0.5, 0, 1)
        vivid_gray = cv2.cvtColor(vivid, cv2.COLOR_BGR2GRAY)[..., None]
        vivid = np.clip(vivid_gray + (vivid - vivid_gray) * config.subject_saturation, 0, 1)
        sharpen = cv2.GaussianBlur(vivid, (0, 0), 1.0)
        subject = np.clip(vivid + 0.15 * (vivid - sharpen), 0, 1)
        height, width = frame.shape[:2]
        x = np.linspace(-1, 1, width, dtype=np.float32)[None, :]
        y = np.linspace(-1, 1, height, dtype=np.float32)[:, None]
        vignette = np.clip(1 - 0.20 * (x * x + y * y), 0.60, 1)[..., None]
        if np.mean(mask) < config.minimum_subject:
            result = vivid * vignette
        else:
            background = np.clip(gray + (image - gray) * config.background_saturation, 0, 1)
            background *= config.background_brightness * vignette
            result = subject * mask + background * (1 - mask)
        return (np.clip(result, 0, 1) * 255).astype(np.uint8)

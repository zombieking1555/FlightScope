import cv2
import numpy as np
import os


def create_mp4(frame_cache, output_path="flight.mp4", fps=30):

    if len(frame_cache) == 0:
        raise ValueError("frame_cache is empty")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    first = np.asarray(frame_cache[0])

    height, width = first.shape[:2]

    writer = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*"avc1"),  #type: ignore
        fps,
        (width, height),
    )

    if not writer.isOpened():
        raise RuntimeError(
            "Failed to open VideoWriter. H.264 encoder may not be installed."
        )

    for frame in frame_cache:

        frame = np.asarray(frame)

        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        elif frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

        else:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        writer.write(frame)

    writer.release()

    return output_path
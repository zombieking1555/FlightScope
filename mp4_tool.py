import cv2
import numpy as np
import os

def create_mp4(frame_cache, output_path="flight.mp4", fps=30):

    from pathlib import Path
    import os

    print("CWD:", os.getcwd())
    print("Resolved output:", Path(output_path).resolve())

    # if len(frame_cache) == 0:
    #     raise ValueError("frame_cache is empty")

    # first = frame_cache[0]

    # height, width = first.shape[:2]

    # writer = cv2.VideoWriter(
    #     output_path,
    #     cv2.VideoWriter_fourcc(*"mp4v"), # type: ignore[attr-defined]
    #     fps,
    #     (width, height),
    # )

    # for frame in frame_cache:

    #     frame = np.asarray(frame)

    #     # RGBA -> BGR
    #     if frame.shape[-1] == 4:
    #         frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)

    #     # RGB -> BGR
    #     elif frame.shape[-1] == 3:
    #         frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    #     writer.write(frame)

    # writer.release()

    os.makedirs("cache", exist_ok=True)

    writer = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*"mp4v"), # type: ignore[attr-defined]
        30,
        (640, 480),
    )

    print(writer.isOpened())

    for _ in range(60):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        writer.write(frame)

    writer.release()

    return output_path
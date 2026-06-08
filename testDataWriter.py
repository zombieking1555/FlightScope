import numpy as np
import pandas as pd
from pathlib import Path

output_dir = Path("test_data")

output_dir.mkdir(exist_ok=True)

def generate_flight(seed, apogee_target):
    np.random.seed(seed)

    dt = 0.005  # 200 Hz
    t = np.arange(0, 20, dt)

    altitude = np.zeros_like(t)
    velocity = np.zeros_like(t)

    burn_time = 1.8

    for i in range(1, len(t)):
        time = t[i]

        # BOOST PHASE
        if time < burn_time:
            accel = 60 + np.random.normal(0, 2)
            velocity[i] = velocity[i-1] + accel * dt

        # COAST PHASE
        elif time < 6:
            accel = -9.8 + np.random.normal(0, 0.3)
            velocity[i] = velocity[i-1] + accel * dt

        # DESCENT PHASE (parachute)
        else:
            velocity[i] = max(-5 + np.random.normal(0, 0.5), velocity[i-1] - 0.2)

        altitude[i] = max(0, altitude[i-1] + velocity[i] * dt)

    # scale to target apogee
    altitude *= apogee_target / max(altitude.max(), 1)

    return pd.DataFrame({
        "time": t,
        "altitude": altitude,
        "velocity": velocity
    })


flights = [
    ("test_data/flight_1.csv", 260),
    ("test_data/flight_2.csv", 230),
    ("test_data/flight_3.csv", 300)
]

for i, (name, apogee) in enumerate(flights):
    df = generate_flight(i, apogee)
    df.to_csv(name, index=False)

print("Created 3 new test flights")
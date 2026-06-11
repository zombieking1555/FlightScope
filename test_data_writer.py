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
    acceleration = np.zeros_like(t)

    burn_time = 1.8
    coast_end = 6.0
    transition_time = 0.2  # Smooth transition over 0.2 seconds

    for i in range(1, len(t)):
        time = t[i]

        # BOOST PHASE
        if time < burn_time - transition_time / 2:
            accel = 60 + np.random.normal(0, 2)

        # BOOST TO COAST TRANSITION
        elif time < burn_time + transition_time / 2:
            boost_accel = 60 + np.random.normal(0, 2)
            coast_accel = -9.8 + np.random.normal(0, 0.3)
            # Linear interpolation between phases
            alpha = (time - (burn_time - transition_time / 2)) / transition_time
            accel = boost_accel * (1 - alpha) + coast_accel * alpha

        # COAST PHASE
        elif time < coast_end - transition_time / 2:
            accel = -9.8 + np.random.normal(0, 0.3)

        # COAST TO DESCENT TRANSITION
        elif time < coast_end + transition_time / 2:
            coast_accel = -9.8 + np.random.normal(0, 0.3)
            descent_accel = -9.8 + np.random.normal(0, 0.2)
            # Linear interpolation between phases
            alpha = (time - (coast_end - transition_time / 2)) / transition_time
            accel = coast_accel * (1 - alpha) + descent_accel * alpha

        # DESCENT PHASE (parachute)
        else:
            accel = -9.8 + np.random.normal(0, 0.2)
        
        # Store acceleration and integrate to velocity
        acceleration[i] = accel
        velocity[i] = velocity[i-1] + accel * dt

        # Integrate velocity to altitude
        altitude[i] = altitude[i-1] + velocity[i] * dt

    # Smooth acceleration values with a rolling window
    window_size = 11
    acceleration = pd.Series(acceleration).rolling(window=window_size, center=True, min_periods=1).mean().values

    # Scale to target apogee
    altitude_scale = apogee_target / max(altitude.max(), 1)
    altitude *= altitude_scale
    velocity *= altitude_scale

    return pd.DataFrame({
        "time": t,
        "altitude": altitude,
        "velocity": velocity,
        "acceleration": acceleration
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
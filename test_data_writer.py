import numpy as np
import pandas as pd
from pathlib import Path

output_dir = Path("test_data")
output_dir.mkdir(exist_ok=True)


def generate_flight(seed, apogee_target):
    np.random.seed(seed)

    dt = 0.01  # 100 Hz

    pre_launch_time = 5.0
    post_landing_time = 28.0

    burn_time = 1.8
    parachute_delay = 3.0
    parachute_terminal_vel = -5.0

    g = 9.81

    def simulate_with_boost(a_boost):
        # returns apogee and full traces until landing
        t_list = []
        alt = []
        vel = []
        acc = []

        # pre-launch
        t = 0.0
        while t < pre_launch_time:
            t_list.append(t)
            alt.append(0.0)
            vel.append(0.0)
            acc.append(np.random.normal(0, 0.02))
            t += dt

        # boost
        boost_steps = int(np.ceil(burn_time / dt))
        for _ in range(boost_steps):
            t_list.append(t)
            a_net = a_boost - g + np.random.normal(0, 0.5)
            acc.append(a_net)
            prev_v = vel[-1]
            v = prev_v + a_net * dt
            prev_h = alt[-1]
            h = prev_h + v * dt
            vel.append(v)
            alt.append(h)
            t += dt

        # coast/free-fall until parachute deploy and landing
        apogee = -1.0
        apogee_time = None
        parachute_deployed = False

        while True:
            t_list.append(t)
            if not parachute_deployed:
                a_now = -g + np.random.normal(0, 0.1)
            else:
                # controller to terminal
                a_now = 1.2 * (parachute_terminal_vel - vel[-1]) + np.random.normal(0, 0.1)
            acc.append(a_now)
            v = vel[-1] + a_now * dt
            h = alt[-1] + v * dt
            vel.append(v)
            alt.append(h)

            # detect apogee
            if apogee_time is None and vel[-2] > 0 and vel[-1] <= 0:
                apogee_time = t
                apogee = alt[-1]

            # deploy parachute after delay from apogee
            if (apogee_time is not None) and (not parachute_deployed) and (t >= apogee_time + parachute_delay):
                parachute_deployed = True

            # landing
            if h <= 0 and t > pre_launch_time:
                # mark landing properly
                alt[-1] = 0.0
                vel[-1] = 0.0
                acc[-1] = np.random.normal(0, 0.02)
                t += dt
                break

            # safety cutoff
            if t > 300:
                break

            t += dt

        # post landing idle
        for _ in range(int(np.ceil(post_landing_time / dt))):
            t_list.append(t)
            alt.append(0.0)
            vel.append(0.0)
            acc.append(np.random.normal(0, 0.02))
            t += dt

        return apogee, np.array(t_list), np.array(alt), np.array(vel), np.array(acc)

    # tune a_boost with a simple binary search to reach apogee_target
    lo = 5.0
    hi = 200.0
    target = apogee_target
    best = None
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        apogee, t_arr, alt_arr, vel_arr, acc_arr = simulate_with_boost(mid)
        if apogee is None:
            apogee = 0.0
        # adjust
        if apogee < target:
            lo = mid
        else:
            hi = mid
        best = (apogee, t_arr, alt_arr, vel_arr, acc_arr)

    # use best result
    assert best is not None
    apogee, t_arr, alt_arr, vel_arr, acc_arr = best

    # smooth acceleration
    acc_sm = pd.Series(acc_arr).rolling(window=5, center=True, min_periods=1).mean().values

    return pd.DataFrame({
        "time": t_arr,
        "altitude": alt_arr,
        "velocity": vel_arr,
        "acceleration": acc_sm,
    })


flights = [
    ("test_data/flight_1.csv", 260),
    ("test_data/flight_2.csv", 230),
    ("test_data/flight_3.csv", 100),
]


for i, (name, apogee) in enumerate(flights):
    df = generate_flight(i, apogee)
    df.to_csv(name, index=False)


print("Created 3 new test flights")
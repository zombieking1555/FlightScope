import pandas as pd
import io
from datetime import datetime


def clean_raw_csv(uploaded_file):
    lines = uploaded_file.getvalue().decode("utf-8").splitlines()

    cleaned = []
    for line in lines:
        # remove comment lines except header
        if line.startswith("#"):
            # Remove leading "#" from header line and keep it
            if line.startswith("# Time"):
                cleaned.append(line[2:].strip())  # Remove "# " prefix
            # Skip all other comment lines
            continue
        cleaned.append(line)

    df = pd.read_csv(io.StringIO("\n".join(cleaned)))

    # ONLY light cleanup here
    df.columns = df.columns.str.strip()

    return df


def normalize_columns(df):
    df = df.rename(columns={
        "Time (s)": "time",
        "Altitude (m)": "altitude",
        "Altitude (ft)": "altitude",
        "Vertical velocity (m/s)": "velocity",
        "Vertical velocity (ft/s)": "velocity",
        "Vertical acceleration (m/s²)": "acceleration",
        "Vertical acceleration (ft/s²)": "acceleration",
        "Vertical acceleration (G)": "acceleration",
        "Roll rate (r/s)": "roll_rate",
        "Pitch rate (r/s)": "pitch_rate",
        "Yaw rate (r/s)": "yaw_rate",
        "Vertical orientation (zenith) (°)": "zenith",
        "Lateral orientation (azimuth) (°)": "azimuth",
        "Vertical orientation (zenith) (arcmin)": "zenith",
        "Lateral orientation (azimuth) (arcmin)": "azimuth",
        "Vertical orientation (zenith) (rad)": "zenith",
        "Lateral orientation (azimuth) (rad)": "azimuth",
    })

    return df

def insert_flight(conn, df, filename):
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM flights WHERE filename = ?",
        (filename,)
    )
    existing = cursor.fetchone()

    if existing:
        return existing[0]

    cursor.execute(
        """
        INSERT INTO flights (filename, upload_date, max_altitude, max_velocity)
        VALUES (?, ?, ?, ?)
        """,
        (
            filename,
            datetime.now().isoformat(),
            float(df["altitude"].max()),
            float(df["velocity"].max()),
        ),
    )

    flight_id = cursor.lastrowid

    for _, row in df.iterrows():
        accel = float(row["acceleration"]) if "acceleration" in df.columns and pd.notna(row["acceleration"]) else None
        zenith = float(row["zenith"]) if "zenith" in df.columns and pd.notna(row["zenith"]) else None
        azimuth = float(row["azimuth"]) if "azimuth" in df.columns and pd.notna(row["azimuth"]) else None

        cursor.execute(
            """
            INSERT INTO telemetry (flight_id, time, altitude, velocity, acceleration, zenith, azimuth)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                flight_id,
                float(row["time"]),
                float(row["altitude"]),
                float(row["velocity"]),
                accel,
                zenith,
                azimuth
            ),
        )

    conn.commit()
    return flight_id

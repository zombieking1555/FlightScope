import pandas as pd
import io
from datetime import datetime

def clean_csv(uploaded_file):
    lines = uploaded_file.getvalue().decode("utf-8").splitlines()

    cleaned = []
    for line in lines:
        if line.startswith("#") and not line.startswith("# Time"):
            continue
        cleaned.append(line)

    df = pd.read_csv(io.StringIO("\n".join(cleaned)))

    df.columns = df.columns.str.replace("#", "").str.strip()

    df = df.rename(
        columns={
            "Time (s)": "time",
            "Altitude (m)": "altitude",
            "Vertical velocity (m/s)": "velocity",
            "Vertical acceleration (m/s²)": "acceleration",
        }
    )

    required = ["time", "altitude", "velocity"]

    if not all(c in df.columns for c in required):
        raise ValueError("CSV missing required columns")

    df[required] = df[required].apply(pd.to_numeric, errors="coerce")

    if df[required].isnull().any().any():
        raise ValueError("Non-numeric values in required columns")

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

        cursor.execute(
            """
            INSERT INTO telemetry (flight_id, time, altitude, velocity, acceleration)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                flight_id,
                float(row["time"]),
                float(row["altitude"]),
                float(row["velocity"]),
                accel,
            ),
        )

    conn.commit()
    return flight_id
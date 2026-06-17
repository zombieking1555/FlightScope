from pathlib import Path
import sqlite3

def ensure_db(path: Path = Path("flights.db")) -> None:
    created = not path.exists()
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        upload_date TEXT,
        max_altitude REAL,
        max_velocity REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        flight_id INTEGER,
        time REAL,
        altitude REAL,
        velocity REAL,
        acceleration REAL,
        zenith REAL,
        azimuth REAL
    )
    """)

    conn.commit()
    conn.close()

    if created:
        print(f"Created new database at {path}")
    else:
        print(f"Database already exists at {path}; schema verified")

if __name__ == "__main__":
    ensure_db()

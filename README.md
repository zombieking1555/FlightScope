# FlightScope

FlightScope is a Python application designed to analyze and visualize model rocket flight data. It provides tools for importing flight logs, processing telemetry, detecting key flight events, and displaying flight performance through an interactive dashboard.

## Features

* Import and manage rocket flight data
* Interactive flight data visualization
* Automatic trimming of pre-launch idle data
* Automatic flight event detection

  * Launch
  * Apogee
  * Landing
* Analysis of important flight metrics:

  * Maximum altitude
  * Maximum velocity
  * Maximum acceleration
  * Flight duration
* Local flight database management
* Streamlit-based user interface

## Installation

### Clone the repository

```bash
git clone https://github.com/yourusername/flightscope.git
cd flightscope
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Generate simulated flights

```bash
python test_data_writer.py
```

## Running FlightScope

Start the Streamlit application:

```bash
streamlit run dashboard.py
```

Then open the local URL shown in your terminal to access the dashboard.

## Project Structure

```
FlightScope/
│
├── Dashboard.py         # Main dashboard and flight visualization
├── Database_Manager.py  # Flight database management page
├── create_db.py         # Generates empty local database on app startup
├── flights.db           # Local database
├── test_data_writer.py  # Simulated flight generator
├── test_data            # Houses flight generations from `test_data_writer.py`
├── requirements.txt     # Python dependencies
└── README.md
```

## Data Format

FlightScope supports CSV flight logs containing telemetry such as:

* Time (s)
* Altitude (m)
* Velocity (m/s)
* Acceleration (m/s^2)

The application automatically converts and cleans supported flight log formats before analysis.

## Future Plans

* Support for additional flight computer formats
* More advanced flight statistics and comparisons
* Improved flight event detection algorithms
* Flight profile simulations
* Exporting and sharing flight reports

## License

This project is currently unlicensed and intended for personal and educational use.

---

Created by **Clifford St. Clair** as a personal aerospace engineering and software development project.

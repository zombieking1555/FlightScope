import streamlit as st
import pandas as pd

from db import get_connection
from data_import import clean_raw_csv, insert_flight, normalize_columns

conn = get_connection()
st.session_state.unit_confirm_table = pd.DataFrame(columns=["Data Type","Detected Unit"])

st.title("Upload Flight Data")

uploaded_file = st.file_uploader("Upload Flight CSV", type="csv")

# ----------------------------
# SIMPLE UNIT DETECTION
# ----------------------------
def detect_units(df: pd.DataFrame):

    conversions = {}

    for col in df.columns:

        col_lower = col.lower()

        # ALTITUDE
        if "altitude" in col_lower or "alt" in col_lower:
            if "(ft)" in col_lower or "feet" in col_lower:
                conversions[col] = ("ft", 0.3048)  # ft > m

        # VELOCITY
        if "velocity" in col_lower or "speed" in col_lower:
            if "(ft/s)" in col_lower:
                conversions[col] = ("ft/s", 0.3048) #ft/s > m/s

        # ACCELERATION
        if "acceleration" in col_lower:
            if "(ft/s²)" in col_lower:
                conversions[col] = ("ft/s²", 0.3048) # ft/s² > m/s²
            if "(g)" in col_lower:
                conversions[col] = ("g", 9.806)

    return conversions


def apply_unit_conversion(df, conversions):
    st.session_state.unit_confirm_table = pd.DataFrame(columns=["Data Type","Detected Unit"])

    for col, (unit, factor) in conversions.items():
        new_row = {"Data Type":col,"Detected Unit":unit}
        st.session_state.unit_confirm_table = pd.concat(
        [st.session_state.unit_confirm_table, pd.DataFrame([new_row])],
        ignore_index=True
        )
        df[col] = pd.to_numeric(df[col], errors="coerce") * factor

    st.dataframe(st.session_state.unit_confirm_table)
    return df


# ----------------------------
# MAIN FLOW
# ----------------------------
if uploaded_file is not None:

    st.info(f"Loaded file: {uploaded_file.name}")

    if st.button("Process & Upload Flight"):

        try:
            # 1. Clean CSV
            df = clean_raw_csv(uploaded_file)
            st.success("Flight file cleaned successfully")

            # 2. Detect units
            conversions = detect_units(df)

            if conversions:
                st.warning("Detected unit conversions:")

                df = apply_unit_conversion(df, conversions)

            else:
                st.success("No unit conversions needed")

            # 3. Normalize column names

            df = normalize_columns(df)

            # 4. Insert into DB
            flight_id = insert_flight(conn, df, uploaded_file.name)

            # 5. Store selection for dashboard
            st.session_state["selected_id"] = flight_id

            st.success(f"Flight uploaded successfully (ID: {flight_id})")

        except Exception as e:
            st.error(str(e))
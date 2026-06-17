import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import sqlite3
import pyvista as pv


from db import get_connection

# ----------------------------
# PV RENDER
# ----------------------------
def render_rocket():
    body = pv.Cylinder(center=(0, 0, 0), direction=(0, 0, 1), radius=0.1, height=1.0)
    nose = pv.Cone(center=(0, 0, .65), direction=(0, 0, 1), height=0.3, radius=0.1, resolution=20)
    # fins = []
    # for angle in [0, 90, 180, 270]:
    #     fin = pv.Box(bounds=(-0.05, 0.05, 0.1, 0.3, -0.01, 0.01))
    #     fin.rotate_z(angle)
    #     fins.append(fin)
    rocket = body + nose
    # for fin in fins:
    #     rocket += fin
    ground = pv.Plane(center=(0, 0, -0.01), direction=(0, 0, 1), i_size=1.5, j_size=1.5)
    plotter = pv.Plotter(off_screen=True)
    plotter.set_background("#242F48") # type: ignore
    plotter.add_mesh(ground, color="#3C8B5A")
    plotter.add_mesh(rocket, color="#943012")
    plotter.screenshot("assets/rocket.png")
    st.image("assets/rocket.png", caption="Rocket Visualization")

def render_frame(rotation_matrix):
    body = pv.Cylinder(center=(0, 0, 0), direction=(0, 0, 1), radius=0.1, height=1.0)
    nose = pv.Cone(center=(0, 0, .65), direction=(0, 0, 1), height=0.3, radius=0.1, resolution=20)
    fins = []
    for angle in [0, 90, 180, 270]:
        fin = pv.Box(bounds=(-0.05, 0.05, 0.1, 0.3, -0.01, 0.01))
        fin.rotate_z(angle)
        fins.append(fin)
    rocket = body + nose
    # for fin in fins:
    #     rocket += fin
    ground = pv.Plane(center=(0, 0, -0.01), direction=(0, 0, 1), i_size=1.5, j_size=1.5)
    plotter = pv.Plotter(off_screen=True)
    plotter.set_background("#242F48") # type: ignore
    plotter.add_mesh(ground, color="#3C8B5A")
    plotter.add_mesh(rocket, color="#943012")
    plotter.screenshot("assets/rocket.png")
    st.image("assets/rocket.png", caption="Rocket Visualization")
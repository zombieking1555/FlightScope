import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import sqlite3
import pyvista as pv

from scipy.spatial.transform import Rotation
from db import get_connection

HIGH_SKY = np.array([36, 47, 72])      # #242F48
GROUND_SKY = np.array([135, 206, 235]) # #87CEEB

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
    

def render_frame(zenith, azimuth, altitude):
    # Convert zenith and azimuth to x,y,z using elevation measured from horizontal
    x = np.cos(np.radians(zenith)) * np.cos(np.radians(azimuth))
    y = np.cos(np.radians(zenith)) * np.sin(np.radians(azimuth))
    z = np.sin(np.radians(zenith))
    direction = np.array([x, y, z])
    direction /= np.linalg.norm(direction)
    body_axis = np.array([0, 0, 1])
    rotation, _ = Rotation.align_vectors(
        [body_axis],
        [direction]
    )

    matrix = np.eye(4)
    matrix[:3, :3] = rotation.as_matrix()

    body = pv.Cylinder(center=(0, 0, 0), direction=(0, 0, 1), radius=0.1, height=1.0)
    nose = pv.Cone(center=(0, 0, 0.65), direction=(0, 0, 1), height=0.3, radius=0.1, resolution=100)
    rocket = body + nose
    rocket.transform(matrix, inplace=True)
    rocket.translate((0, 0, altitude), inplace=True)

    ground = pv.Plane(center=(0, 0, -0.01), direction=(0, 0, 1), i_size=10, j_size=10)
    plotter = pv.Plotter(off_screen=True)

    t = min(altitude/300, 1)
    sky_color = (1 - t) * GROUND_SKY + t * HIGH_SKY
    sky_color = sky_color.astype(int)
    background = "#{:02x}{:02x}{:02x}".format(*sky_color) 

    plotter.set_background(background) # type: ignore
    plotter.add_mesh(ground, color="#3C8B5A")
    plotter.add_mesh(rocket, color="#943012")

    rocket_center = np.array([0.0, 0.0, altitude])
    plotter.camera_position = [
        rocket_center + np.array([0.0, -.5, 2]),
        rocket_center + np.array([0.0, 0.0, -0.5]),
        (0, 0, 1),
    ]

    img = plotter.screenshot(return_img=True)
    plotter.close()
    return img
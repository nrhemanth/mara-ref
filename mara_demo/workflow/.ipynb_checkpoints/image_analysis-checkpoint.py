'''
Vattanary Tevy - created 03/02/2025
Handles reading images, applying filter, and contour detection
'''

from config import CAMERA_URI, ROWS, COLS, TOP_LEFT, BOTTOM_RIGHT, CAPTURE_IMAGE_PATH
# import numpy as np
import cv2
from PIL import Image as PILImage

def load_image(CAPTURE_IMAGE_PATH):
    return PILImage.open(CAPTURE_IMAGE_PATH).convert("RGB")

def compute_rgb_grid(CAPTURE_IMAGE_PATH, ROWS, COLS, TOP_LEFT, BOTTOM_RIGHT):
    """Extracts grid of RGB values from an image by sampling at linearly spaced positions between top_left and bottom_right"""
    image_rgb = cv2.imread(CAPTURE_IMAGE_PATH)  # BGR in OpenCV
    image_rgb = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB)
    
    x_step = (BOTTOM_RIGHT[0] - TOP_LEFT[0]) / (COLS - 1)
    y_step = (BOTTOM_RIGHT[1] - TOP_LEFT[1]) / (ROWS - 1)
    
    grid_positions = []
    rgb_values = []
    
    for row in range(ROWS):
        for col in range(COLS):
            x = int(TOP_LEFT[0] + col*x_step)
            y = int(TOP_LEFT[1] + row*y_step)
            grid_positions.append((x, y))
            b, g, r = image_rgb[y, x]
            rgb_values.append([r, g, b])
            
    return grid_positions, rgb_values

def analyze_image(CAPTURE_IMAGE_PATH, ROWS, COLS, TOP_LEFT, BOTTOM_RIGHT):
    """Convenience function: returns just the list of RGB values for the grid"""
    _, rgb_values = compute_rgb_grid(CAPTURE_IMAGE_PATH, ROWS, COLS, TOP_LEFT, BOTTOM_RIGHT)
    return rgb_values

def plot_grid(rgb_values, ROWS, COLS):
    """plot of color grid"""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 4))
    
    # If fewer values than needed, pad with black
    if len(rgb_values) < ROWS*COLS:
        rgb_values += [[0,0,0]]*(ROWS*COLS - len(rgb_values))
    
    for row in range(ROWS):
        for col in range(COLS):
            index = row*COLS + col
            r,g,b = rgb_values[index]
            color = (r/255, g/255, b/255)
            circle = plt.Circle((col+0.5, ROWS-row-0.5), 0.4, facecolor=color, 
                                edgecolor='black', linewidth=1)
            ax.add_patch(circle)
    
    ax.set_xlim(0, COLS)
    ax.set_ylim(0, ROWS)
    ax.set_aspect('equal')
    ax.axis('off')
    plt.show()


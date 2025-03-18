'''
Vattanary Tevy - created 03/02/2025
Graphical user interface for Mara's workflow
'''

import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import os
import numpy as np
# from opentrons_control import home_position
# from camera import capture_photo
# from main import main_workflow

font = ("Arial", 11)

# for target color display (changes based on user input)
# display picutre captured and BO graph

#function to clear the error display
def clear_error_display():
    error_display.delete(1.0, tk.END)

'''
window setup
'''
window = tk.Tk()
window.geometry('800x600')
window.title('Mara Demo')
window.resizable(False, False)

# home Mara
#command=home_position
home_button = tk.Button(window, text="Move to Home Position", font=font)
home_button.place(x=50, y=20)

# camera
#command=capture_photo
camera_button = tk.Button(window, text="Take a Picture", font=font)
camera_button.place(x=50, y=70)

# target
#command=main_workflow
target_button = tk.Button(window, text="Discover Target Color", font=font)
target_button.place(x=50, y=120)

# display of target color
target_display_frame = tk.Frame(window)
target_display_frame.place(x=400, y=50, width=50, height=50)

# display of captured picture
picture_display_frame = tk.Frame(window)
picture_display_frame.place(x=20, y=300, width=50, height=50)

# display of BO graph
BO_display_frame = tk.Frame(window)
BO_display_frame.place(x=300, y=300, width=50, height=50)

#clear messages
clear_button = tk.Button(window, text="Clear", command=clear_error_display)
clear_button.place(x=500, y=500)

#error display section
error_display_frame = tk.Frame(window)
error_display_frame.place(x=500, y=300, width=300, height=100)

error_display = ScrolledText(error_display_frame, wrap=tk.WORD, height=10, width=100)
error_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

#automatically initialize UI after running program
# initialize_ui()

window.mainloop()
'''
Vattanary Tevy - created 03/02/2025 (Modified for Interactive Workflow)
Orchestrates workflow with manual intervention points and color-grouped output
'''

from camera import capture_photo
from image_analysis import analyze_image, plot_grid, draw_contours, compute_rgb_grid
from lhs import generate_lhs_samples, store_and_print_cmyk
from bayesian import build_bo_model, suggest_next_sample, RGB_to_CMYK
import config
import asyncio
import torch
import numpy as np
import json
import time

from botorch.models import SingleTaskGP
from gpytorch.mlls import ExactMarginalLogLikelihood
from gpytorch.kernels import ScaleKernel, RBFKernel

# Use target color from config if available, otherwise use this default
TARGET_RGB = [224, 163, 46]
MAX_WELL_VOLUME = 270  # Total volume constraint in microliters

def wait_for_user_input(message="Press Enter to continue..."):
    """Pause execution until user presses Enter."""
    input(message)

def print_color_grouped_volumes(cmyk_list):
    """Print CMYK volumes grouped by color component."""
    cyan_values = [round(cmyk[0] * MAX_WELL_VOLUME, 2) for cmyk in cmyk_list]
    magenta_values = [round(cmyk[1] * MAX_WELL_VOLUME, 2) for cmyk in cmyk_list]
    yellow_values = [round(cmyk[2] * MAX_WELL_VOLUME, 2) for cmyk in cmyk_list]
    black_values = [round(cmyk[3] * MAX_WELL_VOLUME, 2) for cmyk in cmyk_list]
    
    print("Cyan:")
    print(", ".join([f"{val}" for val in cyan_values]))
    
    print("Magenta:")
    print(", ".join([f"{val}" for val in magenta_values]))
    
    print("Yellow:")
    print(", ".join([f"{val}" for val in yellow_values]))
    
    print("Black:")
    print(", ".join([f"{val}" for val in black_values]))
    
    # Print total volumes for verification
    for i, cmyk in enumerate(cmyk_list):
        total = sum([round(val * MAX_WELL_VOLUME, 2) for val in cmyk])
        print(f"Well {i} total: {total:.2f}µL")

def main_workflow_interactive():
    # 1) Set target color in RGB
    target_rgb_255 = TARGET_RGB          # e.g. [224, 163, 46]
    target_rgb = np.array(target_rgb_255) / 255 # convert to [0..1]
    target_cmyk = RGB_to_CMYK(target_rgb)       # in [0..1]
    print(f"Target RGB: {target_rgb_255} → CMYK: {[round(v, 3) for v in target_cmyk]}")

    # 2) Generate 5 initial LHS samples (CMYK in [0,1])
    n_init = 5
    lhs_5 = generate_lhs_samples(n_samples=n_init, n_vars=4, sum_constraint=1.0, seed=1)

    # 3) PAUSE: Display CMYK volumes for manual dispensing instead of automatic dispensing
    all_cmyk = lhs_5.tolist()
    print("\n==== Initial 5 CMYK Samples to Dispense Manually ====")
    print_color_grouped_volumes(all_cmyk)
    
    # Wait for user to manually dispense and signal completion
    wait_for_user_input("\nPlease manually dispense these samples, then press Enter to capture image...")

    # 4) Take picture
    print("Capturing image for the 5 initial samples...")
    asyncio.run(capture_photo())
    print("Image captured successfully!")

    # 5) Analyze image: extract the 1st 5 wells
    print("Analyzing image...")
    _, rgb_values = compute_rgb_grid(config.CAPTURE_IMAGE_PATH, config.ROWS, config.COLS,
                                    config.TOP_LEFT, config.BOTTOM_RIGHT)
    
    # We'll slice out just the first 5 wells (0..4)
    initial_rgb = rgb_values[:5]
    print("Initial 5 RGB values extracted:")
    for i, rgb in enumerate(initial_rgb):
        print(f"Well {i}: RGB = {rgb}")

    # 6) Convert these 5 samples of RGB to CMYK
    initial_cmyk_list = []
    for row in initial_rgb:
        row_rgb01 = np.array(row) / 255.0
        row_cmyk = RGB_to_CMYK(row_rgb01)
        initial_cmyk_list.append(row_cmyk)

    # Convert to a PyTorch tensor
    train_x = torch.tensor(initial_cmyk_list, dtype=torch.double)  # shape (5,4)

    # The objective is negative distance to target_cmyk
    t_cmyk = torch.tensor(target_cmyk, dtype=torch.double)
    distances_init = torch.norm(train_x - t_cmyk, dim=1)          # shape (5,)
    train_y = -distances_init.unsqueeze(-1)                       # shape (5,1)

    # Print initial distances
    print("\n==== Initial Distances to Target ====")
    for i, dist in enumerate(distances_init):
        print(f"Well {i} distance: {dist.item():.4f}")

    # Iterative BO, dispensing 1 sample at a time
    bounds = torch.stack([
        torch.zeros(4, dtype=torch.double),
        torch.ones(4, dtype=torch.double)
    ])

    # Keep track of how many total samples dispensed
    total_samples = n_init
    max_samples = 15      # end condition
    threshold = 0.05      # distance threshold

    while total_samples < max_samples:
        # 7) Fit a GP model on the current train_x, train_y
        print("\nFitting Bayesian Optimization model...")
        gp = build_bo_model(train_x, train_y)

        # Check if we already have a "best distance" that meets threshold
        best_idx = torch.argmax(train_y)
        best_dist = -train_y[best_idx].item()
        print(f"Current best distance = {best_dist:.4f}, iteration = {total_samples}")

        if best_dist < threshold:
            print(f"Stopping early because best distance {best_dist:.4f} < {threshold}")
            break

        # 8) Suggest the next sample (only one at a time)
        new_x = suggest_next_sample(gp, train_x, bounds, beta=0.1)  # shape (1,4)
        cmyk_array = new_x.squeeze(0).numpy().tolist()  # shape (4,) -> list
        
        # 9) PAUSE: Display the next CMYK to manually dispense
        new_sample_well = total_samples
        print(f"\n==== Next CMYK Sample (Well {new_sample_well}) ====")
        
        # Format as color-grouped output even though it's just one sample
        print("Cyan:")
        print(f"{round(cmyk_array[0] * MAX_WELL_VOLUME, 2)}")
        
        print("Magenta:")
        print(f"{round(cmyk_array[1] * MAX_WELL_VOLUME, 2)}")
        
        print("Yellow:")
        print(f"{round(cmyk_array[2] * MAX_WELL_VOLUME, 2)}")
        
        print("Black:")
        print(f"{round(cmyk_array[3] * MAX_WELL_VOLUME, 2)}")
        
        total = sum([round(val * MAX_WELL_VOLUME, 2) for val in cmyk_array])
        print(f"Total volume: {total:.2f}µL")
        
        # Wait for user to manually dispense and signal completion
        wait_for_user_input("\nPlease manually dispense this sample, then press Enter to capture image...")

        # 10) Take a picture again
        print("Capturing new image...")
        asyncio.run(capture_photo())
        print("Image captured successfully!")

        # 11) Analyze image: we only need the new well
        print("Analyzing updated image...")
        _, new_rgb_values = compute_rgb_grid(config.CAPTURE_IMAGE_PATH, config.ROWS, config.COLS,
                                            config.TOP_LEFT, config.BOTTOM_RIGHT)
        # Extract the single well
        new_rgb = new_rgb_values[new_sample_well]
        print(f"Well {new_sample_well} RGB = {new_rgb}")
        
        # 12) Convert this new RGB -> CMYK
        row_rgb01 = np.array(new_rgb) / 255.0
        new_cmyk = RGB_to_CMYK(row_rgb01)
        print(f"Measured CMYK = {[round(v, 3) for v in new_cmyk]}")

        # 13) Compute objective, append to train_x, train_y
        new_cmyk_torch = torch.tensor(new_cmyk, dtype=torch.double).unsqueeze(0)  # shape [1,4]
        train_x = torch.cat([train_x, new_cmyk_torch], dim=0)

        new_dist = torch.norm(new_cmyk_torch - t_cmyk, dim=1)   # shape [1,]
        new_y = -(new_dist.unsqueeze(-1))                      # shape [1,1]
        train_y = torch.cat([train_y, new_y], dim=0)
        
        print(f"New distance to target: {new_dist.item():.4f}")

        total_samples += 1

        # 14) Check if new distance meets threshold
        if new_dist.item() < threshold:
            print(f"Distance {new_dist.item():.4f} < {threshold}, stopping.")
            break

    print("\n==== Final Results ====")
    best_idx = torch.argmax(train_y)
    best_dist = -train_y[best_idx].item()
    best_cmyk = train_x[best_idx].numpy()
    print(f"Total samples used: {total_samples}")
    print(f"Best distance: {best_dist:.4f}")
    print(f"Best CMYK: {[round(v, 3) for v in best_cmyk]}")
    best_well = best_idx.item()
    print(f"Best match is in Well {best_well}")
    
    # Show best values in practical volumes
    best_volumes = [round(val * MAX_WELL_VOLUME, 2) for val in best_cmyk]
    print(f"Best CMYK volumes: C={best_volumes[0]}µL, M={best_volumes[1]}µL, Y={best_volumes[2]}µL, K={best_volumes[3]}µL")
    print(f"Total volume: {sum(best_volumes):.2f}µL")


if __name__ == "__main__":
    main_workflow_interactive()
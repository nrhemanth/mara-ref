'''
Vattanary Tevy - created 03/02/2025
Orchestrates entire workflow
'''

from camera import capture_photo
from image_analysis import analyze_image, plot_grid, draw_contours, compute_rgb_grid
from lhs import generate_lhs_samples, store_and_print_cmyk
from opentrons_control import run_opentrons_mix
from bayesian import build_bo_model, suggest_next_sample, RGB_to_CMYK
import config
import asyncio
import torch
import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt

from botorch.models import SingleTaskGP
from botorch.acquisition import LogExpectedImprovement, UpperConfidenceBound, qLogExpectedImprovement
# from botorch.optim import optimize_acqf
# from botorch.fit import fit_gpytorch_mll   # marginal log likelihood
from gpytorch.mlls import ExactMarginalLogLikelihood
# from scipy.stats.qmc import LatinHypercube
from gpytorch.kernels import ScaleKernel, RBFKernel

def main_workflow():
    # 1) Set target color in RGB
    target_rgb_255 = config.TARGET_RGB          # e.g. [96, 86, 87]
    target_rgb = np.array(target_rgb_255) / 255 # convert to [0..1]
    target_cmyk = RGB_to_CMYK(target_rgb)       # in [0..1]

    # 2) Generate 5 initial LHS samples (CMYK in [0,1])
    n_init = 5
    lhs_5 = generate_lhs_samples(n_samples=n_init, n_vars=4, sum_constraint=None, seed=42)
    # shape: (5,4), each row is [C,M,Y,K] in [0..1] (assuming sum_constraint=None for standard LHS)

    # 3) Dispense those 5 samples
    print("Dispensing initial 5 samples via Opentrons...")
    run_opentrons_mix(lhs_5)  # You might need to handle volumes, etc.

    # 4) Take picture
    print("Capturing image for the 5 initial samples...")
    asyncio.run(capture_photo())

    # 5) Analyze image: extract the 1st 5 wells (i.e. the first 5 positions in your 8×12 grid)
    _, rgb_values = compute_rgb_grid(config.CAPTURE_IMAGE_PATH, config.ROWS, config.COLS,
                                     config.TOP_LEFT, config.BOTTOM_RIGHT)
    # rgb_values is length 96 if 8×12. The first 5 correspond to row=0 col=0..4 if you index in row-major order.

    # We'll slice out just the first 5 wells (0..4)
    initial_rgb = rgb_values[:5]  # shape: (5, 3) each in [0..255]

    # 6) Convert these 5 samples of RGB to CMYK
    # -> need them in [0..1], so divide by 255 first, then call RGB_to_CMYK
    initial_cmyk_list = []
    for i in range(n_init):
        row_rgb01 = np.array(initial_rgb[i]) / 255.0
        row_cmyk  = RGB_to_CMYK(row_rgb01)
        initial_cmyk_list.append(row_cmyk)

    # Convert to a PyTorch tensor
    train_x = torch.tensor(initial_cmyk_list, dtype=torch.double)  # shape (5,4)

    # The objective is negative distance to target_cmyk
    t_cmyk = torch.tensor(target_cmyk, dtype=torch.double)
    distances_init = torch.norm(train_x - t_cmyk, dim=1)          # shape (5,)
    train_y = -distances_init.unsqueeze(-1)                       # shape (5,1)

    # iterative BO, dispensing 1 sample at a time
    bounds = torch.stack([
        torch.zeros(4, dtype=torch.double),
        torch.ones(4, dtype=torch.double)
    ])

    # keep track of how many total samples dispensed
    total_samples = n_init
    max_samples   = 15    # end condition
    threshold     = 0.05  # distance threshold

    while total_samples < max_samples:
        # 7) Fit a GP model on the current train_x, train_y
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
        print(f"Proposed next CMYK = {new_x.detach().numpy()}")

        # 9) Dispense the next sample (the 6th, 7th, etc.)
        run_opentrons_mix(new_x.squeeze(0).numpy())  # convert from torch -> np -> pass to your method

        # 10) Take a picture again
        asyncio.run(capture_photo())

        # 11) Analyze image: we only need the new well, i.e. well # total_samples
        # if the first 5 used wells indices [0..4], then the 6th is index=5, 7th is index=6, ...
        well_index = total_samples  # zero-based
        _, new_rgb_values = compute_rgb_grid(config.CAPTURE_IMAGE_PATH, config.ROWS, config.COLS,
                                             config.TOP_LEFT, config.BOTTOM_RIGHT)
        # Extract the single well
        new_rgb = new_rgb_values[well_index]
        
        # 12) Convert this new RGB -> CMYK
        row_rgb01 = np.array(new_rgb) / 255.0
        new_cmyk  = RGB_to_CMYK(row_rgb01)

        # 13) Compute objective, append to train_x, train_y
        new_cmyk_torch = torch.tensor(new_cmyk, dtype=torch.double).unsqueeze(0)  # shape [1,4]
        train_x = torch.cat([train_x, new_cmyk_torch], dim=0)

        new_dist = torch.norm(new_cmyk_torch - t_cmyk, dim=1)   # shape [1,]
        new_y    = -(new_dist.unsqueeze(-1))                    # shape [1,1]
        train_y  = torch.cat([train_y, new_y], dim=0)

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
    print(f"Best CMYK: {best_cmyk}")


if __name__ == "__main__":
    main_workflow()
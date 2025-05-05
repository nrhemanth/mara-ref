'''
Vattanary Tevy - created 03/02/2025
GP-based Bayesian Optimization over 4D CMYK space, trying to match a target RGB color
Returns the best CMYK found
'''

import torch
import numpy as np
import matplotlib.pyplot as plt
import config

from botorch.models import SingleTaskGP
from botorch.acquisition import LogExpectedImprovement, UpperConfidenceBound, qLogExpectedImprovement
from botorch.optim import optimize_acqf
from botorch.fit import fit_gpytorch_mll   # marginal log likelihood
from gpytorch.mlls import ExactMarginalLogLikelihood
from scipy.stats.qmc import LatinHypercube
from gpytorch.kernels import ScaleKernel, RBFKernel

def build_bo_model(train_x, train_y):
    """
    Given train_x (N x 4) and train_y (N x 1) for CMYK distances,
    returns a fitted SingleTaskGP model.
    """
    gp = SingleTaskGP(train_x, train_y, covar_module=ScaleKernel(RBFKernel()))
    mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
    fit_gpytorch_mll(mll)
    return gp

def suggest_next_sample(gp, train_x, bounds, beta=0.1):
    """
    Given the fitted GP model and existing train_x, uses UCB
    to find the next best single sample in [0,1]^4.
    """
    # UCB acquisition
    UCB = UpperConfidenceBound(gp, beta=beta)

    # Optimize acquisition function
    candidates, _ = optimize_acqf(
        acq_function=UCB,
        bounds=bounds,  # shape [2 x 4]
        q=1,
        num_restarts=20,
        raw_samples=256,
    )

    # Return that single next candidate
    return candidates.detach()  # shape [1 x 4]

def RGB_to_CMYK(rgb):
    R, G, B = rgb
    K = min(1 - R, 1 - G, 1 - B)
    C = (1 - R - K) / (1 - K) if (1 - K) > 0 else 0
    M = (1 - G - K) / (1 - K) if (1 - K) > 0 else 0
    Y = (1 - B - K) / (1 - K) if (1 - K) > 0 else 0
    return np.array([C, M, Y, K])

def generate_lhs_samples(n_samples=1, n_features=4):
    sampler = LatinHypercube(d=n_features)
    samples = sampler.random(n_samples)  # Generates values in [0, 1]
    return torch.tensor(samples, dtype=torch.double)

def plot_convergence(train_y):
    """
    Plots the Euclidean distance to the target color over iterations.
    """
    iterations = np.arange(1, len(train_y) + 1)
    distances = -train_y.numpy().flatten()  # Convert to positive distances

    plt.figure(figsize=(8, 5))
    plt.plot(iterations, distances, marker="o", linestyle="-", color="b", label="Distance to Target CMYK")
    plt.xlabel("Iteration")
    plt.ylabel("Distance to Target")
    plt.title("Convergence of Bayesian Optimization")
    plt.grid(True)
    plt.legend()
    plt.show()

def CMYK_to_RGB(cmyk):
    """Convert CMYK to RGB using the standard formula."""
    C, M, Y, K = cmyk
    R = (1 - C) * (1 - K)
    G = (1 - M) * (1 - K)
    B = (1 - Y) * (1 - K)
    return np.array([R, G, B])

def visualize_iterations(train_x, target_rgb):
    """
    Visualizes the colors chosen at each iteration.
    Displays them in a sequential order.
    """
    num_samples = train_x.shape[0]
    
    # Convert CMYK to RGB for visualization
    rgb_colors = np.array([CMYK_to_RGB(cmyk) for cmyk in train_x.numpy()])
    
    # Plot the colors selected over iterations
    plt.figure(figsize=(12, 2))
    for i in range(num_samples):
        plt.subplot(1, num_samples, i + 1)
        plt.imshow([[rgb_colors[i]]], extent=[0, 1, 0, 1])
        plt.axis("off")
        plt.title(f"Iter {i+1}", fontsize=8)
    
    plt.suptitle("Bayesian Optimization - CMYK Convergence", fontsize=12)
    plt.tight_layout()
    
    # Show the target color for reference
    plt.figure(figsize=(2, 2))
    plt.imshow([[target_rgb]], extent=[0, 1, 0, 1])
    plt.axis("off")
    plt.title("Target Color", fontsize=12)
    plt.show()

def bayesian_optimization_with_boTorch(target_cmyk, n_init_samples=config.INITIAL_SAMPLE, n_iter=config.BO_MAX_ITERS, beta=0.1):
    """
    Performs Bayesian optimization using BoTorch to find a CMYK vector 
    that maximizes the negative Euclidean distance (i.e., 
    tries to get as close as possible to target_cmyk).

    Args:
        target_cmyk (list or tensor): 4D CMYK target in [0,1].
        n_init_samples (int): Number of initial LHS samples.
        n_iter (int): Number of Bayesian optimization iterations.
        beta (float): Parameter for the UCB (Upper Confidence Bound).

    Returns:
        best_distance (float): The best (lowest) distance found to the target.
        best_cmyk (numpy array): The 4D CMYK vector that achieved best_distance.
        train_x (tensor): All sampled CMYK points from the optimization process.
        train_y (tensor): The corresponding objective values (negative distance).
    """

    # 1. Generate initial LHS samples in [0,1], shape: (n_init_samples, 4)
    train_x = generate_lhs_samples(n_samples=n_init_samples, n_vars=config.LHS_N_VARS, sum_constraint=config.MAX_WELL_VOLUME, seed=config.BO_SEED)
    train_x = torch.tensor(train_x, dtype=torch.double)

    # 2. Build initial train_y (objective = negative Euclidean distance)
    target_torch = torch.tensor(target_cmyk, dtype=torch.double)
    train_y = -torch.norm(train_x - target_torch, dim=1).unsqueeze(-1)
    # shape: (n_init_samples, 1)

    # 3. Define search bounds in 4D space: [0,1] for each dimension
    bounds = torch.stack([torch.zeros(4, dtype=torch.double), torch.ones(4, dtype=torch.double)])

    # 4. Bayesian optimization loop
    for iteration in range(n_iter):
        # a) Fit GP model
        gp = SingleTaskGP(train_x, train_y, covar_module=ScaleKernel(RBFKernel()))
        mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
        fit_gpytorch_mll(mll)

        # b) Define acquisition function (UCB here)
        EI = UpperConfidenceBound(gp, beta=beta)

        # c) Optimize acquisition function over [0,1]^4
        candidates, _ = optimize_acqf(
            acq_function=EI,
            bounds=bounds,
            q=1,  # single candidate
            num_restarts=20,
            raw_samples=256,
        )

        # d) Evaluate objective (distance) at new candidate
        new_x = candidates.detach()
        new_y = -torch.norm(new_x - target_torch, dim=1).unsqueeze(-1)

        # e) Append to training data
        train_x = torch.cat([train_x, new_x])
        train_y = torch.cat([train_y, new_y])

    # 5. Identify the best solution found
    best_idx = torch.argmax(train_y, dim=0).item()
    best_distance = -train_y[best_idx].item()  # negative distance => actual distance
    best_cmyk = train_x[best_idx].numpy()      # shape: (4,)

    print(f"Best distance: {best_distance} at iteration {best_idx + 1}")
    print("Optimal CMYK:", best_cmyk)

    # Optional: print iteration record
    # for i in range(len(train_y)):
    #     print(f"Iteration {i+1}: Distance = {-train_y[i].item()}, CMYK = {train_x[i].numpy()}")

    return best_distance, best_cmyk, train_x, train_y
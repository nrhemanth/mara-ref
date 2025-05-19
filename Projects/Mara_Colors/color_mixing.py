#%% 
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.signal import find_peaks
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter1d
import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll
from botorch.acquisition.monte_carlo import qExpectedImprovement
from botorch.optim import optimize_acqf
from gpytorch.mlls import ExactMarginalLogLikelihood
import gpytorch
from botorch.utils.transforms import normalize, unnormalize
from botorch.acquisition import qLogExpectedImprovement
from scipy.signal import deconvolve
import ipywidgets as widgets
from ipywidgets import interact
from matplotlib import cm
from matplotlib.colors import Normalize
import os
import re
import csv
#%% 

# %%
# %%
class GaussianProcess:
    def __init__(self, train_X=None, train_y=None, train_yvar=None, bounds=None):
        self.train_X = train_X
        self.train_y = train_y
        self.train_yvar = train_yvar
        self.bounds = bounds

    def fit(self):
        # Set the device and dtype
        dtype = torch.float64

        X = torch.tensor(self.train_X, dtype=dtype)
        X = normalize(X, bounds=self.bounds)
        y = torch.tensor(self.train_y, dtype=dtype).reshape(-1,1)

        # Define a GP model
        self.gp = SingleTaskGP(train_X=X, train_Y=y)
        # Marginal Log Likelihood (MLL) for training
        mll = ExactMarginalLogLikelihood(self.gp.likelihood, self.gp)
        # Optimize model
        fit_gpytorch_mll(mll)

        return self.gp
    
    def get_model(self):
        return self.gp

    def predict(self, X_test):
        dtype = torch.float64
        if isinstance(X_test, np.ndarray):
            X_test = torch.tensor(X_test, dtype=dtype)

        self.gp.eval()
        self.likelihood.eval()

        with torch.no_grad():
            posterior = self.gp.posterior(X_test)
            mean = posterior.mean.squeeze(-1)  # Mean prediction
            std_dev = posterior.variance.sqrt().squeeze(-1)  # Standard deviation

        return mean.numpy(), std_dev.numpy()

    def evaluate(self, X_test):
        dtype = torch.float64
        if isinstance(X_test, np.ndarray):
            X_test = torch.tensor(X_test, dtype=dtype)

        self.gp.eval()
        with torch.no_grad():
            posterior = self.gp.posterior(X_test)
            mean = posterior.mean.squeeze(-1)
            std_dev = posterior.variance.sqrt().squeeze(-1)
        return mean.numpy(), std_dev.numpy()

    def get_train_y(self):
        return self.train_y

#%% 
class BayesianOptimization: 
    def __init__(self, gp_model: GaussianProcess, bounds=None, batch_size=None, seed = None):
        self.gp_model = gp_model
        self.batch_size = batch_size
        self.bounds = bounds if bounds is not None else torch.tensor([[0.0, 0.0], [1.0, 1.0]])
        self.batch_size = batch_size if batch_size is not None else 1
        self.seed = seed

    def suggest_next_point(self, acquisition='EI'):
        dtype = torch.float64
        device = torch.device('cpu')
        model = self.gp_model.get_model()
        best_f = self.gp_model.get_train_y().min()
        batch_size = self.batch_size
        bounds = self.bounds.to(device, dtype=dtype)

        if acquisition == 'EI':
            qEI = qLogExpectedImprovement(model=model, best_f=best_f)
        else:
            raise NotImplementedError(f"Acquisition function '{acquisition}' is not implemented.")

        bo_bounds = torch.tensor([[0.0, 0.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0]], dtype=dtype)

        torch.manual_seed(self.seed)

        candidate, _ = optimize_acqf(
            acq_function=qEI,
            bounds=bo_bounds,
            q=batch_size,
            num_restarts=15,
            raw_samples=100,
            options={"dtype": dtype, "device": device}
        )

        unnormalized_candidates = unnormalize(candidate, bounds).detach().cpu().numpy()
        self.df_candidates = pd.DataFrame(unnormalized_candidates, columns=["volC", "volM", "volY", "volK"])

        return  self.df_candidates
    
    def constrain_volumes(self, df_candidates):
        max_volume = 100
        df_candidates = df_candidates.copy()
        stoichiometry = df_candidates[["volC", "volM", "volY", "volK"]].div(df_volumes, axis=0)
        df_candidates[["volC", "volM", "volY", "volK"]] = stoichiometry.mul(max_volume, axis=0)
        df_volumes = df_candidates[["volC", "volM", "volY", "volK"]].sum(axis=1)
        return df_volumes
    
    def save_results(self, full_df,output_path):
        """
        Save the candidates and their corresponding volumes to a CSV file.
        Parameters:
            output_path (str): Path to save the CSV file.
        """
        df = full_df.copy()
        df.insert(0, 'ID', range(1, len(df) + 1))
        df.to_csv(output_path, mode = 'a',index=False)
        print(f"Results saved to {output_path}")

    
# %%
class PlotGP: 
    def __init__(self, gp_model: GaussianProcess, bounds=None):
        self.gp_model = gp_model
        self.bounds = bounds if bounds is not None else torch.tensor([[0.0, 0.0], [1.0, 1.0]])
        self.gp = gp_model.get_model()
        self.train_X = gp_model.train_X
        self.train_y = gp_model.train_y

    def plot_gp(self, x=None, y=None, num_points=100):
        if x is None:
            x = np.linspace(self.bounds[0, 0], self.bounds[1, 0], num_points)
        if y is None:
            y = np.linspace(self.bounds[0, 1], self.bounds[1, 1], num_points)

        X_test = np.array(np.meshgrid(x, y)).T.reshape(-1, 2)
        mean, std_dev = self.gp_model.predict(X_test)

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(X_test[:, 0], mean, 'r-', label='GP Mean')
        ax.fill_between(X_test[:, 0], mean - 2 * std_dev, mean + 2 * std_dev, alpha=0.5, label='Confidence Interval')
        ax.scatter(self.train_X[:, 0], self.train_y, c='blue', marker='x', label='Training Data')
        ax.set_xlabel('X-axis')
        ax.set_ylabel('Y-axis')
        ax.legend()
        plt.show()

    def interactive_3d_staircase_contours(x_grid, y_grid, z_slices, slice_values,labels,title="3D Staircase Contour", cmap='viridis'):
        """
        Plots stacked 2D contour plots to simulate a 3D staircase of contours with interactive rotation.

        Parameters:
            x_grid (2D array): meshgrid of x values
            y_grid (2D array): meshgrid of y values
            z_slices (list of 2D arrays): function values at each slice (z-level)
            slice_values (list): the z-axis or staircase values (e.g. time, pressure, etc.)
            title (str): Title of the plot
            cmap (str): Colormap for the contours
        """
        def plot_with_rotation(azim, elev):
            fig = plt.figure(figsize=(10, 8))
            ax = fig.add_subplot(projection='3d')

            # Get global min and max across all slices
            global_min = min(np.min(z) for z in z_slices)
            global_max = max(np.max(z) for z in z_slices)
            levels = np.linspace(global_min, global_max, 15)
            norm = Normalize(vmin=global_min, vmax=global_max)

            for i, z_val in enumerate(slice_values):
                z_data = z_slices[i]
                ax.contourf(
                    x_grid, y_grid, z_data, 
                    zdir='z', offset=z_val, 
                    levels=levels, cmap=cmap, alpha=0.8, norm=norm
                )

            # Add a fake ScalarMappable for colorbar
            mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
            mappable.set_array([])  # needed for colorbar
            fig.colorbar(mappable, ax=ax, shrink=0.5, aspect=10, label='Intensity')

            ax.set_xlabel(labels[0])
            ax.set_ylabel(labels[1])
            ax.set_zlabel(labels[2])
            ax.set_zlim(min(slice_values), max(slice_values))
            ax.set_title(title)
            ax.view_init(elev=elev, azim=azim)
            plt.tight_layout()
            plt.show()

        interact(
            plot_with_rotation,
            azim=widgets.FloatSlider(value=45, min=0, max=360, step=1, description='Azimuth'),
            elev=widgets.FloatSlider(value=30, min=-90, max=90, step=1, description='Elevation')
        )


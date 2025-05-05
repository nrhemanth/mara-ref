'''
Vattanary Tevy - created 03/02/2025
Bayesian Optimization for Mara's workflow (includes Gaussian process,
acquisition function, and proposes new points)

Running this program ...

Notes: 
'''

# bayes_opt.py
import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel
from scipy.optimize import minimize
from scipy.stats import norm

def run_bayesian_optimization(target_rgb, n_iters=20):
    """
    A simplified placeholder that runs GP-based Bayesian Optimization 
    over 4D CMYK space, trying to match a target RGB color.
    Returns the best CMYK found.
    """
    # 1) Convert target_rgb to normalized CMYK (for example)
    target_rgb_norm = np.array(target_rgb)/255.0
    # some function that converts RGB->CMYK
    target_cmyk = rgb_to_cmyk(target_rgb_norm)

    # 2) Setup initial data
    X = np.random.rand(2, 4)  # just a quick hack: 2 initial random points in 4D
    # Score: negative distance to target
    y = - np.linalg.norm(X - target_cmyk, axis=1)

    # 3) Build GP
    kernel = ConstantKernel(1.0) * RBF(1.0)
    gp = GaussianProcessRegressor(kernel=kernel, alpha=1e-4, n_restarts_optimizer=5)

    def expected_improvement(X_test, X_sample, y_sample, model, xi=0.01):
        mu, sigma = model.predict(X_test, return_std=True)
        min_val = np.min(y_sample)
        imp = min_val - mu - xi
        Z = imp / sigma
        ei = imp * norm.cdf(Z) + sigma * norm.pdf(Z)
        ei[sigma==0] = 0.0
        return ei

    def propose_location(acquisition, X_sample, y_sample):
        dim = X_sample.shape[1]
        def min_obj(x):
            return -acquisition(x.reshape(-1,dim), X_sample, y_sample, gp)

        # multiple random restarts
        best_x = None
        best_val = 1e8
        for _ in range(20):
            x0 = np.random.rand(dim)
            res = minimize(min_obj, x0, bounds=[(0,1)]*dim, method='L-BFGS-B')
            if res.fun < best_val:
                best_val = res.fun
                best_x = res.x
        return best_x

    # 4) Main loop
    for i in range(n_iters):
        gp.fit(X, y)
        X_next = propose_location(expected_improvement, X, y)
        y_next = - np.linalg.norm(X_next - target_cmyk)
        X = np.vstack([X, X_next])
        y = np.append(y, y_next)

    # best found
    best_idx = np.argmax(y)
    best_cmyk = X[best_idx]
    return best_cmyk

def rgb_to_cmyk(rgb_arr):
    """Example: for a normalized rgb array [r,g,b] in [0,1], 
    return cmyk in [0,1]."""
    r, g, b = rgb_arr
    k = 1 - max(r, g, b)
    if k == 1.0:  # black
        return np.array([0,0,0,1])
    c = (1-r-k)/(1-k)
    m = (1-g-k)/(1-k)
    y = (1-b-k)/(1-k)
    return np.array([c,m,y,k])

import torch
from botorch.models import SingleTaskGP
from gpytorch.mlls import ExactMarginalLogLikelihood
from botorch.fit import fit_gpytorch_model

# Generate synthetic data
torch.manual_seed(123)
train_X = torch.rand(10, 1)  # 10 random input points
train_y = torch.sin(train_X * (2 * 3.1416)) + torch.randn(10, 1) * 0.1  # noisy sine wave

# Define the Gaussian Process model
gp = SingleTaskGP(train_X, train_y)

# Set up the marginal log likelihood
mll = ExactMarginalLogLikelihood(gp.likelihood, gp)

# Use the fit_gpytorch_model function to fit the model
fit_gpytorch_model(mll)

# Make predictions
test_X = torch.linspace(0, 1, 100).unsqueeze(1)  # 100 test points
with torch.no_grad():
    posterior = gp.posterior(test_X)
    mean = posterior.mean
    lower, upper = posterior.mvn.confidence_region()

# Plot the results
import matplotlib.pyplot as plt

plt.figure(figsize=(8, 6))
plt.plot(train_X.numpy(), train_y.numpy(), "k.", label="Observations")
plt.plot(test_X.numpy(), mean.numpy(), "b", label="Mean")
plt.fill_between(
    test_X.numpy().flatten(),
    lower.numpy().flatten(),
    upper.numpy().flatten(),
    alpha=0.3,
    color="blue",
    label="Confidence",
)
plt.xlabel("X")
plt.ylabel("y")
plt.title("Gaussian Process Regression")
plt.legend()
plt.show()

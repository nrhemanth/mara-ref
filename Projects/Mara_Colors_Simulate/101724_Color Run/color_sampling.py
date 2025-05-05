# %%
from pyDOE import lhs
from smt.sampling_methods import LHS
import random
import numpy as np
import pandas as pd

# %%
def latin_hypercube_sum_constraint(n_samples, n_variables, sum_constraint,seed):
    # Step 1: Generate Latin Hypercube Samples
    seed
    lhs_samples = lhs(n_variables, samples=n_samples, criterion='maximin')
    #sampling = LHS(xlimits=xlimits,random_state = np.random.RandomState(0))

    # Step 2: Transform samples to satisfy the sum constraint
    for i in range(n_samples):
        current_sum = np.sum(lhs_samples[i, :])
        lhs_samples[i, :] *= sum_constraint / current_sum

    return lhs_samples
# %%
df_lhs = pd.DataFrame(latin_hypercube_sum_constraint(n_samples=8, n_variables=3, sum_constraint=270.0,seed=np.random.seed(2)),columns=['C','M','Y'])
df_lhs
# %%
df_lhs.to_numpy().T
# %%

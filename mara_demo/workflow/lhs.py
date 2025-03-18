'''
Vattanary Tevy - created 03/02/2025
Latin hypercube sampling for Mara's workflow
'''

import numpy as np
from pyDOE import lhs
import json

def generate_lhs_samples(n_samples, n_vars, sum_constraint, seed):
    """Generate LHS samples that sum to a given constraint 
       (i.e. total of the n_vars must be sum_constraint)"""
    if seed is not None:
        np.random.seed(seed)
    samples = lhs(n_vars, samples=n_samples, criterion='maximin')
    # Scale each row so it sums to sum_constraint
    for i in range(n_samples):
        row_sum = np.sum(samples[i,:])
        samples[i,:] *= sum_constraint / row_sum
    return samples

def store_and_print_cmyk(arrays, seeds, output_json="CMYK_values.json"):
    """
    For each array in 'arrays', prints out the CMYK values and stores them
    in a list of dicts, then writes them to a JSON file

    arrays : list of 2D arrays, each shaped [4 x n_samples]
    output_json : path to output JSON
    """

    CMYK_values = []

    for i, array in enumerate(arrays):
        seed_value = seeds[i]

        # array[0] = C row, array[1] = M row, array[2] = Y row, array[3] = K row
        c_values_str = ", ".join(map(str, array[0]))
        m_values_str = ", ".join(map(str, array[1]))
        y_values_str = ", ".join(map(str, array[2]))
        k_values_str = ", ".join(map(str, array[3]))

        print(f"Results for seed {seed_value}:")
        print("C (blue) values:")
        print(c_values_str)
        print("\nM (red) values:")
        print(m_values_str)
        print("\nY (yellow) values:")
        print(y_values_str)
        print("\nK (black) values:")
        print(k_values_str)
        print("-"*50)

        # append to list for JSON export
        CMYK_values.append({
            "Results for seed": seed_value,
            "C (blue) values": c_values_str,
            "M (red) values": m_values_str,
            "Y (yellow) values": y_values_str,
            "K (black) values": k_values_str
        })

    with open(output_json, "w") as f:
        json.dump(CMYK_values, f, indent=2)

    return CMYK_values
'''
Vattanary Tevy - Modified for Interactive Workflow
Simplified version without Bayesian Optimization
'''
from camera import capture_photo
from image_analysis import compute_rgb_grid
from lhs import generate_lhs_samples
import config
import asyncio
import numpy as np
import time
# Use target color from config if available, otherwise use this default
TARGET_RGB = [224, 163, 46]
MAX_WELL_VOLUME = 270  # Total volume constraint in microliters
def wait_for_user_input(message="Press Enter to continue..."):
    """Pause execution until user presses Enter."""
    input(message)
def RGB_to_CMYK(rgb):
    """Convert RGB in [0,1] to CMYK in [0,1]"""
    r, g, b = rgb
    # Black (K) calculation
    k = 1 - max(r, g, b)
    # Handle pure black case
    if k == 1:
        return [0, 0, 0, 1]
    # CMY calculation
    c = (1 - r - k) / (1 - k)
    m = (1 - g - k) / (1 - k)
    y = (1 - b - k) / (1 - k)
    return [c, m, y, k]
def calculate_color_distance(color1, color2):
    """Calculate Euclidean distance between two color arrays."""
    return np.sqrt(np.sum((np.array(color1) - np.array(color2))**2))
def print_color_grouped_volumes(cmyk_array):
    """
    Print CMYK volumes grouped by color component.
    cmyk_array: shape (n_samples, 4) - each row is a well, columns are C,M,Y,K
    """
    # Convert to numpy array for easier manipulation
    cmyk_array = np.array(cmyk_array)
    n_samples = cmyk_array.shape[0]
    # Extract each color channel and scale to MAX_WELL_VOLUME
    cyan_values = [round(cmyk_array[i, 0] * MAX_WELL_VOLUME, 2) for i in range(n_samples)]
    magenta_values = [round(cmyk_array[i, 1] * MAX_WELL_VOLUME, 2) for i in range(n_samples)]
    yellow_values = [round(cmyk_array[i, 2] * MAX_WELL_VOLUME, 2) for i in range(n_samples)]
    black_values = [round(cmyk_array[i, 3] * MAX_WELL_VOLUME, 2) for i in range(n_samples)]
    print("Cyan:")
    print(", ".join([f"{val}" for val in cyan_values]))
    print("Magenta:")
    print(", ".join([f"{val}" for val in magenta_values]))
    print("Yellow:")
    print(", ".join([f"{val}" for val in yellow_values]))
    print("Black:")
    print(", ".join([f"{val}" for val in black_values]))
    # Print total volumes for verification
    for i in range(n_samples):
        total = sum([round(cmyk_array[i, j] * MAX_WELL_VOLUME, 2) for j in range(4)])
        print(f"Well {i} total: {total:.2f}µL")
def suggest_next_sample_simple(cmyk_samples, distances, target_cmyk):
    """
    Simple alternative to Bayesian Optimization - uses a heuristic approach.
    Returns a new CMYK sample that's likely to be closer to the target.
    """
    # Convert to numpy arrays
    cmyk_samples = np.array(cmyk_samples)
    distances = np.array(distances)
    target_cmyk = np.array(target_cmyk)
    # Find the best sample so far
    best_idx = np.argmin(distances)
    best_sample = cmyk_samples[best_idx]
    # Strategy 1: Move 30% of the way from best sample toward target
    weight = 0.3
    new_sample = (1 - weight) * best_sample + weight * target_cmyk
    # Ensure the sum is 1.0 (for proper scaling)
    new_sample = new_sample / np.sum(new_sample)
    return new_sample
def main_workflow_simplified():
    # 1) Set target color in RGB
    target_rgb_255 = TARGET_RGB          # e.g. [224, 163, 46]
    target_rgb = np.array(target_rgb_255) / 255 # convert to [0..1]
    target_cmyk = RGB_to_CMYK(target_rgb)       # in [0..1]
    print(f"Target RGB: {target_rgb_255} → CMYK: {[round(v, 3) for v in target_cmyk]}")
    # 2) Generate 5 initial LHS samples (CMYK in [0,1])
    n_init = 5
    # Set sum_constraint=1.0 since we'll scale to MAX_WELL_VOLUME later
    lhs_samples = generate_lhs_samples(n_samples=n_init, n_vars=4, sum_constraint=1.0, seed=1)
    # 3) PAUSE: Display CMYK volumes for manual dispensing
    print("\n==== Initial 5 CMYK Samples to Dispense Manually ====")
    print_color_grouped_volumes(lhs_samples)
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
    # Calculate distances to target
    distances = []
    for cmyk in initial_cmyk_list:
        dist = calculate_color_distance(cmyk, target_cmyk)
        distances.append(dist)
    # Print initial distances
    print("\n==== Initial Distances to Target ====")
    for i, dist in enumerate(distances):
        print(f"Well {i} distance: {dist:.4f}")
    # Keep track of all samples and their distances
    all_cmyk_samples = initial_cmyk_list.copy()
    all_distances = distances.copy()
    # Keep track of how many total samples dispensed
    total_samples = n_init
    max_samples = 15      # end condition
    threshold = 0.05      # distance threshold
    # Find current best sample
    best_idx = np.argmin(all_distances)
    best_dist = all_distances[best_idx]
    print(f"Current best distance = {best_dist:.4f}, in well {best_idx}")
    while total_samples < max_samples:
        # Check if we already have a good enough sample
        if best_dist < threshold:
            print(f"Stopping early because best distance {best_dist:.4f} < {threshold}")
            break
        # 7) Suggest the next sample using simple heuristic
        print("\nGenerating next sample recommendation...")
        new_cmyk = suggest_next_sample_simple(all_cmyk_samples, all_distances, target_cmyk)
        # 8) PAUSE: Display the next CMYK to manually dispense
        new_sample_well = total_samples
        print(f"\n==== Next CMYK Sample (Well {new_sample_well}) ====")
        # Format as color-grouped output even though it's just one sample
        print("Cyan:")
        print(f"{round(new_cmyk[0] * MAX_WELL_VOLUME, 2)}")
        print("Magenta:")
        print(f"{round(new_cmyk[1] * MAX_WELL_VOLUME, 2)}")
        print("Yellow:")
        print(f"{round(new_cmyk[2] * MAX_WELL_VOLUME, 2)}")
        print("Black:")
        print(f"{round(new_cmyk[3] * MAX_WELL_VOLUME, 2)}")
        total = sum([round(val * MAX_WELL_VOLUME, 2) for val in new_cmyk])
        print(f"Total volume: {total:.2f}µL")
        # Wait for user to manually dispense and signal completion
        wait_for_user_input("\nPlease manually dispense this sample, then press Enter to capture image...")
        # 9) Take a picture again
        print("Capturing new image...")
        asyncio.run(capture_photo())
        print("Image captured successfully!")
        # 10) Analyze image: we only need the new well
        print("Analyzing updated image...")
        _, new_rgb_values = compute_rgb_grid(config.CAPTURE_IMAGE_PATH, config.ROWS, config.COLS,
                                            config.TOP_LEFT, config.BOTTOM_RIGHT)
        # Extract the single well
        new_rgb = new_rgb_values[new_sample_well]
        print(f"Well {new_sample_well} RGB = {new_rgb}")
        # 11) Convert this new RGB -> CMYK
        row_rgb01 = np.array(new_rgb) / 255.0
        measured_cmyk = RGB_to_CMYK(row_rgb01)
        print(f"Measured CMYK = {[round(v, 3) for v in measured_cmyk]}")
        # 12) Calculate distance and update tracking
        new_dist = calculate_color_distance(measured_cmyk, target_cmyk)
        print(f"New distance to target: {new_dist:.4f}")
        # Add to our collections
        all_cmyk_samples.append(measured_cmyk)
        all_distances.append(new_dist)
        # Update best if this is better
        if new_dist < best_dist:
            best_dist = new_dist
            best_idx = len(all_distances) - 1
            print(f"New best match found in Well {best_idx}!")
        total_samples += 1
        # 13) Check if new distance meets threshold
        if new_dist < threshold:
            print(f"Distance {new_dist:.4f} < {threshold}, stopping.")
            break
    print("\n==== Final Results ====")
    best_idx = np.argmin(all_distances)
    best_dist = all_distances[best_idx]
    best_cmyk = all_cmyk_samples[best_idx]
    print(f"Total samples used: {total_samples}")
    print(f"Best distance: {best_dist:.4f}")
    print(f"Best CMYK: {[round(v, 3) for v in best_cmyk]}")
    print(f"Best match is in Well {best_idx}")
    # Show best values in practical volumes
    best_volumes = [round(val * MAX_WELL_VOLUME, 2) for val in best_cmyk]
    print(f"Best CMYK volumes: C={best_volumes[0]}µL, M={best_volumes[1]}µL, Y={best_volumes[2]}µL, K={best_volumes[3]}µL")
    print(f"Total volume: {sum(best_volumes):.2f}µL")
if __name__ == "__main__":
    main_workflow_simplified()
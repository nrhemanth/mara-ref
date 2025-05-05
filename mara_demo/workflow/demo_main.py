'''
Vattanary Tevy - Modified for Interactive Workflow
With improved suggestion algorithm
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

def suggest_next_sample_improved(cmyk_samples, distances, target_cmyk, prev_suggested=None, prev_measured=None):
    """
    An improved suggestion algorithm that:
    1. Learns from the difference between suggested and measured values
    2. Adapts the weight based on progress
    3. Preserves relative CMYK values
    4. Uses information from multiple samples
    
    Args:
        cmyk_samples: List of all measured CMYK samples so far
        distances: List of distances corresponding to samples
        target_cmyk: Target CMYK value we're trying to match
        prev_suggested: Previously suggested CMYK (to learn from differences)
        prev_measured: Previously measured CMYK after dispensing
    """
    # Convert to numpy arrays
    cmyk_samples = np.array(cmyk_samples)
    distances = np.array(distances)
    target_cmyk = np.array(target_cmyk)
    
    # Find the best sample so far
    best_idx = np.argmin(distances)
    best_sample = cmyk_samples[best_idx]
    
    # Calculate how much progress we've made
    initial_dist = distances[0] if len(distances) > 0 else 1.0
    current_best_dist = distances[best_idx]
    progress_ratio = current_best_dist / initial_dist
    
    # Adapt weight based on progress (smaller steps as we get closer)
    base_weight = 0.3
    adaptive_weight = base_weight * progress_ratio
    
    # Correction factor based on previous suggestion vs measurement
    correction = np.ones(4)
    if prev_suggested is not None and prev_measured is not None:
        # Calculate ratio between what we suggested and what was measured
        prev_suggested = np.array(prev_suggested)
        prev_measured = np.array(prev_measured)
        
        # Avoid division by zero
        prev_suggested = np.where(prev_suggested < 0.001, 0.001, prev_suggested)
        
        # Calculate correction factors (limit to reasonable range)
        raw_correction = np.maximum(prev_measured, 0.001) / prev_suggested
        correction = np.clip(raw_correction, 0.1, 10.0)
        print(f"Correction factors: {[round(c, 2) for c in correction]}")
    
    # Base suggestion: Move from best sample toward target with adaptive weight
    new_sample = (1 - adaptive_weight) * best_sample + adaptive_weight * target_cmyk
    
    # Apply correction factor (what we suggest vs what actually gets measured)
    corrected_sample = new_sample * correction
    
    # Ensure non-negative values
    corrected_sample = np.maximum(corrected_sample, 0)
    
    # Scale to ensure total volume constraint is maintained
    # But preserve relative proportions of CMYK
    total = np.sum(corrected_sample)
    if total > 0:
        # We want the total to be 1.0 (we'll multiply by MAX_WELL_VOLUME later)
        corrected_sample = corrected_sample / total
    
    return corrected_sample

def main_workflow_improved():
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
    
    # Initialize lists to track suggested vs measured CMYK
    suggested_cmyk_history = []
    measured_cmyk_history = []

    # Keep track of how many total samples dispensed
    total_samples = n_init
    max_samples = 15      # end condition
    threshold = 0.05      # distance threshold

    # Find current best sample
    best_idx = np.argmin(all_distances)
    best_dist = all_distances[best_idx]
    print(f"Current best distance = {best_dist:.4f}, in well {best_idx}")

    prev_suggested = None  # First suggestion has no previous reference
    prev_measured = None
    
    while total_samples < max_samples:
        # Check if we already have a good enough sample
        if best_dist < threshold:
            print(f"Stopping early because best distance {best_dist:.4f} < {threshold}")
            break

        # 7) Suggest the next sample using improved heuristic
        print("\nGenerating next sample recommendation...")
        new_cmyk = suggest_next_sample_improved(
            all_cmyk_samples, all_distances, target_cmyk, 
            prev_suggested=prev_suggested, 
            prev_measured=prev_measured
        )
        
        # Store this suggestion for future reference
        prev_suggested = new_cmyk.copy()
        suggested_cmyk_history.append(new_cmyk.copy())

        # 8) PAUSE: Display the next CMYK to manually dispense
        new_sample_well = total_samples
        print(f"\n==== Next CMYK Sample (Well {new_sample_well}) ====")
        
        # Format as color-grouped output
        cyan_vol = round(new_cmyk[0] * MAX_WELL_VOLUME, 2)
        magenta_vol = round(new_cmyk[1] * MAX_WELL_VOLUME, 2)
        yellow_vol = round(new_cmyk[2] * MAX_WELL_VOLUME, 2)
        black_vol = round(new_cmyk[3] * MAX_WELL_VOLUME, 2)
        
        print("Cyan:")
        print(f"{cyan_vol}")
        print("Magenta:")
        print(f"{magenta_vol}")
        print("Yellow:")
        print(f"{yellow_vol}")
        print("Black:")
        print(f"{black_vol}")
        
        total = sum([cyan_vol, magenta_vol, yellow_vol, black_vol])
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
        
        # Store this measurement for future reference
        prev_measured = measured_cmyk
        measured_cmyk_history.append(measured_cmyk)
        
        # 12) Calculate distance and update tracking
        new_dist = calculate_color_distance(measured_cmyk, target_cmyk)
        print(f"New distance to target: {new_dist:.4f}")
        
        # Compare suggested vs measured
        print("Suggested vs Measured CMYK:")
        for i, (name, s, m) in enumerate(zip(['C', 'M', 'Y', 'K'], new_cmyk, measured_cmyk)):
            print(f"  {name}: Suggested={round(s*MAX_WELL_VOLUME, 2)}µL, Measured={round(m, 3)}, Ratio={round(m/s if s > 0 else 0, 2)}")

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
    main_workflow_improved()
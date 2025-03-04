'''
Vattanary Tevy - created 03/02/2025
Orchestrates entire workflow
'''

from camera import capture_photo
# from image_analysis import
# from lhs import
# from opentrons_control import
# from bayesian import
import config
import asyncio

 async def main_workflow():

    # 1. Connect to camera and capture picture
     print("Capturing image...")
     CAPTURE_IMAGE_PATH = capture_photo(config.CAMERA_URI)
     print(f"Image saved at: {CAPTURE_IMAGE_PATH}")

     # 2. Analyze picture and detect contours
     print("Analyzing image...")
     background_rgb_values = analyze_image(CAPTURE_IMAGE_PATH, config.ROWS, config.COLS, config.TOP_LEFT, config.BOTTOM_RIGHT)
     plot_grid(background_rgb_values, rows=config.ROWS, cols=config.COLS)

    # 3. Generate LHS samples
    # lhs_samples = generate_lhs_samples(
    #     n_samples=4, n_vars=4, sum_constraint=config.MAX_WELL_VOLUME, seed=1
    # )
    # print("LHS samples:", lhs_samples)

    # # 4. Dispense samples using Opentrons
    # run_opentrons_mix(lhs_samples)

    # # 5. Capture new picture


    # # 6. Run BO to optimize results
    # best_params = run_bayesian_optimization(target_rgb=[75, 46, 131], n_iters=10)
    # print("Optimal CMYK mixture found:", best_params)

    # 7. Repeat until condition(s) met


if __name__ == "__main__":
    main_workflow()

# if __name__ == "__main__":
#     result = asyncio.run(capture_photo())
#     print(result)
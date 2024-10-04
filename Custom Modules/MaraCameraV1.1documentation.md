# Mara Camera Module V1.1 
Author: Victor Yin

##
The Mara Camera Module is an open-source, 3D-printed imaging tool capable of running Raspberry Pi OS. It is a modular attachment to the Opentron OT-2 workspace.

<div align="center">
  <a>
    <img src="images/unnamed.png" alt="Logo" style="width:50%">
    <!---<img src="/Users/ctuwsunlab/Documents/GitHub/Mara_Opentron/images/unnamed.png" alt="Logo" width="80" height="80"> -->
  </a>
</div>

This repository contains the design procedures required to build the first version of the camera module, which utilizes a Pi 4B 8gb board and a wide-angle Arducam IMX708 (SKU B0310). 


## Specifications
+ Compatible with clear 96 well plates.
+ 152° diagonal FOV camera capable of imaging the underside of a 96 well plate. 
+ User-customizable to fit a variety of cameras and raspberry pi models. 
+ Maximum dimensions (Extruded Raspberry Pi holder): 141.5 (L) x 100 (W) x 82 (H)
+ Attachment dimensions: 
    + Bottom Opentron attachment: 127 x 85 mm
    + Top 96 well-plate: 123.94 x 80.96 mm (Inner)


## Build Files: 
+ The CAD file is available for download in **cads** in Solidworks format.
+ Depending on the Raspberry Pi and camera model, user modifications may be necessary. 

## Fabrication: 
+ The original STL file is located in **printer_exports**
+ Recommended printer settings: 
    + Printer: Bambu Lab X1-Carbon
    + Filament: Bambu PLA
    + Nozzle settings: Default 0.2 mm at 200 C 
    + Infill percentage: 20-25%
    + Support type: Tree
+ Before installing the Pi-board and camera, attach the printed module to the Opentron workspace to double check that it is compatible. 
+ Connect the Pi-board with the camera using a ribbon cable. Instructions can be found [here](https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/Quick-Start-Guide/).
+ Insert the Pi-board first with all ports facing outwards in the appropriate orientations. (see figure 2)
+ Insert the camera, making sure the side with the ribbon cable is inline with the designed indent. Adjust the fitting tightness with tape if necessary. Secure the ribbon cable with tape or baling wire so as to not obstruct the camera’s FOV. 
<p align = "center">
  <img src="images/IMG_0004.JPG" alt="birdeye_camera_photo" style="width:50%">
</p>

## Set-up:
+ Install the Raspberry Pi OS on a microSD card (larger than 8gb storage). See instructions here.
+ Insert the microSD card into the Pi-board using the SD port on its underside. Then connect the board with an ethernet cable, power cable, and one of the following: 
    + USB-A cable to a laptop, or 
    + USB-A cables to a mouse and keyboard, and a mini HDMI cable to a monitor
+ Power on the board. The light next to the microSD card slot should blink to signal that it is powered. 
+ Activate the Arducam IMX708. See instructions [here](https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/12MP-IMX708/) and common troubleshooting [here](https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/Troubleshooting/). 

## Contributing
Please contact hy717@uw.edu for any questions regarding the camera module. 

## Open Source
Mara Camera Module is licensed under a Creative Commons Attribution 4.0 Unported License (CC BY 4.0) and Certified Open Source Hardware (Work in Progress)

## Design Comments: 
In order to be compatible with the opentron workspace and the pipet arm, the height of the module -including the attached well plate- needed to remain smaller than 100 mm. The bottom of the module needs to be consistent with the Opentron workspace, which is 128 by 86 mm.

The camera position is centered, and requires a clearance of 70 mm to focus and image the entire well plate in its FOV. See figure 3 for a visualization of the camera’s FOV and figure 4 for the output image. 


<p align="center">
  <img src="images/IMG_0005.JPG" alt="birdeye_photo" style="width:30%" hspace="10">
  <img src="images/cad_orthog.png" alt="cad_orthogonal" style="width:40%" hspace="10">
    
</p>


## Limitations:
+ To account for the space taken by the camera, the Pi-board is housed in an extruded section, which restricts the placement of other equipment on certain adjacent workstations. 
+ The wide angle camera results in a fish-eye effect, which requires de-fishing in a post-processing program.
+ The clarity and accuracy of imaged colors depend greatly on surrounding light sources. We recommend supplementing the module with white LED lights around the workstation. 


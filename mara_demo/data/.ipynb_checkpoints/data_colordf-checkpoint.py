#%%
import pandas as pd
from opentrons.types import Location, Point
import glob
import os
import json

#%%
##Defining locations - map
x5 = 118.5 + 13.3    ## x5 & y5 are the coordinates for the bottom left corner of plate 5, same idea for x2 & y2 
y5 = 79.3 + 12.3    
x2 = 118.5 + 13.3    ## x_code = x_irl + 13.3
y2 = -11 + 12.3      ## y_code = y_irl + 12.3 

p0 = [[x2 + 0.125*132.4, y2 + 0.75*90.3],#0
      [x2 + 0.375*132.4, y2 + 0.75*90.3],#1
      [x2 + 0.625*132.4, y2 + 0.75*90.3],#2
      [x2 + 0.875*132.4, y2 + 0.75*90.3],#3
      [x2 + 0.125*132.4, y2 + 0.25*90.3],#4
      [x2 + 0.375*132.4, y2 + 0.25*90.3],#5
      [x2 + 0.625*132.4, y2 + 0.25*90.3],#6
      [x2 + 0.875*132.4, y2 + 0.25*90.3]]#7

p1 = [x5+0.25*132.4, y5 + 0.75*90.3]
p2 = [x5 + 0.75*132.4,p1[1]]
p3 = [p1[0],y5 + 0.25*90.3]
p4 = [p2[0],p3[1]]

# %%
## The coordinates are absolute 
## with reference to the bottom left corner of slot 1 as origin.
## x, y, and z can be a float or integer

loc0 = [
    Location(Point(p0[0][0],p0[0][1],6),None),
    Location(Point(p0[1][0],p0[1][1],6),None),
    Location(Point(p0[2][0],p0[2][1],6),None),
    Location(Point(p0[3][0],p0[3][1],6),None),
    Location(Point(p0[4][0],p0[4][1],6),None),
    Location(Point(p0[5][0],p0[5][1],6),None),
    Location(Point(p0[6][0],p0[6][1],6),None),
    Location(Point(p0[7][0],p0[7][1],6),None)
]

loc1 = Location(Point(p1[0],p1[1],6),None) # location of blue dye 
loc2 = Location(Point(p2[0],p2[1],6),None) # location of red dye 
loc3 = Location(Point(p3[0],p3[1],6),None) # location of yellow dye
loc4 = Location(Point(p4[0],p4[1],6),None)  # location of green dye

# %%
# For RGB stocks 
def RGB_stocks():
        RGB_stocksandlocations = {'mix_loc': [loc0[0], loc0[1], loc0[2],loc0[3],loc0[4],loc0[5],loc0[6],loc0[7]], 
                'stock_red_vol':         [100, 223, 323, 423, 523, 698, 400, 309],
                'stock_blue_vol':        [550, 317, 130, 150, 232, 423, 589, 123],
                'stock_green_vol':       [30, 20, 30, 10, 10, 10, 10, 10],
                'loc_red_stock':         [loc2, loc2, loc2, loc2, loc2, loc2, loc2, loc2],
                'loc_blue_stock':   [loc1, loc1, loc1, loc1, loc1, loc1, loc1, loc1],
                'loc_green_stock':  [loc4, loc4, loc4, loc4, loc4, loc4, loc4, loc4,],
                }
        RGB_stock = pd.DataFrame(data=RGB_stocksandlocations)
        return RGB_stock

# %%
RGB_stock = RGB_stocks()
blue_stock_vol = RGB_stock['stock_blue_vol']
red_stock_vol = RGB_stock['stock_red_vol']
green_stock_vol = RGB_stock['stock_green_vol']

blue_stock_loc = RGB_stock['loc_blue_stock']
red_stock_loc = RGB_stock['loc_red_stock']
green_stock_loc = RGB_stock['loc_green_stock']

dispense = RGB_stocks['mix_loc']

# %%
# For CMYK 
def CMYK_stocks():
        CMYK_stocksandlocations = {'mix_loc': [loc0[0], loc0[1], loc0[2],loc0[3],loc0[4],loc0[5],loc0[6],loc0[7]], 
                'stock_cyan_vol':         [100, 223, 323, 423, 523, 698, 400, 309],
                'stock_magenta_vol':        [550, 317, 130, 150, 232, 423, 589, 123],
                'stock_yellow_vol':       [30, 20, 30, 10, 10, 10, 10, 10],
                'stock_black_vol':       [30, 20, 30, 10, 10, 10, 10, 10],
                'loc_cyan_stock':         [loc2, loc2, loc2, loc2, loc2, loc2, loc2, loc2],
                'loc_magenta_stock':   [loc1, loc1, loc1, loc1, loc1, loc1, loc1, loc1],
                'loc_yellow_stock':  [loc4, loc4, loc4, loc4, loc4, loc4, loc4, loc4,],
                'loc_black_stock':  [loc4, loc4, loc4, loc4, loc4, loc4, loc4, loc4,],
                }
        CMYK_stocks = pd.DataFrame(data=CMYK_stocksandlocations)
        return CMYK_stocks
# %%
CMYK_stock = CMYK_stocks()
cyan_stock_vol = CMYK_stock['stock_cyan_vol']
magenta_stock_vol = CMYK_stock['stock_magenta_vol']
yellow_stock_vol = CMYK_stock['stock_yellow_vol']
black_stock_vol = CMYK_stock['stock_black_vol']

cyan_stock_loc = CMYK_stock['loc_cyan_stock']
magenta_stock_loc = CMYK_stock['loc_magenta_stock']
yellow_stock_loc = CMYK_stock['loc_yellow_stock']
black_stock_loc = CMYK_stock['loc_black_stock']

dispense = CMYK_stock['mix_loc']


# %%

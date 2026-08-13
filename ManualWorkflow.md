# Steps for manual workflow

## Synthesis
Synthesis is done in Mara

Example:
```
 PS C:\Users\cnt25\Documents\GitHub\Mara>  $env:ROBOT_URL = "http://192.168.1.102:31950"; uv run python -m preruns.preflight_manual protocols\2D_mapbi3_perovskite_order_matter.py input\08132026\order_check_batch1.csv
```




## Characterize
```
 $env:TSURU_PORT = "COM6"  
 python -m characterize.tsuru_camera_scan Thinfilm_20 A1 A1 results/081226/ input\test_MAPBI3\081226_clean_unclean.csv       

 python -m characterize.tsuru_pl_grid_scan Thinfilm_20 A1 D4 input\test_MAPBI3\081226_clean_unclean.csv results/081226_glass   
```


# Check the plots
example: 
```
python results/plot_pl_overlay.py results\081326\order_check_batch1 --out results/081326_order_batch1.png     
```
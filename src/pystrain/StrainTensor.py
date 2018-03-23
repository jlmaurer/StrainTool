#! /usr/bin/python2.7

############################################## standard libs
import sys
from copy import deepcopy
from math import degrees, radians, floor, ceil
##############################################  numpy & argparse
import numpy
import argparse
##############################################  pystrain
from pystrain.strain import *
from pystrain.geodesy.utm import *
from pystrain.iotools.iparser import *
import pystrain.grid
############################################## ploting
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt
from scipy.spatial import Delaunay

def plot_map(sta_list, stensor_list):
    lat0    = degrees(sum([ x.lat for x in sta_list ])/len(sta_list))
    lon0    = degrees(sum([ x.lon for x in sta_list ])/len(sta_list))
    lons    = [ degrees(x.lon) for x in sta_list ]
    lats    = [ degrees(x.lat) for x in sta_list ]
    lon_off = (max(lons)-min(lons))/10
    lat_off = (max(lats)-min(lats))/10
    my_map = Basemap(projection='merc', lat_0 = lat0, lon_0 = lon0, resolution = 'c', llcrnrlon=min(lons)-lon_off, llcrnrlat=min(lats)-lat_off, urcrnrlon=max(lons)+lon_off, urcrnrlat=max(lats)+lat_off)
    my_map.drawcoastlines()
    my_map.drawcountries()
    my_map.fillcontinents(color = 'coral')
    my_map.drawmapboundary()
    my_map.drawmeridians(numpy.arange(floor(min(lons)), ceil(max(lons)), 2), labels=[True,False,False,True])
    my_map.drawparallels(numpy.arange(floor(min(lats)), ceil(max(lats)), 2), labels=[False,True,True,False], fontsize=10)

    for sta in sta_list:
        x, y = my_map(degrees(sta.lon), degrees(sta.lat))
        my_map.plot(x, y, 'bo', markersize=10)
        plt.text(x, y, sta.name)
        #print 'Point at {}, {}'.format(degrees(sta.lon), degrees(sta.lat))

    for tnr in stensor_list:
        x, y = my_map(degrees(tnr.lon), degrees(tnr.lat))
        my_map.plot(x, y, 'r+', markersize=8)
        #print 'Tensor at {}, {}'.format(degrees(tnr.lon), degrees(tnr.lat))

    print '[DEBUG] Area is {}/{}/{}/{}'.format(min(lons), max(lons), min(lats), max(lats))
    plt.show()
    return

parser = argparse.ArgumentParser(
    formatter_class=argparse.RawTextHelpFormatter,
    description='Estimate Strain Tensor(s) from GNSS derived velocities.',
    epilog=('''National Technical University of Athens,
    Dionysos Satellite Observatory\n
Send bug reports to:
  Xanthos Papanikolaou, xanthos@mail.ntua.gr
  Demitris Anastasiou,danast@mail.ntua.gr
November, 2017'''))

parser.add_argument('-i', '--input-file',
    default=None,
    metavar='INPUT_FILE',
    dest='gps_file',
    required=True)

parser.add_argument('--x-grid-step',
    default=50000,
    metavar='X_GRID_STEP',
    dest='x_grid_step',
    type=float,
    required=False)

parser.add_argument('--y-grid-step',
    default=50000,
    metavar='Y_GRID_STEP',
    dest='y_grid_step',
    type=float,
    required=False)

parser.add_argument('-m', '--method',
    default='shen',
    metavar='METHOD',
    dest='method',
    choices=['shen', 'veis'],
    required=False)

parser.add_argument('-b', '--barycenter',
    dest='one_tensor',
    action='store_true')

##  Parse command line arguments.
args = parser.parse_args()

##  Parse stations from input file
sta_list_ell = parse_ascii_input(args.gps_file)
print '[DEBUG] Number of stations parsed: {}'.format(len(sta_list_ell))

##  Make a new station list (copy of the original one), where all coordinates
##+ are in UTM. All points should belong to the same ZONE.
mean_lon = degrees(sum([ x.lon for x in sta_list_ell ])/len(sta_list_ell))
utm_zone = floor(mean_lon/6)+31
utm_zone = utm_zone + int(utm_zone<=0)*60 - int(utm_zone>60)*60
print '[DEBUG] Mean longtitude is {} deg.; using Zone = {} for UTM'.format(mean_lon, utm_zone)
sta_list_utm = deepcopy(sta_list_ell)
for idx, sta in enumerate(sta_list_utm):
    N, E, Zone, lcm = ell2utm(sta.lat, sta.lon, Ellipsoid("wgs84"), utm_zone)
    sta_list_utm[idx].lon = E
    sta_list_utm[idx].lat = N
    assert Zone == utm_zone, "[ERROR] Invalid UTM Zone."
print '[DEBUG] Station list transformed to UTM.'

##  Compute only one Strain Tensor, at the region's barycenter
if args.one_tensor:
    if args.method == 'shen':
        sstr = ShenStrain(0e0, 0e0, sta_list_utm)
    else:
        sstr = VeisStrain(0e0, 0e0, sta_list_utm)
    sstr.set_to_barycenter()
    sstr.estimate()
    sys.exit(0)

##  Construct the grid, based on station coordinates (Ref. UTM)
strain_list = []
if args.method == 'shen':
    grd = pystrain.grid.generate_grid(sta_list_utm, args.x_grid_step, args.y_grid_step)
    print '[DEBUG] Constructed the grid. Limits are:'
    print '\tEasting : from {} to {} with step {}'.format(grd.x_min, grd.x_max, grd.x_step)
    print '\tNorthing: from {} to {} with step {}'.format(grd.y_min, grd.y_max, grd.y_step)
    print '[DEBUG] Estimating strain tensor for each cell center'
    ##  Iterate through the grid (on each cell center)
    prev_x = 0
    prev_y = 0
    node_nr = 0
    sstr = ShenStrain(0e0, 0e0, sta_list_utm)
    for x, y in grd:
        clat, clon = utm2ell(x, y, utm_zone)
        sstr.set_xy(x, y)
        #sstr.compute_z_weights()
        #sstr.compute_l_weights()
        estim2 = sstr.estimate()
        node_nr += 1
        print '[DEBUG] Computed tensor for node {}/{}'.format(node_nr, grd.xpts*grd.ypts)
        strain_list.append(Station(lat=clat, lon=clon))
        prev_x = x
        prev_y = y
else:
    points = numpy.array([ [sta.lon, sta.lat] for sta in sta_list_utm ])
    tri = Delaunay(points)
    for idx, trng in enumerate(tri.simplices):
        cx = (sta_list_utm[trng[0]].lon + sta_list_utm[trng[1]].lon + sta_list_utm[trng[2]].lon)/3e0
        cy = (sta_list_utm[trng[0]].lat + sta_list_utm[trng[1]].lat + sta_list_utm[trng[2]].lat)/3e0
        sstr = VeisStrain(cx, cy, [sta_list_utm[trng[0]], sta_list_utm[trng[1]], sta_list_utm[trng[2]]])
        estim2 = sstr.estimate()
        clat, clon = utm2ell(cx, cy, utm_zone)
        strain_list.append(Station(lat=clat, lon=clon))

plot_map(sta_list_ell, strain_list)

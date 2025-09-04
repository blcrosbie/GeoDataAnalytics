# -*- coding: utf-8 -*-
"""
Created on Thu Jun 11 06:55:13 2020

@author: blcrosbie
"""

# My arcpy functions for GUI in PyQT5:
import os, sys
import math

import arcpy
arcpy.env.overwriteOutput = True

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_ASSIGNMENTDATA_DIR = os.path.join(LOCAL_DIR, "assignment2data")

countries_shape = os.path.join(LOCAL_ASSIGNMENTDATA_DIR, "countries.shp")

polygonField = "NAME"
polygonValue = "El Salvador"

OSM_shape = os.path.join(LOCAL_ASSIGNMENTDATA_DIR, "OSMpoints.shp")
pointField = "shop"
pointValue = "supermarket"

ASSIGNMENT_OUTPUT_DIR = os.path.join(LOCAL_DIR, "results")
outputFile = os.path.join(ASSIGNMENT_OUTPUT_DIR, "OutputShapefile.shp")

def getAttributes(featureClass):
    fields = arcpy.ListFields(featureClass)
    field_list = [field for field in fields]
    return field_list

def getDropDownOptions(featureClass):
    fieldList = arcpy.ListFields(featureClass)
    field_name_list = [field.name for field in fieldList]
    return field_name_list

def getLineEntryOptions(featureClass):
    attribute_list = getDropDownOptions(featureClass)
    attrib_val_dict = {}
    for attribute in attribute_list:
        val_list = []
        with arcpy.da.SearchCursor(featureClass, (attribute)) as cursor:
            for row in cursor:
                if row[0] != ' ' and row[0] not in val_list:
                    val_list.append(row[0])
        attrib_val_dict[attribute] = val_list
        
    return attrib_val_dict


def choose_file():    
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    
    start_dir = os.path.dirname(os.path.abspath(__file__))
   
    fn = filedialog.askopenfilename(initialdir=start_dir, title="Select File", filetypes = (("shapefiles", "*.shp"),("all files", "*.*")))
    print(os.path.dirname(os.path.abspath(fn)))
    
    return fn
        
def queryShapefile(query, field, value, limit=10):
    """ pull results from shape file on filtered field and value"""
    results_dict = queryOSMfile(query, field, value, limit, internal=False)
    
    
    return results_dict


def queryOSMfile(query, field, value, limit=10, internal=False):
    """ pull results from OSM file filtered on either Shape attributes or own attributes"""
    results = []
    if internal:
        allowed_fields = ['amenity', 'cuisine', 'denominati', 'leisure', 'place', 'religion', 'shop']
    else:
        allowed_fields = ['NAME', 'SOV_A3']
        
    try:
        assert field in allowed_fields, "try again"
    except Exception as e:
        return results # empty
    
    

    OSM_featureClass = choose_file()
    all_data = {}
    attribute_list = getDropDownOptions(OSM_featureClass)
    
    for attribute in attribute_list:
        val_list = []

        with arcpy.da.SearchCursor(OSM_featureClass, (attribute)) as cursor:
            for row in cursor:
                val_list.append(row[0])
                if len(row) > 1:
                    print("WAIT A MINUTE")
        all_data[attribute] = val_list
        
    import pandas as pd
    results_df = pd.DataFrame(data=all_data, columns=list(all_data.keys()), index=list(all_data['FID']))
    
    #filter on field and value
    results_df = results_df[results_df[field] == value]
    results_df = results_df.reset_index(drop=True)
    
    #filter on limit
    results_df = results_df.iloc[0:limit]
         
    return results_df

#def findCountry(poi, featureClass):
    
def convert_miles_to_km(distance):
    return distance*1.60934

def get_KM_distance(distance, unit):
    if unit.lower() == 'mi' or unit.lower() == 'miles':
        distance = convert_miles_to_km(distance)
    elif unit.lower() == 'm' or unit.lower() == 'meters':
        distance = distance/1000
    elif unit.lower() == 'ft' or unit.lower() == 'feet':
        distance = distance/3280.839895
    else:
        print("Change your unit to something more common: ", unit)
    
    print("distance in km: ", distance)
    
    return distance
    
    

def createPolygonBuffer(lat, lon, radius=1, unit='km', sides=6):
    
    lat_rad = (lat/180)*math.pi 
    lon_rad = (lon/180)*math.pi
    
    if unit != 'km':
        radius = get_KM_distance(radius, unit)
        
    # in degrees, bearing is [30, 90, 150, 210, 270, 330] 
    # circle is 360 degrees
    interval = (2*math.pi)/sides
    # since we start at 0, first bearing splits middle/ interval/2
    start = interval/2
    
    radian_bearings = [start + i*interval for i in range(sides)]
    
    # latitude degrees
    # equator = 110.567 km
    # poles = 110.699 km
    # 1 degree latitde ~ 111km
    # R is Radius of the earth = 6731 km
    R = 6371
    d_over_R = radius/R
    
    polygon_points = []
    for radian in radian_bearings:
        new_lat_rad = math.asin(math.sin(lat_rad)*math.cos(d_over_R) + math.cos(lat_rad)*math.sin(d_over_R)*math.cos(radian))
        
        new_lon_rad = lon_rad + math.atan2((math.sin(radian)*math.sin(d_over_R)*math.cos(lat_rad)), (math.cos(d_over_R)-(math.sin(lat_rad)*math.sin(new_lat_rad)))) 

        new_lat = new_lat_rad * 180/math.pi
        new_lon = new_lon_rad * 180/math.pi
        polygon_points.append(({"latitude": new_lat, "longitude": new_lon}))

    return polygon_points

def createPolygonGeometry(POI_list):
    geometry = []
    for poi in POI_list:
        geometry.append(arcpy.Point(poi['latitude'],poi['longitude']))
        
    return arcpy.Polygon(arcpy.Array(geometry))
        


# if imported arcpy
#def findAllPOIinRadius(center_lat, center_lon, all_poi_list, radius=0, units='km'):
#    
#    buffer_shape_poi_list = createPolygonBuffer(center_lat, center_lon, radius, units, sides=6)
#    buffer_shape = createPolygonGeometery(buffer_shape_poi_list)
#    
#    for poi in all_poi_list:
#        lat = poi['y']
#        lon = poi['x']
#        geojson_point = {"type": "Point", "coordinates": [lat, lon]}
#        point = arcpy.AsShape(geojson_point)
        
# if no arcpy
    

def is_point_in_path(x , y, poly):
    num = len(poly)
    j = num - 1
    c = False
    for i in list(range(0, num)):
        if (poly[i][1] > y) != (poly[j][1] > y):
            if (x < poly[i][0] + (poly[j][0] - poly[i][0]) * (y - poly[i][1])/(poly[j][1] - poly[i][1])):
                c = not c
        j = i
    return c


def findAllPOIinRadius(center_lat, center_lon, all_poi_list, radius=0, units='km'):
    buffer_shape_poi_list = createPolygonBuffer(center_lat, center_lon, radius, units, sides=6)
    
    
    print(buffer_shape_poi_list)
    
    buffer_tuples = [(poi['longitude'], poi['latitude']) for poi in buffer_shape_poi_list]
    
    filtered_poi = []
    for poi in all_poi_list:
        if is_point_in_path(poi['x'], poi['y'], buffer_tuples):
            filtered_poi.append(poi)
            
    return filtered_poi
        
    
    
    
    

if __name__ == '__main__':
    
#    countries_shape
    countries = []
    for row in arcpy.da.SearchCursor(countries_shape, ["NAME", "SHAPE@"]):
        print("Country: {0}".format(row[0]))
        country_boundary = []
        for points in row[1]:
            ndx = 0
            for pnt in points:
                this_row = {"index": ndx, "x": pnt.X, "y": pnt.Y, "z": pnt.Z, "m": pnt.M}
                ndx += 1
                country_boundary.append(this_row)
        this_country = {row[0]: country_boundary}
        
        countries.append(this_country)
        
    # OSM_shape
    all_OSM_points = []
    for row in arcpy.da.SearchCursor(OSM_shape, ["SHAPE@"]):
        points = []
        ndx = 0
        for pnt in row[0]:
            this_row = {"index": ndx, "x": pnt.X, "y": pnt.Y, "z": pnt.Z, "m": pnt.M}
            ndx += 1
            all_OSM_points.append(this_row)
            
    

    
        
    test_POI = all_OSM_points[0]
    test_lat = test_POI['y']
    test_lon = test_POI['x']
    test_radius = 200
    test_units = 'm'
    
    my_list = findAllPOIinRadius(test_lat, test_lon, all_OSM_points, test_radius, test_units)
    
    print(my_list)           
        
     

    

            

    
    
    
#    

    osm_lookup = getLineEntryOptions(OSM_shape)
#    
##    my_limit = 15
##    my_field = 'shop'
##    my_value = 'convenience'
##    my_query = ''
###    my_results = queryShapefile(my_query, my_field, my_value, my_limit)
##    my_results = queryOSMfile(my_query, my_field, my_value, my_limit, internal=True)
##    print(my_results)
#    non_duplicate_shape_osm = []
#    for shape in osm_lookup['Shape']:
#        if shape not in non_duplicate_shape_osm:
#            non_duplicate_shape_osm.append(shape)
#    
#    print("SHAPE OPTIONS in COUNTRIES.shp: ", poly_lookup['Shape'])
##    print("SHAPE OPTIONS in OSM.shp: ", non_duplicate_shape_osm)
    
    
    
    
    
    

    
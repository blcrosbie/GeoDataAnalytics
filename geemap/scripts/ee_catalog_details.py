
import os, sys, json

import numpy as np

#import pandas as pd
#import geopandas as gpd
#import shapely
#from shapely.geometry import LinearRing, Polygon
#import pyproj

import datetime

#import geemap
#from ipyleaflet import GeoJSON

import ee
from setup_gee import ee_init
ee_init()

from ee_catalog import read_catalog

# import all the common scripts as cs
import common as cs



def footprint2geometry(fp):
    coordinates = fp['coordinates']
    ring = LinearRing(coordinates)
    s = Polygon(ring)
    return s

def translate_unix_time(Unix_Time_ms):
    # our unix time stamp in ms, change back to s
    seconds = Unix_Time_ms/1000
    translate_date = datetime.datetime.utcfromtimestamp(seconds).strftime("%Y-%m-%d")
    return translate_date


    
# def get_name_options(name):
    
#     # first name should be all '/'
#     # go from back to front replacing / with _
#     all_name_options = [name]
#     options_count = len(name.split('_'))

#     print(options_count)
    
#     if options_count-1 > 1:
#         for i in range(options_count-1):
#             # first option all replaced already in list
#             first = name.split('_')[0:options_count-i-1]
#             last = name.split('_')[options_count-i-1: options_count]
#             adjusted_name = '/'.join(first) + '_' + '_'.join(last)
#             all_name_options.append(adjusted_name)

#     last_option = name.replace('_', '/')

#     if last_option not in all_name_options:
#         all_name_options.append(last_option)

        
#     # find the right name that will satisfy the ImageCollection argument
#     return all_name_options

def get_ImageCollection_info(IC_id):
    # from an image collection:
    # 1. extract the list of images included in this set
    
    # all_id_options = get_name_options(name)
    # for IC_id in all_id_options:

    image_collection = ee.ImageCollection(IC_id)
    features = image_collection.getInfo()['features']
    df = pd.DataFrame(dtype=object)

    row_count = 0

    for feat in features:
        feat_id = feat['id']
        start = feat['properties']['system:time_start']
        start_date = translate_unix_time(start)
        end = feat['properties']['system:time_end']
        end_date = translate_unix_time(end)
        footprint = feat['properties']['system:footprint']
        geometry = footprint2geometry(footprint)

        for band in feat['bands']:
            # bands.append(band['id'])
            band_crs = band['crs']
            band_dim_x = band['dimensions'][0]
            band_dim_y = band['dimensions'][1]
            this_feat = {'id': feat_id, 'band': band['id'], 'crs':band_crs, 'dim_x': band_dim_x, 'dim_y': band_dim_y, 'start':start, 'end':end, 'start_date': start_date, 'end_date': end_date, 'geometry': geometry}
            this_df = pd.DataFrame(this_feat, index=[row_count], dtype=object)
            row_count += 1
            df = pd.concat([df, this_df], axis=0)



    return df


def get_Image_info(img_id):
    image = ee.Image(img_id)
    features = image.getInfo()
    # print(features)

    return


def get_FeatureCollection_info(FC_id):
    FC = ee.FeatureCollection(FC_id)
    features = FC.getInfo()
    print(features)
    print(STOP)
    return



def get_info(dataset):
    dataset_id = dataset['dataset_id']
    dataset_type = dataset['dataset_type']

    if dataset_type == 'ImageCollection':
        metadata = get_ImageCollection_info(dataset_id)
    elif dataset_type == 'Image':
        metadata = get_Image_info(dataset_id)
    elif dataset_type == 'FeatureCollection':
        metadata = get_FeatureCollection_info(dataset_id)
    else:
        print("Undefined Type: ", dataset_type)

    return metadata


    # 2. for each image, extract the geography (polygon), time frame, and bands (info)
    #  create shapefile to autoload into the GUI for these filters
    # 2a. Polygon
    # 2b. Time Frame
    # 2c. Band (and get Band info for specific data searches)



    # 3. for the whole collection, extract the provider/source of data for citation
    # 3a. in 'properties' -> 'provider', 'provider_url', 'source_tags'
    

            # 1b. with ImageCollection Name, we can run ee.ImageCollection(<name>).getInfo()
        #    to extract geometry data and other properties for metadata filtering
        # IC_details = get_ImageCollection_info(IC)



####################################################################






####################################################################

# "dataset_id" "dataset_type"
def analyze_catalog():
    # self.get_ee_catalog()
    catalog = read_catalog()
    print("Number of Datasets in Catalog:", len(catalog))

    dataset_types = []
    # dataset_ids = []
    type_id_lookup = {}
    all_tags = []
    tag_id_lookup = {}

    for dataset in catalog:
        d_type = dataset['dataset_type']
        d_id = dataset['dataset_id']
        d_tags = dataset['tags']
        # print(d_type)
        # print(d_id)
        # print(d_tags)

        if d_type not in dataset_types:
            dataset_types.append(d_type)
            type_id_lookup.update({d_type: [d_id]})

        else:
            type_id_lookup[d_type].append(d_id)


        for tag in d_tags:
            if tag not in all_tags:
                all_tags.append(tag)
                tag_id_lookup.update({tag: [d_id]})
            else:
                tag_id_lookup[tag].append(d_id)



    print(dataset_types)
    print(type_id_lookup)
    print(all_tags)
    # print(tag_id_lookup)


def test_get_info():
    final_df = pd.DataFrame(dtype=object)

    for dataset in catalog:       
        # # for comprehensive tag list
        # for tag in dataset['tags']:
        #     if tag not in all_tags:
        #         all_tags.append(tag)

        try:
            dataset_df = get_info(dataset)
        except Exception as e:
            print("Failed on:", dataset)
            print(e)
            dataset_df = pd.DataFrame()



        if dataset_df is not None:
            final_df = pd.concat([final_df, dataset_df], axis=0)

    gdf = gpd.GeoDataFrame(final_df, geometry=final_df.geometry)
    fn = 'gee_catalog.geojson'
    outfile = os.path.join(os.getcwd(), os.path.join('catalog', fn))
    gdf.to_file(outfile, driver="GeoJSON")


# =====================================================================
# Calculate Requests
# =====================================================================


def evaluate_request(result):
    request_count = 0
    meta = {}

    static_request_labels = ['type', 'bands', 'id', 'version', 'properties']
    dynamic_request_labels = ['features']


    static_count = 0
    dynamic_count = 0

    for key, val in result.items():
        if isinstance(val, list):
            # for v in val:
                # print(v)
            this_count = len(val)
            # print("{}: \t{}".format(key, len(val)))    
                
        elif isinstance(val, dict):
            this_count = len(list(val.keys()))
            # print("{}: \t{}".format(key, this_count)
                
        else:
            this_count = 1
        

        if key in static_request_labels:
            static_count += this_count

        else:
            dynamic_count = this_count

        # print("{}: \t{}".format(key, this_count))
        meta[key] = this_count
    
    
    meta = {'static': static_count, 'dynamic': dynamic_count}
    
    # meta['total'] = request_count
    return meta



def calculate_requests(dataset):
    """ Create a script to step into each getInfo function from ee method"""
    request_calculations = {
                    'static': 0,
                    'dynamic': 0,
                    'delay': 0,
                    'max_day_range': 0,
                    'expired': False
                    }


    # Get the current catalog
    d_type = dataset['dataset_type']
    d_id = dataset['dataset_id']

    # Find if dataset has expired and set the end date for getInfo filter
    dataset_end = dataset['dataset_end']
    if dataset_end is None or dataset_end == 'Present':
        request_calculations['expired'] = False
        end = datetime.datetime.today() - datetime.timedelta(days=1)
    else:
        request_calculations['expired'] = True
        end = cs.convert_date(dataset_end)

    

    # Start Day Range at 1 delta from end date 
    filter_end = end.strftime('%Y-%m-%d')
    day_range_cap = 10
    day_range = 1
    pattern_established = False
    previous_diff = 0
    max_diff = 1
    request_allowed = True

    while not pattern_established and request_allowed:
        filter_start = (end - datetime.timedelta(days=day_range)).strftime('%Y-%m-%d')

        if d_type == 'ImageCollection':
            try:
                res = ee.ImageCollection(d_id).filterDate(filter_start, filter_end)
                result_info = res.getInfo()
                meta_info = evaluate_request(result_info)
                request_calculations['static'] = meta_info['static']

                # Initialize the dynamic counter difference
                if meta_info['dynamic'] > 0:
                    current_diff = meta_info['dynamic'] - previous_diff
                    if request_calculations['delay'] == 0:
                        request_calculations['delay'] = day_range


                    if current_diff == previous_diff:
                        pattern_established = True
                        # If there is a consistent feature count in result, then update the delay
                        request_calculations['delay'] = day_range
                        request_calculations['dynamic'] = current_diff
                        # calculate the 5000 element limit 
                        request_calculations['max_day_range'] = int((5000 - request_calculations['static'])/current_diff)
                    else:
                        # update previous diff
                        previous_diff = meta_info['dynamic']
                        # store a maximum if the pattern is never established
                        if current_diff >= max_diff:
                            max_diff = current_diff

                # Now if we get to the day range cap, and no pattern exists, use the max diff
                if day_range > day_range_cap and not pattern_established:
                    # cancel any further requests, to save resources + time
                    request_allowed = False
                    # use max diff to get a conservative estimate on the total days we may request
                    request_calculations['max_day_range'] = int((5000 - request_calculations['static'])/(max_diff))
                    request_calculations['dynamic'] = max_diff


                # and increment day_range, for next test
                else:
                    day_range += 1


            # END OF TEST to calculate requests to Google Earth Engine
            except Exception as e:
                print(e)
                # Cancel further requests
                request_allowed = False




        
        elif d_type == 'Image':
            try:
                res = ee.Image(d_id)
                result_info = res.getInfo()
                meta_info = evaluate_request(result_info)
                request_calculations.update(meta_info)
                break

            except Exception as e:
                print(e)
                print("NOT YET DEVELOPED: ", d_type)
                request_allowed = False


        elif d_type == 'FeatureCollection':
            try:
                res = ee.FeatureCollection(d_id).filterDate(filter_start, filter_end)
                result_info = res.getInfo()
                meta_info = evaluate_request(result_info)
                request_calculations['static'] = meta_info['static']

                # Initialize the dynamic counter difference
                if meta_info['dynamic'] > 0:
                    current_diff = meta_info['dynamic'] - previous_diff
                    if request_calculations['delay'] == 0:
                        request_calculations['delay'] = day_range


                    if current_diff == previous_diff:
                        pattern_established = True
                        # If there is a consistent feature count in result, then update the delay
                        request_calculations['delay'] = day_range
                        request_calculations['dynamic'] = current_diff
                        # calculate the 5000 element limit 
                        request_calculations['max_day_range'] = int((5000 - request_calculations['static'])/current_diff)
                    else:
                        # update previous diff
                        previous_diff = meta_info['dynamic']
                        # store a maximum if the pattern is never established
                        if current_diff >= max_diff:
                            max_diff = current_diff


                # Now if we get to the day range cap, and no pattern exists, use the max diff
                if day_range > day_range_cap and not pattern_established:
                    # cancel any further requests, to save resources + time
                    request_allowed = False
                    # use max diff to get a conservative estimate on the total days we may request
                    request_calculations['max_day_range'] = int((5000 - request_calculations['static'])/(max_diff))
                    request_calculations['dynamic'] = max_diff


                # and increment day_range, for next test
                else:
                    day_range += 1


            # END OF TEST to calculate requests to Google Earth Engine
            except Exception as e:
                print(e)
                # Cancel further requests
                request_allowed = False


        else:
            print("Not Yet Defined Dataset Type: ", dataset)
            request_allowed = False

    return request_calculations







def test_ee_catalog_details():
    analyze_catalog()


def test_calculate_requests():
    catalog = read_catalog()
    # Set the Save File name
    save_fn = 'gee_catalog'
    PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    METADATA_DIR = os.path.join(PLUGIN_DIR, "metadata") 
    filename = os.path.join(METADATA_DIR, save_fn)

    # Test 1: Single ID

    test_id = 'COPERNICUS/S5P/NRTI/L3_NO2'

    for dataset in catalog:
        if dataset['dataset_id'] == test_id:
            save_info = calculate_requests(dataset)
            dataset['request_calculations'] = save_info
        else:
            pass

    # Test 2: each dataset type

    d_types_found = ['ImageCollection', 'Image', 'FeatureCollection']


    # Build the test set
    one_of_each = {}

    for dataset in catalog:
        d_type = dataset['dataset_type']
        d_id = dataset['dataset_id']

        try:
            if one_of_each[d_type]:
                pass
        except KeyError:
            if d_type in d_types_found:
                one_of_each[d_type] = dataset

    for d_type in d_types_found:
        dataset = one_of_each[d_type]
        save_info = calculate_requests(dataset)
        dataset['request_calculations'] = save_info


    cs.save_progressive_json(fn=filename, results=catalog)



    




    



if __name__ == '__main__':
    test_calculate_requests()


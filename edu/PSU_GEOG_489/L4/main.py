import json
import qgis
import qgis.core
from qgis.core import *
import sys, os

from PyQt5.QtWidgets import QApplication

import waterbodies

def load_json(filename):
	with open(filename, encoding="utf8") as f:
		data = json.load(f)
	return data


def filter_elements(elements, filter_on):
	filter_data = {}
	for el in elements:
		if el['type'] == filter_on:
			filter_data[el['id']] = el

	return filter_data


def get_linear(ways, nodes):
	features = {}
	ignore = {}

	for w_id in ways:
		way = ways[w_id]
		try:
			result = waterbodies.LinearWaterbody.detect(way, nodes)
			assert result, "not linear"

			# LINEAR CHECK 1: Stream
			result = waterbodies.Stream.fromOSMWay(way, nodesDict)

			# LINEAR CHECK 2: River
			if not result:
				result = waterbodies.River.fromOSMWay(way, nodesDict)

			# Linear CHECK 3: Canal
			if not result:
				result = waterbodies.Canal.fromOSMWay(way, nodesDict)

			# Linear CHECK 4: Other Linear
			if not result:
				result = waterbodies.OtherLinear.fromOSMWay(way, nodesDict)


			# If no result still, then ignore the Linear waterbody for now
			assert result, "Undefined Linear Waterway"

			# if we have result, press on
			this_feature = result.toQgsFeature()
			features[w_id] = this_feature

		except Exception as e:
			ignore[w_id] = way


	return features, ignore



def get_areal(ways, nodes):
	features = {}
	ignore = {}

	for w_id in ways:
		way = ways[w_id]
		try:
			result = waterbodies.ArealWaterbody.detect(way, nodes)
			assert result, "not areal"

			# AREAL CHECK 1: Lake
			result = waterbodies.Lake.fromOSMWay(way, nodesDict)

			# AREAL CHECK 2: Pond
			if not result:
				result = waterbodies.Pond.fromOSMWay(way, nodesDict)

			# AREAL CHECK 3: Reservoir
			if not result:
				result = waterbodies.Reservoir.fromOSMWay(way, nodesDict)

			# AREAL CHECK 4: Other Areal
			# last check, if there was the "natural" tag but no "water" tag
			# create undefined "natural" areal water type "undefined"
			if not result:
				result = waterbodies.OtherAreal.fromOSMWay(way, nodesDict)

			# if still no result, then ignore this Areal Waterbody
			assert result, "Undefined Areal Waterbody"

			this_feature = result.toQgsFeature()
			features[w_id] = this_feature


		except Exception as e:
			ignore[w_id] = way

	
	
	return features, ignore



def saveLinearFeatures(features, filename, fileFormat):
    """save event list as a WGS84 point vector dataset using qgis under the provided filename and using the given format. It is
       expected that qgis has been initalized before calling this method""" 
    # create layer for polylines in EPSG:4326 and an integer field BUS_ID for storing the bus id for each track
    
    if fileFormat == '.gpkg':
    	fileFormat = "GPKG"

    layer = qgis.core.QgsVectorLayer('LineString?crs=EPSG:4326&field=WAY_ID:integer', 'ways' , 'memory')
    prov = layer.dataProvider()
    
    # create polyline features
    feature_list = list(features.values())
    print(feature_list)
    # for w_id, way_feature in features.items():
	#	  points = [ qgis.core.QgsPointXY(tp.lon,tp.lat) for tp in bus.timepoints ]
    #     feat = qgis.core.QgsFeature()
    #     lineGeometry = qgis.core.QgsGeometry.fromPolylineXY(points)
    #     feat.setGeometry(lineGeometry)
    #     feat.setAttributes([int(busId)])
    #     features.append(feat)
    
    # add features to layer and write layer to file
    prov.addFeatures(feature_list)
    qgis.core.QgsVectorFileWriter.writeAsVectorFormat(layer, filename, "utf-8", layer.crs(), fileFormat)


def saveArealFeatures(features, filename, fileFormat):
	
	if fileFormat == '.gpkg':
		fileFormat = "GPKG"

	layer = qgis.core.QgsVectorLayer('Polygon?crs=EPSG:4326&field=WAY_ID:integer', 'ways', 'memory')
	prov = layer.dataProvider()

	feature_list = list(features.values())
	print(feature_list)

	prov.addFeatures(feature_list)
	qgis.core.QgsVectorFileWriter.writeAsVectorFormat(layer, filename, "utf-8", layer.crs(), fileFormat)




if __name__ == '__main__':

	inputJSONFile = os.path.join(os.getcwd(), "input_data\\assignment4_data.json")
	data = load_json(inputJSONFile)

	# separate json file into Node lat/lon lookup with ID 
	# and then separate all ways for further classification
	nodesDict = filter_elements(data['elements'], 'node')
	waysDict = filter_elements(data['elements'], 'way')

	# in case we want to expand our tag coverage
	all_way_tags = []

	# There are many other waterbody tags in this .json file that we will not
	# use as classifiers for the assignment (i.e. dam, riverbank, ditch, derelict_canal ...)
	ignore_waterbodies = []

	## instantiate qgis
	app = QApplication(sys.argv)
	qgis_prefix = os.getenv("QGIS_PREFIX_PATH")
	qgs = qgis.core.QgsApplication([], False)
	qgs.initQgis()

	# first check for linear 'waterway' waterbodies
	linear_features, remainingWaysDict = get_linear(waysDict, nodesDict)

	# then check for areal 'natural' waterbodies
	areal_features, ignoreWays = get_areal(remainingWaysDict, nodesDict)

	file_format = '.gpkg'
	file_path = os.path.join(os.getcwd(), "results")
	# get filename for linear features
	linear_fn = 'linear_features' + file_format

	linear_fn = os.path.join(file_path, linear_fn)
	# save the linear features
	saveLinearFeatures(linear_features, linear_fn, file_format)

	areal_fn = 'areal_features' + file_format
	areal_fn = os.path.join(file_path, areal_fn)
	saveArealFeatures(areal_features, areal_fn, file_format)






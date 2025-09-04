# -*- coding: utf-8 -*-
"""
Created on Wed Jun 10 08:15:45 2020

@author: blcrosbie
"""
import sys
import math
import time
import csv
import os

# Step 1: Main Window
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction, QStyle
# Step 2: Datatypes
from PyQt5.QtGui import QStandardItemModel, QStandardItem,  QDoubleValidator, QIntValidator
# Step 3: Map
import matplotlib.pyplot as plt
import numpy as np
import shapefile
from matplotlib.backends.qt_compat import QtCore, QtWidgets, is_pyqt5
if is_pyqt5():
    from matplotlib.backends.backend_qt5agg import (
            FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
else:
    from matplotlib.backends.backend_qt4agg import(
            FigureCanvas, NavigationToolbar2QT as NavigationToolbar)
from matplotlib.figure import Figure

# Step 4: New File Dialog
from PyQt5.QtWidgets import QFileDialog, QDialog

# For auto Completer
from PyQt5.QtWidgets import QCompleter

# For Results List Buttons
from PyQt5.Qt import Qt

# For Results List
from PyQt5.QtCore import QVariant


# Step N: file handling in menu bar
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QWidget, QGridLayout, QLabel, QMenu

import gui_basic_main 
import gui_new_shapefile




def selectShapefile():    
    """open file dialog to select exising shapefile and if accepted, update GUI accordingly"""
    fileName, _ = QFileDialog.getOpenFileName(mainWindow,"Select shapefile", "","Shapefile (*.shp)")
    if fileName:
        ui.shapeSaveFileNameLE.setText(fileName)
        #updateShapeFieldSaveOption()
        return fileName
    
def importShapefile():    
    """open file dialog to select exising shapefile and if accepted, update GUI accordingly"""
    fileName, _ = QFileDialog.getOpenFileName(mainWindow,"Select shapefile", "","Shapefile (*.shp)")
                    
    #if fileName:
        ## meant for matplot lib visual, but nothing seems to work right in Qt making visuals
#        shp = shapefile.Reader(fileName)
#        for shape in shp.shapeRecords():
#            x = [i[0] for i in shape.shape.points[:]]
#            y = [i[1] for i in shape.shape.points[:]]
        
                
    return fileName


def getCountries():
    fileName = importShapefile()
    if fileName:
        global country_shapes 
        for row in arcpy.da.SearchCursor(fileName, ["NAME", "SHAPE@"]):
            country_bounds = []
            for points in row[1]:
                ndx = 0
                for pnt in points:
                    this_row = {"index": ndx, "x": pnt.X, "y": pnt.Y}
                    ndx += 1
                    country_bounds.append(this_row)
            country_shapes.append({'NAME':row[0], 'SHAPE':country_bounds})
    
        # now this should work but just in case
    try:
        ui.countrySelectCB.clear()
        ui.countrySelectCB.addItem('')
        for country in country_shapes:
            ui.countrySelectCB.addItem(country['NAME'])

    except Exception as e:
         QMessageBox.information(mainWindow, 'Operation failed', 'Obtaining Shape Field list from  ArcGIS failed with '+ str(e.__class__) + ': ' + str(e), QMessageBox.Ok )

    

#    apply_filter = ui.ShapeApplyFilter.isChecked()
#    
#    if apply_filter:
#        ui.statusbar.showMessage('Filtering Results...')
#        search_field = ui.ShapeFieldFilter.currentText()
#        search_value = ui.ShapeValueFilter.text()
#        
#        limit = ui.ShapeLimitFilter.text()
    
    return



def getPOIs():
    fileName = importShapefile()
    if fileName:
    # OSM_shape
        allowed_filters = ['amenity', 'cuisine', 'denominati', 'leisure', 'place', 'religion', 'shop']
        search_shape = ["SHAPE@"]  
        all_fields = arcpy.ListFields(fileName)
        all_field_names = [field.name for field in all_fields]
        search_shape += all_field_names
        
        global OSM_points
        ndx = 0
        for row in arcpy.da.SearchCursor(fileName, search_shape):
            for pnt in row[0]:
                this_row = {"index": ndx, "x": pnt.X, "y": pnt.Y, "z": pnt.Z, "m": pnt.M}
            ndx += 1
            
            for i in range(1, len(all_field_names)+1):
                field = all_field_names[i-1]
                this_row[field] = row[i]
            
            OSM_points.append(this_row)         
            
    # make filters
    try:
        ui.filterPoiCB.clear()
        ui.filterPoiLE.clear()
        ui.filterPoiCB.addItem('')
        for field in allowed_filters:
            ui.filterPoiCB.addItem(field)
                   
        
#        ui.filterPoiLE.setCompleter(list(arcValidOSMFields.values()))
    except Exception as e:
         QMessageBox.information(mainWindow, 'Operation failed', 'Obtaining OSM Field list from  ArcGIS failed with '+ str(e.__class__) + ': ' + str(e), QMessageBox.Ok )
        
        
    return
  

def runChecks():
    global OSM_points
    global country_shapes
    
    
    try:
        if country_shapes == []:
            assert 1 == 0
    except Exception:
        QMessageBox.information(mainWindow, 'Operation failed', 'No Country Shapes are Imported', QMessageBox.Ok )
        getCountries()        
    
    try:
        if OSM_points == []:
            assert 1 == 0
    except Exception:
        QMessageBox.information(mainWindow, 'Operation failed', 'No POIs are Imported', QMessageBox.Ok )
        getPOIs()
    
        
    return
    


def updateEntryOptions():
    try:
        limit_list = [1, 5, 10, 25, 50, 100, 1000]
        ui.customLimitCB.addItem('')
        for i in limit_list:
            ui.customLimitCB.addItem(str(i))
        
        if ui.filterPoiCB.currentText() != '':
            field = ui.filterPoiCB.currentText()
            global OSM_points
            all_options = []
            for row in OSM_points:
                if row[field] not in all_options:
                    all_options.append(row[field])
            
            completer = QCompleter(all_options, ui.filterPoiLE)    
            ui.filterPoiLE.setCompleter(completer)
    except Exception as e:
        QMessageBox.information(mainWindow, 'Operation failed', 'Obtaining OSM Field list from  ArcGIS failed with '+ str(e.__class__) + ': ' + str(e), QMessageBox.Ok )
        


def selectCountry():
    runChecks()
    country = ui.countrySelectCB.currentText()
    global filtered_country
    global filtered_OSM
    if country == '':
        QMessageBox.information(mainWindow, 'Operation failed', 'No Specified Filter on Country ', QMessageBox.Ok )
        filtered_country = []
        
    else:
        global country_shapes
        Qstart = time.time()
        filtered_OSM = []
        filtered_country = [shp for shp in country_shapes if shp["NAME"] == country]
        filterCountry()
        resultsListUpdate()
        Qend = time.time()
        ui.statusbar.showMessage("Filtered Results: {0}\t\t\t\t Query Time: {1} seconds".format(len(filtered_OSM), round(Qend-Qstart, 3)))
    return


def filterCountry():
    global filtered_country
    global OSM_points
    global filtered_OSM
    
    shape_coordinates = []
    sub_filtered_OSM = []
    # Start with filtering on the Selected Country
    if filtered_country != []:
        for coord_pair in filtered_country[0]['SHAPE']:
            shape_coordinates.append((coord_pair['x'], coord_pair['y']))

        # Iterate through OSM to filter down OSM list
        
        if len(filtered_OSM) == 0:
            for poi in OSM_points:
                lat = poi['y']
                lon = poi['x']
                if is_point_in_path(lon, lat, shape_coordinates):
                    filtered_OSM.append(poi)
        else:
            for poi in filtered_OSM:
                lat = poi['y']
                lon = poi['x']
                if is_point_in_path(lon, lat, shape_coordinates):
                    sub_filtered_OSM.append(poi)
                    filtered_OSM = sub_filtered_OSM
                    
                
    return


def customDistance():
    global filtered_country
    global OSM_points
    global filtered_OSM
    
    
    try:
        customLat = float(ui.customLatitudeLE.text())
        customLon = float(ui.customLongitudeLE.text())
        radius = float(ui.customRadiusLE.text())
        radius = float(ui.customRadiusLE.text())
        units = 'km' if ui.radiusUnitKM.isChecked() else 'mi'
    
    except:
         QMessageBox.information(mainWindow, 'Operation failed', 'Custom Search Not Set ', QMessageBox.Ok )
        
        
    
    shape_coordinates = []
    if filtered_country != [] and filtered_OSM != []:
        for coord_pair in filtered_country[0]['SHAPE']:
            shape_coordinates.append((coord_pair['x'], coord_pair['y']))
        try:
            assert is_point_in_path(customLon, customLat, shape_coordinates)
        except Exception as e:
            QMessageBox.information(mainWindow, 'Operation failed', 'Custom Point not in Country, Reset Filtered POIs '+ str(e.__class__) + ': ' + str(e), QMessageBox.Ok )    
            filtered_OSM = []
    
     # do custom radius search
    Qstart = time.time()           
            
    # continue filtering down FROM country
    custom_radius_shape = findAllPOIinRadius(customLat, customLon, filtered_OSM, radius, units)
    custom_coordinates = []
    sub_filtered_OSM = []
    for coord in custom_radius_shape:
        custom_coordinates.append((coord['x'], coord['y']))
        
    for poi in OSM_points:
        lat = poi['y']
        lon = poi['x']
        if is_point_in_path(lon, lat, custom_coordinates):
            sub_filtered_OSM.append(poi)
            
    filtered_OSM = sub_filtered_OSM
    
    resultsListUpdate()
    
    Qend = time.time()
    ui.statusbar.showMessage("Filtered Results: {0} Query Time: {1} s".format(len(filtered_OSM), (Qend-Qstart)))
    
    return
    

    
def applyPoiFilter():
    runChecks()
    attribute = ui.filterPoiCB.currentText()
    value = ui.filterPoiLE.text()
    
    global filtered_OSM
    global OSM_points
    if attribute != '' and value != '': 
        Qstart = time.time()
        if len(filtered_OSM) == 0:  
            filtered_OSM = [poi for poi in OSM_points if poi[attribute] == value]
        else:
            sub_filtered_OSM = [poi for poi in filtered_OSM if poi[attribute] == value]
            filtered_OSM = []
            filtered_OSM = sub_filtered_OSM
        
        resultsListUpdate()
        Qend = time.time()
        ui.statusbar.showMessage("Filtered Results: {0}\t\t\t\t Query Time: {1} seconds".format(len(filtered_OSM), round(Qend-Qstart, 3)))


    else:
        QMessageBox.information(mainWindow, 'Operation failed', 'No Specified Filter on Attribute or Value in POI Filter ', QMessageBox.Ok )
    
    return

def setResultLimits():
    limit_list = [1, 5, 10, 25, 50, 100, 1000]
    ui.customLimitCB.addItem('')
    for i in limit_list:
        ui.customLimitCB.addItem(i)


def queryAll():
    runChecks()
    global filtered_OSM
    filtered_OSM = []
    Qstart = time.time()
    
    if ui.countrySelectCB.currentText() != '':
        selectCountry()
    
    if ui.filterPoiLE.text() != '':
        applyPoiFilter()
    
    if ui.customRadiusLE.text() != '' and ui.customLatitudeLE.text() != '':
        customDistance()
    
    if filtered_OSM == []:
        ui.statusbar.showMessage("No Results Found with Filter, Showing ALL")
        filtered_OSM = [poi for poi in OSM_points]
        
 
    resultsListUpdate()
    
    Qend = time.time()
    ui.statusbar.showMessage("Results: {0}\t\t\t\t Query Time: {1} seconds".format(len(filtered_OSM), round(Qend-Qstart, 3)))

def resultsListUpdate():
    
    """populate list view with checkable entries created from result list in r"""

    global country_shapes
    global filtered_country
    
    global OSM_points
    global filtered_OSM
    
    if ui.customLimitCB.currentText() != '':
        limit = min(int(ui.customLimitCB.currentText()), len(filtered_OSM))
        sub_OSM = filtered_OSM[0:limit]
        filtered_OSM = sub_OSM
    
#    global results    

    m = QStandardItemModel()
    for item in filtered_OSM:
        item = QStandardItem(str(item['name']) + ' ('+str(item['y']) + ',' + str(item['x']) + ')')
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setData(QVariant(Qt.Checked), Qt.CheckStateRole)
        m.appendRow(item)
    ui.resultsList.setModel(m)
        

    
    return


#################### List Results Functions ##################################
# list view selection functions, No adjustment to buttons, these will trigger

def selectAll():
    """select all items of the list view widget"""
    for i in range(ui.resultsList.model().rowCount()):
        ui.resultsList.model().item(i).setCheckState(Qt.Checked) 

def clearSelection():
    """deselect all items of the list view widget"""
    for i in range(ui.resultsList.model().rowCount()):
        ui.resultsList.model().item(i).setCheckState(Qt.Unchecked) 
        
def invertSelection():
    """invert current selection of the list view widget"""
    for i in range(ui.resultsList.model().rowCount()):
        currentValue = ui.resultsList.model().item(i).checkState()
        ui.resultsList.model().item(i).setCheckState(Qt.Checked if currentValue == Qt.Unchecked else Qt.Unchecked)


def resetForm():
    
    confirm = QMessageBox()
    confirm.setIcon(QMessageBox.Question)
    confirm.setText("RESET FORM, Are you sure?")
    confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    confirm.setDefaultButton(QMessageBox.No)
    buttonYes = confirm.button(QMessageBox.Yes)
    buttonNo = confirm.button(QMessageBox.No)
    confirm.exec_()
    
    if confirm.clickedButton() != buttonYes:
        return
    
    global filtered_country
    global filtered_OSM
    global results
    
    filtered_country = []
    filtered_OSM = []
    results = []
    
    ui.countrySelectCB.clear()
    ui.filterPoiCB.clear()
    ui.customLimitCB.clear()
    ui.shapeSaveFieldCB.clear()
    
    
    ui.customLatitudeLE.clear()
    ui.customLongitudeLE.clear()
    ui.shapeSaveFileNameLE.clear()
    ui.customRadiusLE.clear()
    
    ui.resultsList.clear()
    
    

###############################################################################
# Possibly add the functions Below to external .py file
 

###############################################################################
# Odd Even Algorithm
###############################################################################

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


###############################################################################
# Simple Import Check
###############################################################################
def importArcpyIfAvailable():
    """test whether arcpy is available for import"""
    try: # test whether we can import arcpy
        import arcpy
    except:
        return False
    return True

###############################################################################



def saveFile():
    """run one of the different functions for adding features based on which tab is currently open"""
    activeTab = ui.saveResultsTab.currentWidget()
    saveFileHandler[activeTab]() # call a function from the dictionary in addFeatureHandler

def saveShapefile():
    """add selected features from list view to shapefile"""
    fileName = selectShapefile()
    ui.shapeSaveFileNameLE.setText(fileName)
    fieldName = ui.filterPoiCB.currentText()
#    fileName = ui.ShapeValueFilter.text()
    ui.statusbar.showMessage('Adding entities has started... please wait!')
    
    global filtered_OSM
    result = filtered_OSM
    try:
        with arcpy.da.InsertCursor(fileName, ("SHAPE@",fieldName)) as cursor: 
           for i in range(ui.resultsList.model().rowCount()): # go through all items in list view
               if ui.resultsList.model().item(i).checkState() == Qt.Checked:
                   point = arcpy.Point( result[i]['x'], result[i]['y'])
                   cursor.insertRow( (point, result[i]['name'][:30]) ) # name shortened to 30 chars      
                   
        ui.statusbar.showMessage('Adding entities has finished.')
    except Exception as e:
        QMessageBox.information(mainWindow, 'Operation failed', 'Writing to shapefile failed with '+ str(e.__class__) + ': ' + str(e), QMessageBox.Ok )
        ui.statusbar.clearMessage()


def selectCSVdir():    
    """open file dialog to select exising csv/text file and if accepted, update GUI accordingly"""
    fileName, _ = QFileDialog.getOpenFileName(mainWindow,"Select CSV filepath", "","(*.*)")
   
    return os.path.dirname(fileName)

def saveCSV():
    """add selected features from list view to csv/text file"""

    fn = ui.csvSaveFileNameLE.text()
    if not fn:
        QMessageBox.information(mainWindow, 'Operation failed', 'Please Name New CSV')
    else:
        fn = fn + '.csv'
        
        filepath = selectCSVdir()
        fileName = os.path.join(filepath, fn)
        ui.statusbar.showMessage('Adding entities has started... please wait!')
    
    
    
        global flitered_OSM
        result = filtered_OSM
        
        try:
            with open(fileName, 'a', newline='') as csvfile:
                 csvWriter = csv.writer(csvfile)
                 for i in range(ui.resultsList.model().rowCount()): # go through all items in list view
                    if ui.resultsList.model().item(i).checkState() == Qt.Checked:
                         csvWriter.writerow( [ result[i]['name'], result[i]['x'], result[i]['y'] ])   
                         
            ui.statusbar.showMessage('Adding entities has finished.')
        except Exception as e:
            QMessageBox.information(mainWindow, 'Operation failed', 'Writing to csv file failed with '+ str(e.__class__) + ': ' + str(e), QMessageBox.Ok )
            ui.statusbar.clearMessage()


###############################################################################
# Specific Earth GEO Math functions
###############################################################################    

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
    

def findAllPOIinRadius(center_lat, center_lon, all_poi_list, radius=0, units='km'):
    buffer_shape_poi_list = createPolygonBuffer(center_lat, center_lon, radius, units, sides=6)   
    buffer_tuples = [(poi['longitude'], poi['latitude']) for poi in buffer_shape_poi_list]
    
    filtered_poi = []
    for poi in all_poi_list:
        if is_point_in_path(poi['x'], poi['y'], buffer_tuples):
            filtered_poi.append(poi)
            
    return filtered_poi
###############################################################################
###############################################################################

if __name__ == '__main__':

    #=====================================
    # 1. instantiate QApplication, QMainWindow, and ui class
    #=====================================
    app = QApplication(sys.argv)
    mainWindow = QMainWindow()
    ui = gui_basic_main.Ui_MainWindow()
    ui.setupUi(mainWindow)
    
    #=====================================
    # 2. Set Valid datatypes for Line Edit Numeric Values
    #=====================================
    ui.customLatitudeLE.setValidator(QDoubleValidator(-90, -90, 9))
    ui.customLongitudeLE.setValidator(QDoubleValidator(-180, 180, 9))
    ui.customRadiusLE.setValidator(QDoubleValidator(0, 10000000, 9))

    #=====================================
    # 3. Try to set up Map Widget since QT design does not have a Map Widget
    #=====================================
    layout = QtWidgets.QVBoxLayout(ui.resultsMapWidget)
    static_canvas = FigureCanvas(Figure(figsize=(5, 3)))
    layout.addWidget(static_canvas)
    ui._static_ax = static_canvas.figure.subplots()
#    t = np.linspace(0, 10, 501)
#    ui._static_ax.plot(t, np.tan(t), ".")
    

 
    
    #=====================================
    # 4. set up Create New Shapefile dialog
    #=====================================
    createShapefileDialog = QDialog(mainWindow)
    createShapefileDialog_ui = gui_new_shapefile.Ui_Dialog()
    createShapefileDialog_ui.setupUi(createShapefileDialog)
    
#    mapWV.setHtml(core_functions.webMapFromDictionaryList([]))
#    ui.resultsAndMapHBL.addWidget(mapWV)
#    mapWV.setFixedSize(300,200)
#    mapWV.setSizePolicy(QSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed))
    
    #=====================================
    # 5. connect signlas
    #=====================================
#    lons = None
#    lats = None
    ui.importCountryBTN.clicked.connect(getCountries)
#    if lons is not None and lats is not None:
#        ui._static_ax.plot(lons, lats)
#        print(lons)    
    ui.importPoiBTN.clicked.connect(getPOIs)
    
    #=====================================
    # GUI event handler and related functions
    #=====================================
    ui.filterPoiCB.activated.connect(updateEntryOptions)
    ui.countrySelectBTN.clicked.connect(selectCountry)
    ui.filterPoiApplyBTN.clicked.connect(applyPoiFilter)
    ui.searchBTN.clicked.connect(queryAll)
    
    ui.clearAllBTN.clicked.connect(clearSelection)
    ui.selectAllBTN.clicked.connect(selectAll)
    ui.invertAllBTN.clicked.connect(invertSelection)
    
    ui.csvOpenFilePathTB.clicked.connect(selectCSVdir)
    ui.csvSaveBTN.clicked.connect(saveCSV)
    
    ui.shapeOpenFilePathTB.clicked.connect(selectShapefile)
    ui.shapeSaveBTN.clicked.connect(saveShapefile)
    
    ui.RESET.clicked.connect(resetForm)
    #=====================================
    # create app and main window + dialog GUI
    #=====================================
    
    saveFileHandler = { ui.saveShapeTab: saveShapefile, ui.saveCSVTab: saveCSV }
    #=====================================
    # initialize global variaibes
    #=====================================
    country_shapes = []
    OSM_points = []
    
    filtered_country = []
    filtered_OSM = []
    
    results = []
    #=====================================
    # test availablitiy and if run as script tool
    #=====================================
   
    
    
    arcpyAvailable = importArcpyIfAvailable()
    if not arcpyAvailable:
        ui.statusbar.showMessage('arcpy not available. Adding to shapefiles and layers has been disabled.')
    
    else:
        import arcpy
    
    #=====================================
    # run app
    #=====================================
    mainWindow.show()
    sys.exit(app.exec_())
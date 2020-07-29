
import qgis
import qgis.core

# ## instantiate qgis
# app = QApplication(sys.argv)
# qgis_prefix = os.getenv("QGIS_PREFIX_PATH")
# qgs = qgis.core.QgsApplication([], False)
# qgs.initQgis()

# abstract class Waterbody is the root class of our hierarchy 
class Waterbody():
    
    # constructor (can be derived by subclasses)
    def __init__(self, name, geometry):
        self.name = name            # instance variable for storing the name of the watebrbody
        self.geometry = geometry    # instance variable for storing the a QgsGeometry object with the geometry for this waterbody
        
        # my additions to the base class attributes, these should be simple to understand and use 
        # for later file export methods
        self.WAY_ID = None
        self.tag = None

    # all waterbodies need a better print display
    def __str__(self):
        return "{}".format(type(self))

    # abstract static class function for creating a waterbody object if the given way satisfies
    # the required conditions; needs to be overridden by instantiable subclasses 
    def fromOSMWay(way, allNodes):     
        pass
    
    # abstract method for creating QgsFeature object for this waterbody;
    # needs to be overridden by instantiable subclasses 
    def toQgsFeature(self):
        pass

    def getName(way):
        if 'name' in way['tags']:
            name = way['tags']['name']
        else:
            name = 'unknown'
        return name


# abstract class LinearWaterBody is derived from class Waterbody
class LinearWaterbody(Waterbody):
    
    # constructor (can be invoked by derived classes and takes care of the length computation)
    def __init__(self, name, geometry):
        super(LinearWaterbody, self).__init__(name, geometry)
        
        # calculate length of this linear waterbody
        qda = qgis.core.QgsDistanceArea() 
        qda.setEllipsoid('WGS84')
        length = qda.measureLength(geometry)

        # instance variable for storing the length of this linear waterbody
        self.length = qda.convertLengthMeasurement(length, qgis.core.QgsUnitTypes.DistanceMeters) 

        # similar to the bus tracker example we will store all Linear Features in a private attribute
        self._allLinearFeatures = {}


    # add a definition of the method __str__(self) that returns a string describing the object including its
    # name, type, and length, e.g. Stream Rapid Run (length: 372.01922201444535m) 
    def __str__(self):
        pretty_printout = "{classname} {name} (length: {dimension}m)".format(
                            classname=self.__class__.__name__,
                            name=self.name,
                            dimension=self.length)
        return pretty_printout

    # additional auxiliary methods or class functions to this class definition

    def lineFromWay(way, allNodes):
        points = []
        for nid in way['nodes']:
            node = allNodes[nid]
            p = qgis.core.QgsPointXY(node['lon'], node['lat'])
            points.append(p)
        geoline = qgis.core.QgsGeometry.fromPolylineXY(points)

        return geoline

    # static method to detect if way is linear using 'waterway' tag
    def detect(way, allNodes):
        if 'waterway' in way['tags']:
            name = Waterbody.getName(way)
            geometry = LinearWaterbody.lineFromWay(way, allNodes)
            return LinearWaterbody(name, geometry)
        else:
            return None


    # toQgsFeature is going to be basically the same between all Linear Waterbodies
    # we can also save all Waterbodies into a single GeoPackage
    # and break it down to each subclass of Linear Waterbody by returning the Qgs Feature
    # to the sub-subclass method where this is called.
    def toQgsFeature(self):
        feat = qgis.core.QgsFeature()
        feat.setGeometry(self.geometry)
        feat.setAttributes([self.name, self.tag, self.length])
        # first method, saving all Linear Features in one place
        self._allLinearFeatures[self.WAY_ID] = feat
        # return so that we can save all sub-subclass features in one place
        return feat

    # Work In Progress, save based on WAY_ID
    def saveLinearFeatures(self, filename, fileformat):
        layer = qgis.core.QgsVectorLayer('LineString?crs=EPSG:4326&field=WAY_ID:integer', 'ways' , 'memory')
        prov = layer.dataProvider()


# abstract class ArealWaterbody is derived from class Waterbody
class ArealWaterbody(Waterbody):

    # constructor (can be invoked by derived classes and takes care of the area computation)
    def __init__(self, name, geometry):
        super(ArealWaterbody, self).__init__(name, geometry)

        # calculate area of this areal waterbody
        qda = qgis.core.QgsDistanceArea() 
        qda.setEllipsoid('WGS84')
        area = qda.measureArea(geometry)

        # instance variable for storing the length of this areal waterbody
        self.area = qda.convertAreaMeasurement(area, qgis.core.QgsUnitTypes.AreaSquareMeters)

        # similar to the bus tracker example we will store all Linear Features in a private attribute
        self._allArealFeatures = {}
    # ... you may want to add additional auxiliary methods or class functions to this class definition
    
    def __str__(self):
        pretty_printout = "{classname} {name} (area: {dimension}m2)".format(
                            classname=self.__class__.__name__,
                            name=self.name,
                            dimension=self.area)
        return pretty_printout

    # Using WKT method because fromPolygonXY does not seem to work
    def areaFromWay(way, allNodes):
        points = []
        for nid in way['nodes']:
            node = allNodes[nid]
            #p = qgis.core.QgsPointXY(node['lon'], node['lat'])
            p = "{} {}".format(node['lon'], node['lat'])
            points.append(p)

        wkt = 'Polygon ((' + ','.join(points) + '))'
        geopoly = qgis.core.QgsGeometry.fromWkt(wkt)
        return geopoly

    # TypeError on this function, fromPolygonXY not working...
    def getPolygon(way, allNodes):
        points = []
        for nid in way['nodes']:
            node = allNodes[nid]
            p = qgis.core.QgsPointXY(node['lon'], node['lat'])
            points.append(p)
        geopoly = qgis.core.QgsGeometry.fromPolygonXY([points])

        return geopoly

    # this method will detect if the Waterbody is Natural, from this point on
    # we can dig deeper to find if the Natural Waterbody has an attribute "water" to
    # tell us the correct Sub-subclass of Areal Waterbody
    def detect(way, allNodes):
        if 'natural' in way['tags']:
            name = Waterbody.getName(way)
            # geometry = ArealWaterbody.areaFromWay(way, allNodes)
            geometry = ArealWaterbody.getPolygon(way, allNodes)
            return ArealWaterbody(name, geometry)
        else:
            return None
    
    def toQgsFeature(self):
        feat = qgis.core.QgsFeature()
        feat.setGeometry(self.geometry)
        feat.setAttributes([self.name, self.tag, self.area])
        # first method, saving all Linear Features in one place
        self._allArealFeatures[self.WAY_ID] = feat
        # return so that we can save all sub-subclass features in one place
        return feat


# NOW DEFINE THE SUB-SUBCLASSES of WATERBODIES
#LINEAR SUBCLASSES: Stream, River, Canal, OtherLinear

# class Stream is derived from class LinearWaterBody and can be instantiated
class Stream(LinearWaterbody):
    
    # constructor (calls LinearWaterbody constructor to initialize name, geometry, and length instance variables)
    def __init__(self, name, geometry):
        super(Stream,self).__init__(name, geometry)
        self._allStreams = {}

    # override the fromOSMWay(...) static class function
    def fromOSMWay(way, allNodes):
        result = LinearWaterbody.detect(way, allNodes)
        if result:
            if 'stream' == way['tags']['waterway']:
                new_result = Stream(result.name, result.geometry)
                new_result.WAY_ID = way['id'] 
                new_result.tag = way['tags']['waterway']
                return new_result

        else:
            return None

    # override the toQgsFeature(...) method
    def toQgsFeature(self):
        # not sure what the point of override is at the sub-subclass level, this should be
        feat = LinearWaterbody.toQgsFeature(self)
        self._allStreams[self.WAY_ID] = feat
        return feat
    # Don't forget to add a definition of the method __str__(self) that returns a string describing the object including its
    # name, type, and length, e.g. Stream Rapid Run (length: 372.01922201444535m)  
    # def __str__(self):
    #     pass


# class River is derived from class LinearWaterBody and can be instantiated
class River(LinearWaterbody):   
    # constructor (calls LinearWaterbody constructor to initialize name, geometry, and length instance variables)
    def __init__(self, name, geometry):
        super(River,self).__init__(name, geometry)
        self._allRivers = {}

    # override the fromOSMWay(...) static class function
    def fromOSMWay(way, allNodes):
        result = LinearWaterbody.detect(way, allNodes)
        if result:
            if 'river' == way['tags']['waterway']:
                new_result = River(result.name, result.geometry)
                new_result.WAY_ID = way['id']
                new_result.tag = way['tags']['waterway']
                return new_result

        else:
            return None

    # override the toQgsFeature(...) method (somewhat override)
    def toQgsFeature(self):
        feat = LinearWaterbody.toQgsFeature(self)
        self._allRivers[self.WAY_ID] = feat
        return feat

# class Stream is derived from class LinearWaterBody and can be instantiated
class Canal(LinearWaterbody):
    
    # constructor (calls LinearWaterbody constructor to initialize name, geometry, and length instance variables)
    def __init__(self, name, geometry):
        super(Canal,self).__init__(name, geometry)
        self._allCanals = {}

    # override the fromOSMWay(...) static class function
    def fromOSMWay(way, allNodes):
        result = LinearWaterbody.detect(way, allNodes)
        if result:
            if 'canal' == way['tags']['waterway']:
                new_result = Canal(result.name, result.geometry)
                new_result.WAY_ID = way['id']
                new_result.tag = way['tags']['waterway']
                return new_result

        else:
            return None

    # override the toQgsFeature(...) method
    def toQgsFeature(self):
        feat = LinearWaterbody.toQgsFeature(self)
        self._allCanals[self.WAY_ID] = feat
        return feat


# class Stream is derived from class LinearWaterBody and can be instantiated
class OtherLinear(LinearWaterbody):
    
    # constructor (calls LinearWaterbody constructor to initialize name, geometry, and length instance variables)
    def __init__(self, name, geometry):
        super(OtherLinear,self).__init__(name, geometry)
        self._allOtherLinear = {}

    # override the fromOSMWay(...) static class function
    def fromOSMWay(way, allNodes):
        result = LinearWaterbody.detect(way, allNodes)
        if result:
            new_result = OtherLinear(result.name, result.geometry)
            new_result.WAY_ID = way['id']
            new_result.tag = 'OtherLinear'
            return new_result

        else:
            return None

    # override the toQgsFeature(...) method
    def toQgsFeature(self):
        feat = LinearWaterbody.toQgsFeature(self)
        self._allOtherLinear[self.WAY_ID] = feat
        return feat


########################## AREAL ####################
# NOW DEFINE THE SUB-SUBCLASSES FOR AREAL WATERBODIES
# AREAL SUB-SUBCLASSES: Lake, Pond, Reservoir, OtherAreal

class Lake(ArealWaterbody):
    # constructor (calls ArealWaterbody constructor to initialize name, geometry, and area instance variables)
    def __init__(self, name, geometry):
        super(Lake,self).__init__(name, geometry)
        self._allLakes = {}

    # override the fromOSMWay(...) static class function
    def fromOSMWay(way, allNodes):
        result = ArealWaterbody.detect(way, allNodes)
        if result and 'water' in way['tags']:
            if 'lake' == way['tags']['water']:
                new_result = Lake(result.name, result.geometry)
                new_result.WAY_ID = way['id']
                new_result.tag = way['tags']['water']
                return new_result

        else:
            return None

    # override the toQgsFeature(...) method
    def toQgsFeature(self):
        feat = ArealWaterbody.toQgsFeature(self)
        self._allLakes[self.WAY_ID] = feat
        return feat



class Pond(ArealWaterbody):
    
    # constructor (calls LinearWaterbody constructor to initialize name, geometry, and length instance variables)
    def __init__(self, name, geometry):
        super(Pond,self).__init__(name, geometry)
        self._allPonds = {}

    # override the fromOSMWay(...) static class function
    def fromOSMWay(way, allNodes):
        result = ArealWaterbody.detect(way, allNodes)
        if result and 'water' in way['tags']:
            if 'pond' == way['tags']['water']:
                new_result = Pond(result.name, result.geometry)
                new_result.WAY_ID = way['id']
                new_result.tag = way['tags']['water']
                return new_result

        else:
            return None

    # override the toQgsFeature(...) method
    def toQgsFeature(self):
        feat = ArealWaterbody.toQgsFeature(self)
        self._allPonds[self.WAY_ID] = feat
        return feat



class Reservoir(ArealWaterbody):
    # constructor (calls LinearWaterbody constructor to initialize name, geometry, and length instance variables)
    def __init__(self, name, geometry):
        super(Reservoir,self).__init__(name, geometry)
        self._allReservoirs = {}

    # override the fromOSMWay(...) static class function
    def fromOSMWay(way, allNodes):  
        result = ArealWaterbody.detect(way, allNodes)
        if result and 'water' in way['tags']:
            if 'reservoir' == way['tags']['water']:
                new_result = Reservoir(result.name, result.geometry)
                new_result.WAY_ID = way['id']
                new_result.tag = way['tags']['water']
                return new_result

        else:
            return None

    # override the toQgsFeature(...) method
    def toQgsFeature(self):
        feat = ArealWaterbody.toQgsFeature(self)
        self._allReservoirs[self.WAY_ID] = feat
        return feat



class OtherAreal(ArealWaterbody):
    # constructor (calls LinearWaterbody constructor to initialize name, geometry, and length instance variables)
    def __init__(self, name, geometry):
        super(OtherAreal,self).__init__(name, geometry)
        self._allOtherAreal = {}

    # override the fromOSMWay(...) static class function
    def fromOSMWay(way, allNodes):
        result = ArealWaterbody.detect(way, allNodes)
        # this time, we allow the script to run even if "water" is not included in the tag
        # but natural is included, this will allow for unnamed Areal Waterbodies to go through
        if result:
            new_result = OtherAreal(result.name, result.geometry)
            new_result.WAY_ID = way['id']
            new_result.tag = 'OtherAreal'
            return new_result

        else:
            return None

    # override the toQgsFeature(...) method
    def toQgsFeature(self):
        feat = ArealWaterbody.toQgsFeature(self)
        self._allOtherAreal[self.WAY_ID] = feat
        return feat


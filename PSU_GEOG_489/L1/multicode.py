import os, sys
import arcpy
 
def worker(clipper, tobeclipped, field, oid, output_PATH): 
    """  
       This is the function that gets called and does the work of clipping the input feature class to one of the polygons from the clipper feature class. 
       Note that this function does not try to write to arcpy.AddMessage() as nothing is ever displayed.  If the clip succeeds then it returns TRUE else FALSE.  
    """
    try:   
        # Create a layer with only the polygon with ID oid. Each clipper layer needs a unique name, so we include oid in the layer name.
        query = '"' + field +'" = ' + str(oid)
        # what is the last directory of clipper
    #    shape_name = os.path.basename(clipper)
    #    not_to_be_shape_name_id = shape_name + "_" + str(oid)
        clip_oid = field + "_" + str(oid)
        arcpy.MakeFeatureLayer_management(clipper, clip_oid, query) 
        # Do the clip. We include the oid in the name of the output feature class. 
        filetype = ".shp"
    #    not_to_be_shape_name_id_filetype = not_to_be_shape_name_id + filetype
        clip_oid_file = clip_oid + filetype
        outFC = os.path.join(output_PATH, clip_oid_file)
        
    #    to_be_shape_name_id = os.path.basename(tobeclipped) + "_" + str(oid)
        arcpy.Clip_analysis(tobeclipped, clip_oid, outFC) 
         
        print("finished clipping:", str(oid)) 
        return True # everything went well so we return True
    except: 
        # Some error occurred so return False 
        print("error condition") 
        return False
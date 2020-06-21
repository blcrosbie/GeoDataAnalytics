import os, sys
import arcpy 
import multiprocessing 
from multicode import worker
 
## Input parameters
#clipper = r"C:\Users\blcrosbie\Documents\489\USA.gdb\States"
##clipper = arcpy.GetParameterAsText(0) 
#tobeclipped = r"C:\Users\blcrosbie\Documents\489\USA.gdb\Roads"
##tobeclipped = arcpy.GetParameterAsText(1)
#output_PATH = r"C:\Users\blcrosbie\Documents\489\output
 
def get_install_path():
    ''' Return 64bit python install path from registry (if installed and registered),
        otherwise fall back to current 32bit process install path.
    '''
    if sys.maxsize > 2**32: return sys.exec_prefix #We're running in a 64bit process
  
    #We're 32 bit so see if there's a 64bit install
    path = r'SOFTWARE\Python\PythonCore\2.7'
  
    from _winreg import OpenKey, QueryValue
    from _winreg import HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_64KEY
  
    try:
        with OpenKey(HKEY_LOCAL_MACHINE, path, 0, KEY_READ | KEY_WOW64_64KEY) as key:
            return QueryValue(key, "InstallPath").strip(os.sep) #We have a 64bit install, so return that.
    except: return sys.exec_prefix #No 64bit, so return 32bit path 
    
def mp_handler(clipper, tobeclipped, output_PATH):
 
    try: 
        # Create a list of object IDs for clipper polygons 
         
        arcpy.AddMessage("Creating Polygon OID list...") 
        print("Creating Polygon OID list...") 
        clipperDescObj = arcpy.Describe(clipper) 
        field = clipperDescObj.OIDFieldName 
      
        idList = [] 
        with arcpy.da.SearchCursor(clipper, [field]) as cursor: 
            for row in cursor: 
                id = row[0] 
                idList.append(id)
 
        arcpy.AddMessage("There are " + str(len(idList)) + " object IDs (polygons) to process.") 
        print("There are " + str(len(idList)) + " object IDs (polygons) to process.") 
 
        # Create a task list with parameter tuples for each call of the worker function. Tuples consist of the clippper, tobeclipped, field, and oid values.
        
        jobs = []
     
        for id in idList:
            jobs.append((clipper,tobeclipped,field,id,output_PATH)) # adds tuples of the parameters that need to be given to the worker function to the jobs list
 
        arcpy.AddMessage("Job list has " + str(len(jobs)) + " elements.") 
        print("Job list has " + str(len(jobs)) + " elements.") 
 
        # Create and run multiprocessing pool.

        multiprocessing.set_executable(os.path.join(get_install_path(), 'pythonw.exe')) # make sure Python environment is used for running processes, even when this is run as a script tool
 
        arcpy.AddMessage("Sending to pool") 
        print("Sending to pool") 
 
        cpuNum = multiprocessing.cpu_count()  # determine number of cores to use
        print("there are: " + str(cpuNum) + " cpu cores on this machine") 
        
        # SHUT DOWN MULTIPROCESS TO START
        # test first job 
#        test_job = jobs[0]
#        print(test_job)
#        passed = worker(test_job[0], test_job[1], test_job[2], test_job[3], test_job[4])
#        failed = 1 if passed else 0
        with multiprocessing.Pool(processes=cpuNum) as pool: # Create the pool object    
           res = pool.starmap(worker, jobs)  # run jobs in job list; res is a list with return values of the worker function

        # If an error has occurred report it 
        failed = res.count(False) # count how many times False appears in the list with the return values
        
        if failed > 0:
            arcpy.AddError("{} workers failed!".format(failed)) 
            print("{} workers failed!".format(failed)) 
         
        arcpy.AddMessage("Finished multiprocessing!") 
        print("Finished multiprocessing!") 
 
    except arcpy.ExecuteError:
        # Geoprocessor threw an error 
        arcpy.AddError(arcpy.GetMessages(2)) 
        print("Execute Error:", arcpy.ExecuteError) 
    except Exception as e: 
        # Capture all other errors 
        arcpy.AddError(str(e)) 
        print("Exception:", e)
 
if __name__ == '__main__': 
    # Input parameters
    my_clipper = r"C:\Users\blcrosbie\Documents\489\USA.gdb\States"
    #clipper = arcpy.GetParameterAsText(0) 
    my_tobeclipped = r"C:\Users\blcrosbie\Documents\489\USA.gdb\Roads"
    #tobeclipped = arcpy.GetParameterAsText(1)
    my_output_PATH = r"C:\Users\blcrosbie\Documents\489\output"
    mp_handler(my_clipper, my_tobeclipped, my_output_PATH) 
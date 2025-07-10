"""
--------------------------------------------------------------------------------------------------------------------------------
ZoningDistrictsWeb_Workflow.py

Description:
 Export zoning district features for monthly release.
 
Requirements:
Create a folder anywhere you like
Copy the template folder from M:\GIS\BytesProduction\PyProcessing\Templates\zoning into that folder
If needed update Metadata templates on M:\GIS\BytesProduction\PyProcessing\ArcGIS_Team_Files\Metadata\zoning

Parameter list
                                Parameter Properties
	Display Name                                              Data type                  Type       Direction  
  arvg[1]-   Input Zoning District (TRD.nyzd)                     Feature Class              Required   Input
  arvg[2]-   Input Commercial Overlay District (TRD.nyco)         Feature Class              Required   Input
  arvg[3]-   Input Special Purpose Districts (TRD.nysp)           Feature Class              Required   Input
  arvg[4]-   Input Special Purpose Subdistrict (TRD.nysp_sd)      Feature Class              Required   Input
  arvg[5]-   Input Limited Height District (TRD.nylh)             Feature Class              Required   Input  
  arvg[6]-   Input E-Designation points (TRD.nydp)                Feature Class              Required   Input 
  arvg[7]-   Input Zoning Index (TRD.nyzi)                        Feature Class              Required   Input 
  arvg[8]-   Output Folder                                        Workspace                  Required   Input
  arvg[9]-   Metadata Template Folder                             Workspace                  Required   Input
  argv[10]-  Metadata Version                                     String                     Optional   Input
  argv[11]-  Calendar Data                                        String                     Required   Input  
  argv[12]-  Publication date                                     String                     Required   Input
  argv[13]-  Other Metadata changes                               String                     Optional   Input
  argv[14]-  Zip files                                            Check Box                  Required   Input

 Author: Uttam Bera
 Created Date: 9/18/2011
 
 Update: October 28 2011
 nydp export deleted
 
 Update: September 2015
 By: Matt Downing
 For: Use as tool within Arc
 
 DO NOT RUN FROM python. THIS IS MEANT TO BE RUN AS A TOOL FROM ARC
 Usage:
 "M:\GIS\ArcGIS_Team_Files\ArcSDE@DCP@SDE.sde\sde.TRD.ZONING\sde.TRD.nyzd" "M:\GIS\ArcGIS_Team_Files\ArcSDE@DCP@SDE.sde\sde.TRD.ZONING\sde.TRD.nyco" "M:\GIS\ArcGIS_Team_Files\ArcSDE@DCP@SDE.sde\sde.TRD.ZONING\sde.TRD.nysp" "M:\GIS\ArcGIS_Team_Files\ArcSDE@DCP@SDE.sde\sde.TRD.ZONING\sde.TRD.nysp_sd" "M:\GIS\ArcGIS_Team_Files\ArcSDE@DCP@SDE.sde\sde.TRD.ZONING\sde.TRD.nylh" "M:\GIS\ArcGIS_Team_Files\ArcSDE@DCP@SDE.sde\sde.TRD.ZONING\sde.TRD.SidewalkCafeZones" "M:\GIS\ArcGIS_Team_Files\ArcSDE@DCP@SDE.sde\sde.TRD.ZONING\sde.TRD.nyzi" "C:\temp\Zoning\2014\June" "M:\GIS\ArcGIS_Team_Files\Metadata\zoning\AGS10" "#" "2014-06-26T00:00:00" "2014-06-26T00:00:00" "#" "true"
--------------------------------------------------------------------------------------------------------------------------------
"""

#------------------------------------------------------------------------------#
# Functions
#------------------------------------------------------------------------------#

import os, sys, re, shutil, string, arcgisscripting, time, traceback, socket, glob, arcpy, zipfile
import datetime
import arcpy
import xml.dom.minidom
from bs4 import BeautifulSoup
# sys.path.append --path removed to metadata

def printMes(inMessage):
 #print inMessage
 arcpy.AddMessage(inMessage)

"""
-------------------------------------------------------------------------
Function:
    Parses HTML file to remove specific tags.
-------------------------------------------------------------------------
"""
def HTMLParse(html_file):
    soup = BeautifulSoup(open(html_file).read(), )
    printMes("removing No thumbnail tag")
    noTumbnail_div = soup.find('div',{'class':'noThumbnail'})
    noTumbnail_div.replaceWith('')
    printMes("removing fdgc tag")
    if soup.has_attr('fgdcMetadata'):
     arcpy.AddMessage("has div fgdcMetadata")
     removeFDGCtags = soup.find('div',{'id':'fgdcMetadata'})
     removeFDGCtags.replaceWith('')
    printMes("removing h2 fdgc tag")
    if soup.has_attr('fgdc head'):
     arcpy.AddMessage("has div fgdc head")
     removeFDGCheadtags = soup.find('h2',{'class':'fgdc head'})
     removeFDGCheadtags.replaceWith('')
    f = open(html_file, 'w')
    f.write(str(soup))
    f.close()
    printMes("completed")
    
def HTMLParse_ras(html_file):
 soup = BeautifulSoup(open(html_file).read(), )
 printMes("removing No thumbnail tag") 
 noTumbnail_div = soup.find('div',{'class':'noThumbnail'})
 noTumbnail_div.replaceWith('')
 #printMes("removing fdgc tag")
 #removeFDGCtags = soup.find('div',{'id':'fgdcMetadata'})
 #removeFDGCtags.replaceWith('')
 printMes("removing h2 fdgc tag")
 removeFDGCheadtags = soup.find('h2',{'class':'fgdc head'})
 removeFDGCheadtags.replaceWith('')
 f = open(html_file, 'w')
 f.write(str(soup))
 f.close()
 printMes("completed")

"""
-------------------------------------------------------------------------
Function:
    Determines the basename (i.e. filename) from a specific path
-------------------------------------------------------------------------
"""
def GetFileNameFromPath(Path,IncludeExtension=1):

    PathIndex = Path.rfind("\\")
    if PathIndex>0:
	    FileExt = Path[PathIndex+1:]
	    if Path.find(".sde")>0:
		    if FileExt.rfind(".")>0:
			    return FileExt[FileExt.rfind(".")+1:]
		    else:
			    return FileExt
	    elif IncludeExtension == 0 and FileExt.rfind(".")<>-1:
		    PathIndex2 = FileExt.rfind(".")
		    return FileExt[:PathIndex2]
	    else:
		    return FileExt
    else:
	    return Path
	
	
## Create Temporary Workspace for the Geoprocessing...
def createWS(fgdb):
	arcpy.env.workspace=fgdb
	#temp_dir = r"c:\temp\Zoning_GP"
	temp_dir = outputFCPath + "\\Zoning_GP"
	if os.path.exists(temp_dir)==0:
		os.makedirs(temp_dir)
		arcpy.RefreshCatalog(temp_dir)
	if arcpy.Exists(fgdb)==0:
		arcpy.CreateFileGDB_management(os.path.dirname(fgdb), os.path.basename(fgdb))
	else:
		# Delete any feature classes in the temporary workspace
		temp_fcs=arcpy.ListFeatureClasses()
		for fc in temp_fcs:
		    dsc=arcpy.Describe(fc)
		    arcpy.Delete_management(dsc.CatalogPath)
		
"""
-------------------------------------------------------------------------
Function:
    Get Install Directory
-------------------------------------------------------------------------
"""
def get_install_directory():
    """ this function returns the filepath to the ArcGIS install directory """
    import arcpy
    return arcpy.GetInstallInfo()['InstallDir']
	
"""
-------------------------------------------------------------------------
Function:
    Load ArcToolBox
-------------------------------------------------------------------------
"""
def load_toolboxes(gp):
    """loads the Conversion and Data Management Toolboxes into memory
       -> toolboxes are ONLY applied to the gp input  """
    install_dir = get_install_directory()
    toolbox_dir = os.path.join(install_dir, 'ArcToolbox', 'Toolboxes')
    for tbx in ['Conversion Tools.tbx', 'Data Management Tools.tbx']:
        tbx_path = os.path.join(toolbox_dir, tbx)
        arcpy.AddToolbox(tbx_path)


def UpdateMetadata(flist, webPath, MetadataFolder, MetadataVersion, MetadataCalDate, MetadataPubDate, MetadataChangesDesc, CouncilDate):
    import metadata_update_tool.update_metadata as UPDATE
    printMes("******* flist: ")
    printMes(flist)
    for infile in flist:
     arcpy.AddMessage("*****infile name::::::::::**********")
     arcpy.AddMessage(infile)
     MetadataTemplate = MetadataFolder + "\\" + os.path.basename(infile) + ".shp.xml"
     printMes("Updating metadata for " + infile + "\n")
     if os.path.exists(MetadataTemplate):
      UPDATE.replace_values(MetadataTemplate, "#", "#", MetadataCalDate, MetadataPubDate, CouncilDate)
			
     #Starts importing Metadata into datasets
     arcpy.ImportMetadata_conversion(MetadataTemplate, "FROM_ESRIISO", infile, "DISABLED")
     arcpy.RefreshCatalog(infile)
     
     #Export the metadata from ARCGIS format to perform some well-defined tasks
     temp_dir = os.path.join(webPath, "metadata_GP")
     printMes(temp_dir)
     if os.path.exists(temp_dir)==0:
	 os.makedirs(temp_dir)
	 arcpy.RefreshCatalog(temp_dir)
     
     RemoveMetadataInfo_fc(infile, temp_dir)
     
     #Remove all unwanted XML files
     if os.path.isdir(temp_dir):
	 files = glob.glob(temp_dir + "/*")
	 for f in files:
	     os.remove(f)
     
     #Export to HTML file
     HTML_OUT = webPath + os.path.basename(infile) +  "_metadata.html"
     printMes(HTML_OUT)
     dir = get_install_directory()
     xslt = dir + "Metadata/Stylesheets/ArcGIS.xsl"
     arcpy.XSLTransform_conversion(infile, xslt, HTML_OUT, "#")
     printMes(arcpy.GetMessages())
     
     #Parse HTML file to remove unwanted tags
     HTMLParse(HTML_OUT)		   		
    else:
     printMes(MetadataTemplate + " does not exists.")

def RemoveMetadataInfo_fc(fx,out_MdDir):
    arcpy.ClearWorkspaceCache_management()
    # list to hold replacements... tuple containing (xslt, xml)
    printMes("Removing unnecessary metadata info..............")
    xml_list = []    
    dir = get_install_directory()
    remove_gp_history_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove geoprocessing history.xslt"
    remove_gp_local_storage_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove local storage info.xslt"
    remove_gp_thumbnail_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove thumbnail.xslt"
    remove_gp_empty_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove empty elements.xslt"
    remove_gp_pre94_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove pre94 metadata elements.xslt"
    
    worksp = os.path.dirname(fx)
    outfileBname = os.path.basename(fx)
    arcpy.env.workspace = worksp        
    gp_hist_xml = out_MdDir + os.sep + str(outfileBname) + "gp_hist.xml"
    gp_local_xml = out_MdDir + os.sep + str(outfileBname) + "gp_local.xml"
    gp_thumbnail_xml = out_MdDir + os.sep + str(outfileBname) + "gp_thumnail.xml"
    gp_empty_xml = out_MdDir + os.sep + str(outfileBname) + "gp_empty.xml"
    gp_pre94_xml = out_MdDir + os.sep + str(outfileBname) + "gp_pre94.xml"
    
    xml_list.append((remove_gp_history_xslt, gp_hist_xml))
    xml_list.append((remove_gp_local_storage_xslt, gp_local_xml))
    xml_list.append((remove_gp_thumbnail_xslt, gp_thumbnail_xml))
    xml_list.append((remove_gp_empty_xslt, gp_empty_xml))
    xml_list.append((remove_gp_pre94_xslt, gp_pre94_xml))
    
    
    for xmls in xml_list:
     #Process: XSLT Transformation - Remove GP history
     printMes("-------------- Begin XSLT Transformation ---------------")
     xslt = xmls[0]
     xmlout = xmls[1]
     arcpy.XSLTransform_conversion(fx, xslt, xmlout, "")
     printMes("Completed xml coversion on {0}".format(fx))
     # Process: Metadata Importer
     arcpy.MetadataImporter_conversion(xmlout,fx)
     arcpy.RefreshCatalog(fx)
     printMes("Imported XML on {0}".format(fx))
	
"""
-------------------------------------------------------------------------
Function:
    Converts feature class to shapefile
-------------------------------------------------------------------------
"""
def fc2shape(FC_In,Shp_Out,Expression="#",listIndex=["#"],Overwrite=0,RepairGeom=1,DCP_SR=1):
    WS =  os.path.dirname(Shp_Out)
    Name = os.path.basename(Shp_Out)
    if (arcpy.Exists(Shp_Out) and TrueOrFalse(Overwrite)==True) or arcpy.Exists(Shp_Out)==0:
	if TrueOrFalse(DCP_SR)==True:
	    # Set Environmental Defaults to use same Spatial Reference as LION on DCPGIS
	    #lion_sr = arcpy.Describe(strLionFeatureClass).spatialReference  #Database Connections\DCPGIS@DCP@SDE.sde\sde.DCP.LION')
	    #arcpy.env.XYResolution = lion_sr.XYResolution
	    #arcpy.env.XYTolerance = lion_sr.XYTolerance
	    arcpy.env.OutputCoordinateSystem = CoordSYS
	    if Expression=='#':
		ShpCount=int(gp.GetCount(FC_In))
		SelectCount=ShpCount
	    else:
		ShpCount=int(gp.GetCount(FC_In))
		arcpy.MakeFeatureLayer_management(FC_In,'TmpLayer',Expression)
		SelectCount=int(gp.GetCount('Tmp_Layer'))
		arcpy.Delete_management(Tmp_Layer)
	    BatchSize=3000
	    FC_In_Desc = arcpy.Describe(FC_In)
	    OID_Name = FC_In_Desc.OIDFieldName
	    if Shp_Out<=10000:
		arcpy.Select_analysis(FC_In,Shp_Out,Expression)
	    else:
		import arcgisscripting
		Finished=False
		ShpSplits=int(ShpCount/BatchSize)
		n=0
		OldTime=time.time()
		while Finished==False:
		    minObjectID=BatchSize*n
		    maxObjectID=BatchSize*(n+1)
		    TempOutput = os.path.join(os.path.dirname(Shp_Out),GetFileNameFromPath(Shp_Out,0)+'__Iteration.shp')
		    arcpy.Select_analysis(FC_In,TempOutput,"ObjectID>="+str(minObjectID)+" AND ObjectID<"+str(maxObjectID))
		    if Expression=='#':
			if n==0:
			    arcpy.Select_analysis(TempOutput,Shp_Out)
			else:
			    arcpy.Append_management(TempOutput,Shp_Out)
		    else:
			if n==0:
			    arcpy.Select_analysis(TempOutput,Shp_Out,Expression)
			else:
			    arcpy.MakeFeatureLayer_management(TempOutput,"Tmp_Layer",Expression)
			    arcpy.Append_management("Tmp_Layer",Shp_Out)
			    arcpy.Delete_management(Tmp_Layer)
		    n=n+1
		    arcpy.AddMessage(str(maxObjectID) + ' (Time: ' + str(round((time.time()-OldTime)*10000/BatchSize)) +  ' (sec/10k)')
		    OldTime=time.time()
		    if n>=ShpSplits:
			if SelectCount==gp.GetCount(Shp_Out):
			    Finished=True
			    arcpy.Delete_management(TempOutput)
	    print arcpy.GetMessages()
	# Repair Geometry
	if TrueOrFalse(RepairGeom)==True:
	    arcpy.RepairGeometry_management(Shp_Out)
	    arcpy.AddMessage("REPAIRING GEOMETRY")
	    arcpy.AddMessage("\n" + arcpy.GetMessages())
	if listIndex <> ['#']:
	    for strIndex in listIndex:
		try:
		    arcpy.AddIndex_management(Shp_Out, strIndex, "idx_" + strIndex, "NON_UNIQUE", "NON_ASCENDING")
		except:
		    pass
    else:
	arcpy.AddMessage("\n" + Shp_Out + " already exists and Overwrite is off.")

"""
-------------------------------------------------------------------------
Function:
    Interprets numbers or strings that represent True and returns the Boolean: True, else False.  
    Useful for ArcGIS because the boolean type in ArcToolbox that is assigned is not a real boolean 
    but is a string of either "true" or "false"
-------------------------------------------------------------------------
"""
def TrueOrFalse(TrueOrFalse):
	if type(TrueOrFalse)==str:
		TrueOrFalse=TrueOrFalse.lower
	if TrueOrFalse in [1,True,'t','true','y','yes']:
		return True
	else:
		return False

		
def createShp(featureList, folderPath):
	for infile in featureList:
		#convert to shapefile and zip (if boolean is true)
		shape_out = folderPath + os.path.basename(infile) +".shp"
		fc2shape(infile,shape_out,'#','#',True,True,True)
		shape_list.append(shape_out)
		printMes(shape_list)

"""
-------------------------------------------------------------------------
Function:
    Converts an ESRI list (i.e. a string containing a list of items separated by semicolons) to a list, or vice-versa.
-------------------------------------------------------------------------
"""
def ConvertToList(Value,ConvertToEsriList=0):

    if str(ConvertToEsriList).lower() in ('0','false','f','no','n'):
	    if type(Value)<>list:
		    if str(Value).find(';')>0:
			    return Value.strip().split(';')
		    else:
			    return [Value]
	    else:
		    return Value
    else:
	    if type(Value)==list:
		    esri_list=''
		    for item in Value:
			    if esri_list<>'' : esri_list=esri_list+';'
			    esri_list=esri_list+str(item)
		    return esri_list
	    else:
		    return Value
    

"""
-------------------------------------------------------------------------
Function:
    Creates a compressed zip file and adds spatial files, other files and folders.
    ZipArchivePath - Zip file to be created. Will be overwritten if it already exists.
    ZipItems - Semicolon delimeted list of files/folders to be added.
    ParentFolder - Optional folder that all items will be placed within the zipfile.
    
    Users only need to add the primary file for spatial data types that are actually are 
    made up of a collection of files (e.g. the *.shp file of a Shapefiles), as long as the 
    collection is included in the "Extensions" list and the primary file extension is the 
    first in that list.
-------------------------------------------------------------------------
"""
def Zip_Geofile(ZipArchivePath, ZipItems, ParentFolder=''):

    FilesAdded=0
    isdir = os.path.isdir
    arcpy.AddMessage("")
    #Geofile associations
    Extensions = [['shp', 'dbf','shx','prj','shp.xml'],
                  ['tab', 'dat','id','map','ind']]

    ParentFolder = ParentFolder.strip()
    if ParentFolder not in ['','#'] or ParentFolder.endswith('\\')==False:
	ParentFolder = ParentFolder + '\\'
    elif ParentFolder == '#':
	ParentFolder = ''

    ZipList = ConvertToList(ZipItems)
    
    import zipfile    
    
    #print ZipList
    cwd=os.getcwd()
    #print cwd
       
    z = zipfile.ZipFile(ZipArchivePath,mode="w",compression=zipfile.ZIP_DEFLATED)
    
    for item in ZipList:
	item = item.strip("'")
	item_basename=os.path.basename(item)
	if item_basename.find('.')>0:
	    item_ext=item[item.rfind('.')+1:].lower()
	else:
	    item_ext=''
    
	if os.path.isdir(item): #Adds entire folder (including subfolders) to archive - Geodatabase
	    os.chdir(item)
	    path = os.path.abspath(item)
	    folder = os.path.basename(item)
	    for (dirpath, dirnames, filenames) in os.walk(path):
		for f in filenames:
		    if not f.endswith('.lock'):
			arcpy.AddMessage("Adding %s..." % os.path.join(path, dirpath, f))
			try:
			    absname = os.path.abspath(os.path.join(dirpath, f))
			    arcname = os.path.join(folder,absname[len(path) + 1:])
			    z.write(absname, arcname)
			    
			except Exception, e:
			    arcpy.AddWarning("    Error adding %s: %s" % (f, e))			
	    
	else:
	    ext_type=0
	    for ext in Extensions:
		if item_ext==ext[0]: #Adds geofile and all files that are associated with it (as defined above) - Shapefiles
		    ext_type=1
		    ext_len=len(ext[0])
		    item_no_ext=item[:-ext_len]
		    for e in ext:
			if os.path.exists(item_no_ext + e):
			    filename = item_no_ext + e
			    arcname = ParentFolder + os.path.basename(item_no_ext + e)
			    z.write(filename,arcname)
			    FilesAdded = FilesAdded + 1
			    arcpy.AddMessage("Added to zip:  " + filename)
	   
    z.close()
    os.chdir(cwd)
    arcpy.AddMessage("Packaged " + str(FilesAdded) + " file(s) in " + ZipArchivePath)
    arcpy.AddMessage("")  

def zipShp(featList, name, type):
	tYear = datetime.datetime.strptime(MetadataPubDate, '%m/%d/%Y').year
	tMonth = datetime.datetime.strptime(MetadataPubDate, '%m/%d/%Y').month
	if len(str(tMonth))==1:
	    tMonth = "0" + str(tMonth)
	if type == 'shp':
		ZipShpPath = os.path.dirname(dirWEB) + "\\" + name + "_" + str(tYear) + str(tMonth) + "shp.zip" 
		ZipName = name + "_" + str(tYear) + str(tMonth)+ "shp"
	else:
		ZipShpPath = os.path.dirname(dirWEB) + "\\" + name + "_" + str(tYear) + str(tMonth) + "fgdb.zip"
		ZipName = name + "_" + str(tYear) + str(tMonth) + "fgdb"
	
	Zip_Geofile(ZipShpPath, featList, ZipName)
	#printMes("Ziping Completed")
	arcpy.AddMessage("Zipping Completed")
	
def zipShp1(featList, type):
	tYear = datetime.datetime.strptime(MetadataPubDate, '%m/%d/%Y').year
	tMonth = datetime.datetime.strptime(MetadataPubDate, '%m/%d/%Y').month
	if len(str(tMonth))==1:
	    tMonth = "0" + str(tMonth)
	if type == 'shp':
		ZipShpPath = os.path.dirname(dirWEB) + "\\" + "nycgissidewalkcafe_" + str(tYear) + str(tMonth) + "shp.zip" 
		#ZipShpPath = os.path.dirname(dirWEB) + "\\" + "nycgissidewalkcafe_shp.zip" #+ str(tYear) + str(tMonth) + "shp.zip" 
		ZipName = "nycgissidewalkcafe_" + str(tYear) + str(tMonth)+ "shp"
		#ZipName = "nycgissidewalkcafe_shp" #+ str(tYear) + str(tMonth)+ "shp"
	else:
		ZipShpPath = os.path.dirname(dirWEB) + "\\" + "nycgissidewalkcafe_" + str(tYear) + str(tMonth) + "fgdb.zip"
		#ZipShpPath = os.path.dirname(dirWEB) + "\\" + "nycgissidewalkcafe_fgdb.zip" #+ str(tYear) + str(tMonth) + "fgdb.zip"
		ZipName = "nycgissidewalkcafe_" + str(tYear) + str(tMonth) + "fgdb"
		#ZipName = "nycgissidewalkcafe_fgdb" #+ str(tYear) + str(tMonth) + "fgdb"
	
	Zip_Geofile(ZipShpPath,featList, ZipName)
	printMes("completed")

"""
-------------------------------------------------------------------------
Function:
    Interprets numbers or strings that represent True and returns the Boolean: True, else False.  
    Useful for ArcGIS because the boolean type in ArcToolbox that is assigned is not a real boolean 
    but is a string of either "true" or "false"
-------------------------------------------------------------------------
"""
def ReturnBool(TF):
 strBool = str(TF).lower()
 if strBool in ("1","t","true","y","yes"):
  return 1
 else:
  return 0


"""
-------------------------------------------------------------------------
Function:   
    export to fgdb
-------------------------------------------------------------------------
"""   
def Export_fGDB(shp_list, fgdb_out,overwrite):
    if fgdb_out.lower().find(".gdb")<>-1:
	if (arcpy.Exists(fgdb_out) and ReturnBool(overwrite)==1) or arcpy.Exists(fgdb_out)==0:
	    #if (xgp.WS_FC_Exists(fgdb_out)==1 and xgp.ReturnBool(overwrite)==1) or xgp.WS_FC_Exists(fgdb_out)==0:
	    if arcpy.Exists(fgdb_out)==1:
		arcpy.Delete_management(fgdb_out)
		
		workspace=dirShp
		arcpy.RefreshCatalog(dirShp)
		arcpy.CreateFileGDB_management(os.path.dirname(fgdb_out), os.path.basename(fgdb_out))
		exportlist = '"' + ';'.join(shp_list) + '"'
		printMes(exportlist)
		arcpy.FeatureClassToGeodatabase_conversion(exportlist,fgdb_out)
		printMes(arcpy.GetMessages())
				
	else:
	    printMes(" Already exists and overwrite set to off.")
	    

		    
#------------------------------------------------------------------------------#
# Import system modules

try:
	from ConfigParser import *
	#read configuration file for paths, versions, etc.
	config = ConfigParser()
	#change the path of the config file to the root of our scripts or m drive when go live
	config.read('M:\\GIS\\BytesProduction\\PyProcessing\\TRD\\Tools\\dcp_public_python27.conf')
	    
	#variables to hold config values
	PublicScriptsPath = config.get('paths', 'PublicScriptDir')
	SDE_DCP_Connection = 'Database Connections\DCPGIS@TRD@SDE.sde' #config.get('paths', 'SDE_DCP_Connection')
	Cdrive_DCPStylesheet = config.get('paths', 'DCPStylesheet')
	Cdrive_DCPWebStylesheet = config.get('paths', 'DCPWebStylesheet')
	#strLionFeatureClass = config.get('paths', 'LionFeatureClass')
	CoordSYS = config.get('paths', 'CoordSYSPrj')	
    
	sys.path.append(PublicScriptsPath)
	
	#------------------------------------------------------------------------------#
	# Create the Geoprocessor object
	gp = arcgisscripting.create()
	gp.Overwriteoutput = 1	
	
	#xgp has common dcp functions
	#import SyncPackages_p27
	#import xgp
	
	
	printMes("Zoning Districts: Start Processing" + '\n')
	time_start = time.clock()
	
	# Script arguments...
	nyzd = r"M:\GIS\BytesProduction\PyProcessing\TRD\Connections\trd@GISTRD.sde\GISTRD.TRD.Digital_Zoning_Map\GISTRD.TRD.DZM_nyzd" #arcpy.GetParameterAsText(0)
	nyco = r"M:\GIS\BytesProduction\PyProcessing\TRD\Connections\trd@GISTRD.sde\GISTRD.TRD.Digital_Zoning_Map\GISTRD.TRD.DZM_nyco" #r"M:\GIS\ArcGIS_Team_Files\ArcSDE@DCP@SDE.sde\sde.TRD.ZONING\sde.TRD.nyco" arcpy.GetParameterAsText(1)
	nysp = r"M:\GIS\BytesProduction\PyProcessing\TRD\Connections\trd@GISTRD.sde\GISTRD.SDE.DZM_nysp_dissolve" #arcpy.GetParameterAsText(2) #adjusted for dissolved version
	nysp_sd = r"M:\GIS\BytesProduction\PyProcessing\TRD\Connections\trd@GISTRD.sde\GISTRD.TRD.Digital_Zoning_Map\GISTRD.TRD.DZM_nysp_sd" #arcpy.GetParameterAsText(3)
	nylh = r"M:\GIS\BytesProduction\PyProcessing\TRD\Connections\trd@GISTRD.sde\GISTRD.TRD.Digital_Zoning_Map\GISTRD.TRD.DZM_nylh" #arcpy.GetParameterAsText(4)
	nysidewalkcafe = r"M:\GIS\BytesProduction\PyProcessing\TRD\Connections\trd@GISTRD.sde\GISTRD.TRD.Digital_Zoning_Map\GISTRD.TRD.DZM_SidewalkCafeZones" #arcpy.GetParameterAsText(5) #sidewalk cafe addition
	nyzi = r"M:\GIS\BytesProduction\PyProcessing\TRD\Connections\trd@GISTRD.sde\GISTRD.TRD.Digital_Zoning_Map\GISTRD.TRD.DZM_nyzi" #arcpy.GetParameterAsText(6)
	outputFCPath = arcpy.GetParameterAsText(0)
	MetadataFolder = r"M:\GIS\BytesProduction\PyProcessing\TRD\ArcGIS_Team_Files\Metadata\zoning\AGS10" #arcpy.GetParameterAsText(8)  # the metadata xml template file (ex: M:\GIS\ArcGIS_Team_Files\Metadata\Districts\nypa.shp.xml)
	MetadataVersion = '#' #arcpy.GetParameterAsText(9) # the version of the data (ex: 09A)
	MetadataCalDate = arcpy.GetParameterAsText(1) # the calender date of the data (ex: "2014-01-25T00:00:00")
	MetadataPubDate = arcpy.GetParameterAsText(1) # the publication date of the data (ex: "2014-01-25T00:00:00")
	MetadataChangesDesc = '#' #arcpy.GetParameterAsText(12) # description of change in metadata?
	CouncilDate = arcpy.GetParameterAsText(2)
	#CouncilDate = CouncilDate.encode("utf-8")
	#CouncilDate = CouncilDate.decode('ascii')
	#CouncilDate = CouncilDate.encode('ascii')
	#CouncilDate = CouncilDate.decode('utf-8')
	zipBol = 'true' #arcpy.GetParameterAsText(13) # "true"  #boolean to zip the files when done (ex: true)
		
	
	#path for saving zip files and metadata in web folder
	dirWEB = os.path.join(outputFCPath,'web\\')
	dirShp = os.path.join(outputFCPath,'shp\\')
	fgdb_path = os.path.join(outputFCPath,'fgdb\\')
	fgdb_out = os.path.join(fgdb_path,'zoning.gdb')
	fgdb_out_sw = os.path.join(fgdb_path,'sidewalkcafe.gdb')
	shape_list = []

	tYear = datetime.datetime.strptime(MetadataPubDate, '%m/%d/%Y').year
	tMonth = datetime.datetime.strptime(MetadataPubDate, '%m/%d/%Y').month

	'''
	Modifying all tYear and tMonth references to reflect the year and month associated with the user 
	inputted MetadataPubDate variable
	'''

	#create temp geoprocessing database
	#temp_fgdb = r"c:\temp\Zoning_GP\zoningGp.gdb"
	temp_fgdb = outputFCPath + "\\Zoning_GP\\zoningGp.gdb"
	if arcpy.Exists(temp_fgdb)==0:
		createWS(temp_fgdb)
	else:
		#arcpy.env.workspace=r"c:\temp\Zoning_GP\zoningGp.gdb"
		arcpy.env.workspace = outputFCPath + "\\Zoning_GP\\zoningGp.gdb"
		temp_fcs=arcpy.ListFeatureClasses()
		for fc in temp_fcs:
		    dsc=arcpy.Describe(fc)
		    arcpy.Delete_management(dsc.CatalogPath)		
		    
		arcpy.env.workspace=""
		arcpy.Compact_management(temp_fgdb)   
	
	    
	#temp_outws = 'c:\\temp\\Zoning_GP\\'
	temp_outws = outputFCPath
	
	#Local Variables
	nyzma_lyr = "nyzma Layer"
	nyzma_lyrT = "nyzma_lyrT"
	nyzd_temp = os.path.join(temp_fgdb, "nyzd")
	nysidewalkcafe_temp = os.path.join(temp_fgdb, "nysidewalkcafe")
	nyco_temp = os.path.join(temp_fgdb, "nyco")
	nysp_temp = os.path.join(temp_fgdb, "nysp")
	nysp_sd_temp = os.path.join(temp_fgdb, "nysp_sd")
	nylh_temp = os.path.join(temp_fgdb, "nylh")
	nyzma_temp = os.path.join(temp_fgdb, "nyzma")
	
	printMes("Start exporting features from SDE to temp database\n")

	# Process Zoning files to get correct schema
	arcpy.FeatureClassToFeatureClass_conversion(nyzd, temp_fgdb, "nyzd", "", "\"ZONEDIST 'ZONEDIST' true true false 15 Text 0 0 ,First,#," + nyzd + ",ZONEDIST,-1,-1\"", "")
	printMes(arcpy.GetMessages())
	arcpy.FeatureClassToFeatureClass_conversion(nyco, temp_fgdb, "nyco", "", "\"OVERLAY 'Commercial Overlay' true true false 15 Text 0 0 ,First,#," + nyco+ ",OVERLAY,-1,-1\"", "")
	printMes(arcpy.GetMessages())
	#sidewalk cafe
	arcpy.FeatureClassToFeatureClass_conversion(nysidewalkcafe, temp_fgdb, "nysidewalkcafe", "", "\"CafeType 'CafeType' true true false 25 Text 0 0 ,First,#," + nysidewalkcafe + ",CafeType,-1,-1\"", "")
	printMes(arcpy.GetMessages())
	arcpy.FeatureClassToFeatureClass_conversion(nysp, temp_fgdb, "nysp", "", "\"SDNAME 'SDNAME' true true false 255 Text 0 0 ,First,#," + nysp + ",SDNAME,-1,-1;SDLBL 'SDLBL' true true false 10 Text 0 0 ,First,#," + nysp + ",SDLBL,-1,-1\"", "")
	printMes(arcpy.GetMessages())
	arcpy.FeatureClassToFeatureClass_conversion(nysp_sd, temp_fgdb, "nysp_sd", "SUBDIST IS NOT NULL", "\"SPNAME 'SDNAME' true true false 255 Text 0 0 ,First,#," + nysp_sd + ",SDNAME,-1,-1;SPLBL 'SDLBL' true true false 10 Text 0 0 ,First,#," + nysp_sd + ",SDLBL,-1,-1;SUBDIST 'SUBDIST' true true false 50 Text 0 0 ,First,#," + nysp_sd + ",SUBDIST,-1,-1;SUB_AREA_NM 'Sub-Area Name' true true false 50 Text 0 0 ,First,#," + nysp_sd + ",SUBAREA_NM,-1,-1;SUBDIST_LBL 'Subdistrict Label' true true false 50 Text 0 0 ,First,#," + nysp_sd + ",SUBDIST_LBL,-1,-1;SUBAREA_LBL 'Sub-Area Label' true true false 50 Text 0 0 ,First,#," + nysp_sd + ",SUBAREA_LBL,-1,-1;SUBAREA_OTR 'Sub-Area Other' true true false 50 Text 0 0 ,First,#," + nysp_sd + ",SUBAREA_OTR,-1,-1\"", "")
	printMes(arcpy.GetMessages())
	arcpy.FeatureClassToFeatureClass_conversion(nylh, temp_fgdb, "nylh", "", "\"LHNAME 'LHNAME' true true false 50 Text 0 0 ,First,#," + nylh + ",LHNAME,-1,-1;LHLBL 'LHLBL' true true false 10 Text 0 0 ,First,#," + nylh + ",LHLBL,-1,-1\"", "") 
	printMes(arcpy.GetMessages())
	
	printMes("Processing Zoning Map Amendment layer\n")
	
	#Process nyzma to get data based on query
	arcpy.MakeFeatureLayer_management(nyzi, nyzma_lyr, "", "", "EFFECTIVE EFFECTIVE VISIBLE NONE;STATUS STATUS VISIBLE NONE;ULURPNO ULURPNO VISIBLE NONE;LUCATS LUCATS VISIBLE NONE;DCPI_ID DCPI_ID VISIBLE NONE;PROJECT_NAME PROJECT_NAME VISIBLE NONE;INITIATIVE_TYPE INITIATIVE_TYPE VISIBLE NONE")
	printMes(arcpy.GetMessages())
	
	# Process: Select Layer By Attribute...
	# Removed restriction of records older than 2002. Requested by Matt Croswell and implemented by Adrian Ferrar 07/01/2019
	#arcpy.SelectLayerByAttribute_management(nyzma_lyr, "NEW_SELECTION", "EFFECTIVE >= '2002-01-30 00:00:00' AND STATUS = '1' OR STATUS = '2'")
	arcpy.SelectLayerByAttribute_management(nyzma_lyr, "NEW_SELECTION", "STATUS = '1' OR STATUS = '2'")
	printMes(arcpy.GetMessages())
	printMes("Selected records:" + str(arcpy.GetCount_management(nyzma_lyr)))
	arcpy.SelectLayerByAttribute_management(nyzma_lyr, "SUBSET_SELECTION", "INITIATIVE_TYPE = '1'")
	printMes(arcpy.GetMessages())
	printMes("Selected records:" + str(arcpy.GetCount_management(nyzma_lyr)))
	# Count the number of selected records
	printMes("Selected records:" + str(arcpy.GetCount_management(nyzma_lyr)))
 
	# Process: Feature Class to Feature Class...
	arcpy.FeatureClassToFeatureClass_conversion(nyzma_lyr, temp_fgdb, "nyzma", "", "\"EFFECTIVE 'EFFECTIVE' true true false 36 Date 0 0 ,First,#," + nyzi + ",EFFECTIVE,-1,-1;STATUS 'Status' true true false 15 Text 0 0 ,First,#," + nyzi + ",STATUS,-1,-1;ULURPNO 'ULURPNO' true true false 50 Text 0 0 ,First,#," + nyzi + ",ULURPNO,-1,-1;LUCATS 'LUCATS' true true false 10 Text 0 0 ,First,#," + nyzi + ",LUCATS,-1,-1;PROJECT_NAME 'PROJECT_NAME' true true false 100 Text 0 0 ,First,#," + nyzi + ",PROJECT_NAME,-1,-1\"", "")
	printMes(arcpy.GetMessages())
		
	#Process nyzma to get data based on query
	arcpy.MakeFeatureLayer_management(nyzma_temp, nyzma_lyrT)
	printMes(arcpy.GetMessages())
	#Calculate Status field as it is a domain value
	# Process: Select Layer By Attribute...
	arcpy.SelectLayerByAttribute_management(nyzma_lyrT, "NEW_SELECTION", "STATUS = '1'")
	printMes(arcpy.GetMessages())
	printMes("Selected records:" + str(arcpy.GetCount_management(nyzma_lyrT)))
	
	# Process: Calculate Field...
	arcpy.CalculateField_management(nyzma_lyrT, "STATUS", "\"Adopted\"", "VB", "")
	printMes(arcpy.GetMessages())
	arcpy.SelectLayerByAttribute_management(nyzma_lyrT, "CLEAR_SELECTION", "")
	
	# Process: Select Layer By Attribute...
	arcpy.SelectLayerByAttribute_management(nyzma_lyrT, "NEW_SELECTION", "STATUS = '2'")
	printMes(arcpy.GetMessages())
	printMes("Selected records:" + str(arcpy.GetCount_management(nyzma_lyrT)))
	
	# Process: Calculate Field...
	arcpy.CalculateField_management(nyzma_lyrT, "STATUS", "\"Certified\"", "VB", "")
	printMes(arcpy.GetMessages())
	arcpy.SelectLayerByAttribute_management(nyzma_lyrT, "CLEAR_SELECTION", "")
	
	printMes("Completed processing Zoning Map Amendment layer\n")
	
	#Convert Layers to list
	listIndex = [nyzd_temp, nyco_temp, nysp_temp, nysp_sd_temp, nylh_temp, nyzma_temp]
	printMes("********************* Zoning data processing ****************************")
	
	# Update Metadata
	printMes("----------- Begin metadata update process --------------------------\n")
	UpdateMetadata(listIndex, dirWEB, MetadataFolder, MetadataVersion, MetadataCalDate, MetadataPubDate, MetadataChangesDesc, CouncilDate)
	printMes("----------- completed metadata update ------------------------------\n")
	
	# Create shapefiles
	printMes("-------------- Start processing shape files -------------------------- \n")
	createShp(listIndex, dirShp)
	printMes("--------------- Completed processing shape files ----------------------\n")
	
	# Create fgdb
	printMes("--------------- Start processing fgdb ---------------------------------\n")
	Export_fGDB(listIndex, fgdb_out,'1')
	printMes("--------------- Completed processing fgdb -----------------------------\n")

	# Zip files
	printMes("--------------- Start ziping files ------------------------------------\n")
	
	if zipBol=='true':
	    zipShp(shape_list, "nycgiszoningfeatures", "shp")
	    zipShp(fgdb_out, "nycgiszoningfeatures", "fgdb")
	    	
	printMes("********************* Completed Zoning data processing *********************")
	
	# Process Sidewalk cafe
	printMes("********************* Sidewalkcafe data processing *************************")
	
	swIndex=[nysidewalkcafe_temp]
	shape_list=[]
	
	# Update Metadata
	printMes(" Begin metadata update\n")
	UpdateMetadata(swIndex, dirWEB, MetadataFolder, MetadataVersion, MetadataCalDate, MetadataPubDate, MetadataChangesDesc, CouncilDate)
	printMes(" completed metadata update\n")
	
	# Create shapefiles
	printMes("Start processing shape files and modify metadata\n")
	createShp(swIndex, dirShp)
	printMes("Completed processing shape files\n")
	printMes("Start processing fgdb\n")
	
	# Create fgdb
	Export_fGDB(swIndex,fgdb_out_sw,'1')
	printMes("Completed processing fgdb\n")
	
	# Zip files
	printMes("Start ziping files\n")
	if zipBol=='true':
		zipShp(shape_list, "nycgissidewalkcafe", "shp")
		zipShp(fgdb_out_sw, "nycgissidewalkcafe", "fgdb")	
	
	printMes("Completed ziping files\n")
	
#------------------------------
# Edit April 5, 2016
# Brendan Cleary
# Add ability to export raster to gdb
#------------------------------
	arcpy.env.workspace = fgdb_path
	arcpy.env.overwriteOutput = True
	printMes("********************* Raster processing *************************")
	#raster = r"G:\Connections\arcsdegis\sde@GISPROD.sde\GISPROD.SDE.GeoreferencedNYCZoningMaps" # Changed by AF 3/27/2020 because TRD changed to mosaic. Used to be G:\Connections\arcsdegis\sde@GISPROD.sde\GISTRD.TRD.NYC_Zoning_Maps : Changed by AF 3/2/2020 because TRD changed naming convention. Used to be GISTRD.TRD.Georef_zoning_maps
	raster = r"G:\Connections\arcsdegis\sde@GISTRD.sde\GISTRD.TRD.NYC_Zoning_Maps"
	fgdb_out_sgm = os.path.join(fgdb_path,'georeferencednyczoningmaps.gdb')
	szm_gdb_name = "georeferencednyczoningmaps"
	printMes("Creating File GDB")
	arcpy.CreateFileGDB_management(fgdb_path, szm_gdb_name)
	printMes("Copying Scanned Geo Maps to FGDB")
	#arcpy.RasterToGeodatabase_conversion(raster, fgdb_out_sgm) # -- Commenting out as this has changed to a Mosaic and cannot use RasterToGeodatabase anymore
	# Was testing CopyRaster, can remove after confirmed functional AF 04/30/2019
	arcpy.CopyRaster_management(raster, os.path.join(fgdb_out_sgm, 'NYC_Zoning_Maps'))
	printMes(os.path.join(fgdb_out_sgm, "NYC_Zoning_Maps"))
	arcpy.Rename_management(os.path.join(fgdb_out_sgm, "NYC_Zoning_Maps"), szm_gdb_name)

	printMes("********************* Completed Raster processing *********************")
	
	printMes("********************* Updating Metadata *********************")
	rasFile = os.path.join(fgdb_out_sgm, szm_gdb_name)
	rasIndex= [rasFile]
	
	UpdateMetadata(rasIndex, dirWEB, MetadataFolder, MetadataVersion, MetadataCalDate, MetadataPubDate, MetadataChangesDesc, CouncilDate)	

	printMes("********************* Zipping Raster FGDB *************************")
	# Paramaters of gdb for seamless map raster export
	tYear = datetime.datetime.strptime(MetadataPubDate, '%m/%d/%Y').year
	tMonth = datetime.datetime.strptime(MetadataPubDate, '%m/%d/%Y').month
	if len(str(tMonth))==1:
	 tMonth = "0" + str(tMonth)
		
	infile = fgdb_out_sgm
	web_out_sgm = os.path.join(dirWEB,'georeferencedzoningmaps_' + str(tYear) + str(tMonth) + '.zip')
	#web_out_sgm = os.path.join(dirWEB,'GeoreferencedNYCZoningMaps_fgdb.zip')
	outfile = web_out_sgm	

	def zipFileGeodatabase(inFileGeodatabase, newZipFN):
	 if not (os.path.exists(inFileGeodatabase)):
	  return False
	 
	 if (os.path.exists(newZipFN)):
	  os.remove(newZipFN)
	  
	 zipobj = zipfile.ZipFile(newZipFN,'w')
	 
	 for infile in glob.glob(inFileGeodatabase+"/*"):
	  zipobj.write(infile, os.path.basename(inFileGeodatabase)+"/"+os.path.basename(infile), zipfile.ZIP_DEFLATED)
	  printMes("Zipping: "+infile)
	  
	 zipobj.close()
	 return True
	
	printMes(infile)
	printMes(outfile)
	
	zipFileGeodatabase(infile,outfile)
	
	printMes("********************* Completed Zipping Raster FGDB *************************")

	#dir = get_install_directory()
	#xslt = dir + "Metadata/Stylesheets/ArcGIS.xsl"
	#remove_gp_history_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove geoprocessing history.xslt"
	#remove_gp_local_storage_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove local storage info.xslt"
	#remove_gp_thumbnail_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove thumbnail.xslt"
	#remove_gp_empty_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove empty elements.xslt"
	#remove_gp_pre94_xslt = dir + "Metadata\\Stylesheets\\gpTools\\remove pre94 metadata elements.xslt"
	#fgdb_meta_out = os.path.join(dirWEB,'scanned_geo_maps.xml')
	#fgdb_meta_out2 = os.path.join(dirWEB,'scanned_geo_maps2.xml')
	#fgdb_meta_out3 = os.path.join(dirWEB,'scanned_geo_maps3.xml')
	#fgdb_meta_out4 = os.path.join(dirWEB,'scanned_geo_maps4.xml')
	#fgdb_meta_out5 = os.path.join(dirWEB,'scanned_geo_maps5.xml')
	#fgdb_meta_out6 = os.path.join(dirWEB,'scanned_geo_maps6.xml')
	#raster_sgm = os.path.join(fgdb_out_sgm,'DZM_raster_maps')
	
##	arcpy.ExportXMLWorkspaceDocument_management(raster_sgm, fgdb_meta_out)
	#arcpy.XSLTransform_conversion(raster_sgm, xslt, fgdb_meta_out)
	#arcpy.ImportMetadata_conversion(fgdb_meta_out, "FROM_ARCGIS", raster_sgm)
	#arcpy.XSLTransform_conversion(raster_sgm, remove_gp_history_xslt, fgdb_meta_out2)
	#arcpy.ImportMetadata_conversion(fgdb_meta_out2, "FROM_ARCGIS", raster_sgm)
	#arcpy.XSLTransform_conversion(raster_sgm, remove_gp_local_storage_xslt, fgdb_meta_out3)
	#arcpy.ImportMetadata_conversion(fgdb_meta_out3, "FROM_ARCGIS", raster_sgm)
	#arcpy.XSLTransform_conversion(raster_sgm, remove_gp_thumbnail_xslt, fgdb_meta_out4)
	#arcpy.ImportMetadata_conversion(fgdb_meta_out4, "FROM_ARCGIS", raster_sgm)
	#arcpy.XSLTransform_conversion(raster_sgm, remove_gp_empty_xslt, fgdb_meta_out5)
	#arcpy.ImportMetadata_conversion(fgdb_meta_out5, "FROM_ARCGIS", raster_sgm)
	#arcpy.XSLTransform_conversion(fgdb_meta_out5, xslt, fgdb_meta_out6)
	#arcpy.ImportMetadata_conversion(fgdb_meta_out6, "FROM_ARCGIS", raster_sgm)

	#printMes("********************* Export Complete *************************")


	printMes("Minutes: " + str(time.clock()/60) + '\n')
	printMes("Zoning Districts: End processing")
	
except:
	type=None
	value=None
	tb=None
	limit=None
	import traceback, string
	type, value, tb = sys.exc_info()
	err_msg = "Traceback (innermost last):\n"
	list = traceback.format_tb(tb, limit) + traceback.format_exception_only(type, value)
	err_msg = err_msg + "%-20s %s" % (string.join(list[:-1], ""),list[-1])
	arcpy.AddError(err_msg)
	arcpy.AddError(arcpy.GetMessages(2)+'\n')	


from pathlib import Path
import shapely
from .common import DataError


def field_types(rows):
    result={}
    for name in sorted({k for r in rows for k in r['properties']}):
        values=[r['properties'].get(name) for r in rows if r['properties'].get(name) is not None]
        if values and all(isinstance(v,(int,bool)) for v in values): kind='LONG'
        elif values and all(isinstance(v,(int,float)) for v in values): kind='DOUBLE'
        elif not values and ('PCT' in name or 'PRZEWAGA' in name): kind='DOUBLE'
        elif not values and 'GLOSY' in name: kind='LONG'
        else: kind='TEXT'
        result[name]=kind
    return result


def write_ogr(path,rows,crs,rounds):
    from osgeo import ogr,osr
    from pyproj import CRS
    from .elections import vote_fields
    ogr.UseExceptions()
    if path.exists(): raise FileExistsError(path)
    ds=ogr.GetDriverByName('GPKG').CreateDataSource(str(path))
    sr=osr.SpatialReference(); sr.ImportFromWkt(CRS.from_user_input(crs).to_wkt())
    types={'LONG':ogr.OFTInteger64,'DOUBLE':ogr.OFTReal,'TEXT':ogr.OFTString}
    layers=[('obwody_wyniki',rows,True)]
    for t,table in enumerate(rounds,1):
        values=[]
        for r in table['rows']:
            props={k:v for k,v in r.items() if k!='votes'}; props.update(vote_fields(r,t))
            values.append(dict(properties=props))
        layers.append((f'protokoły_T{t}',values,False))
    for name,values,spatial in layers:
        layer=ds.CreateLayer(name,sr if spatial else None,ogr.wkbMultiPolygon if spatial else ogr.wkbNone)
        schema=field_types(values)
        for field,kind in schema.items(): layer.CreateField(ogr.FieldDefn(field,types[kind]))
        layer.StartTransaction()
        for row in values:
            f=ogr.Feature(layer.GetLayerDefn())
            for k,kind in schema.items():
                v=row['properties'].get(k)
                if v is not None: f.SetField(k,str(v) if kind=='TEXT' else (int(v) if kind=='LONG' else v))
            if spatial:
                g=ogr.CreateGeometryFromWkb(row['geometry'].wkb)
                f.SetGeometry(ogr.ForceToMultiPolygon(g))
            layer.CreateFeature(f)
        layer.CommitTransaction()
    ds=None
    check=ogr.Open(str(path)); layer=check.GetLayerByName('obwody_wyniki')
    if layer.GetFeatureCount()!=len(rows): raise DataError('Niezgodna liczba rekordów po eksporcie.')
    return str(path)


def write_arcpy(directory,rows,crs,rounds,gpkg=False):
    import arcpy
    from .elections import vote_fields
    from pyproj import CRS
    gdb=directory/'wyniki.gdb'
    if gdb.exists(): raise FileExistsError(gdb)
    arcpy.management.CreateFileGDB(str(directory),gdb.name)
    sr=arcpy.SpatialReference(); sr.loadFromString(CRS.from_user_input(crs).to_wkt(version='WKT1_ESRI'))
    target=str(gdb/'obwody_wyniki')
    arcpy.management.CreateFeatureclass(str(gdb),'obwody_wyniki','POLYGON',spatial_reference=sr)

    def populate(path,values,spatial):
        schema=field_types(values)
        for name,kind in schema.items():
            if arcpy.ValidateFieldName(name,str(gdb))!=name: raise DataError(f'Niedozwolona nazwa pola: {name}')
            if kind=='TEXT': arcpy.management.AddField(path,name,kind,field_length=max(64,max((len(str(r['properties'].get(name) or '')) for r in values),default=0)))
            else: arcpy.management.AddField(path,name,kind)
        fields=list(schema)+(['SHAPE@'] if spatial else [])
        with arcpy.da.InsertCursor(path,fields) as cursor:
            for row in values:
                vals=[row['properties'].get(k) for k in schema]
                vals=[str(v) if schema[k]=='TEXT' and v is not None else v for k,v in zip(schema,vals)]
                if spatial: vals.append(arcpy.FromWKB(bytearray(row['geometry'].wkb),sr))
                cursor.insertRow(vals)

    populate(target,rows,True)
    for t,table in enumerate(rounds,1):
        name=f'protokoly_T{t}'; path=str(gdb/name)
        arcpy.management.CreateTable(str(gdb),name)
        values=[]
        for r in table['rows']:
            props={k:v for k,v in r.items() if k!='votes'}; props.update(vote_fields(r,t)); values.append(dict(properties=props))
        populate(path,values,False)
    if int(arcpy.management.GetCount(target)[0])!=len(rows): raise DataError('Błąd liczby rekordów eksportu.')
    if gpkg:
        package=directory/'wyniki.gpkg'
        arcpy.management.CreateSQLiteDatabase(str(package),'GEOPACKAGE')
        arcpy.management.CopyFeatures(target,str(package/'obwody_wyniki'))
    return target


def add_to_project(target,rows,rounds,directory,project_path='CURRENT'):
    import arcpy
    from .cartography import color,label
    project=arcpy.mp.ArcGISProject(project_path)
    map_obj=project.createMap('PRG Wybory','MAP')
    map_obj.spatialReference=arcpy.Describe(target).spatialReference
    map_obj.defaultCamera.setExtent(arcpy.Describe(target).extent)
    for t in (1,2):
        layer=map_obj.addDataFromPath(target); layer.name=f'{"I" if t==1 else "II"} tura — lider'
        sym=layer.symbology; sym.updateRenderer('UniqueValueRenderer'); sym.renderer.fields=[f'T{t}_STYL']
        for group in sym.renderer.groups:
            for item in group.items:
                value=item.values[0][0]; leader,cat=value.rsplit('_',1); cat=int(cat)
                rgb=color(leader,cat)
                item.symbol.color={'RGB':[int(rgb[i:i+2],16) for i in (1,3,5)]+[100]}
                item.symbol.outlineColor={'RGB':[255,255,255,100]}; item.symbol.outlineWidth=.25
                item.label=label(leader,cat,rounds[t-1]['candidates'])
        layer.symbology=sym; layer.visible=t==1
        arcpy.management.SaveToLayerFile(layer,str(directory/f'kartogram_T{t}.lyrx'),'RELATIVE')
    project.saveACopy(str(directory/'wybory.aprx'))
    return str(directory/'wybory.aprx')

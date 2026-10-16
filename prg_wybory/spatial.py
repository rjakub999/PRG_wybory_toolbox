from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict
import shapely
from shapely.geometry import shape, mapping
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import CRS, Transformer
from .common import DataError, integer, teryt, key, save_json


def parts(geometry, kind):
    if geometry.geom_type==kind: return [geometry]
    return [p for child in getattr(geometry,'geoms',[]) for p in parts(child,kind)]


def metric_crs(value):
    crs = CRS.from_user_input(value)
    if not crs.is_projected or any(abs(a.unit_conversion_factor-1)>1e-9 for a in crs.axis_info[:2]):
        raise DataError('Obliczenia wymagają projektowanego CRS w metrach.')
    return crs


def read_features(path, target_crs, layer=None, source_crs=None, io_backend='arcpy'):
    target = metric_crs(target_crs)
    path = str(path)
    rows = []
    if Path(path).suffix.lower() in ('.geojson', '.json'):
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        # RFC 7946 GeoJSON is WGS84 unless explicitly overridden / legacy CRS exists.
        source = CRS.from_user_input(source_crs or data.get('crs',{}).get('properties',{}).get('name',4326))
        rows = [dict(geometry=shape(f['geometry']) if f.get('geometry') else None, properties=dict(f['properties'] or {})) for f in data['features']]
    elif io_backend == 'arcpy':
        import arcpy
        dataset = str(Path(path)/layer) if layer else path
        sr = arcpy.Describe(dataset).spatialReference
        if not source_crs and sr.name == 'Unknown':
            raise DataError(f'Nieznany CRS: {dataset}')
        source = CRS.from_user_input(source_crs or sr.exportToString().split(';')[0])
        fields = [f.name for f in arcpy.ListFields(dataset) if f.type not in ('Geometry','Blob','Raster')]
        with arcpy.da.SearchCursor(dataset,fields+['SHAPE@WKB']) as cursor:
            for row in cursor:
                rows.append(dict(properties=dict(zip(fields,row[:-1])),geometry=shapely.from_wkb(bytes(row[-1])) if row[-1] else None))
    elif io_backend == 'ogr':
        from osgeo import ogr
        ogr.UseExceptions()
        ds = ogr.Open(path)
        if ds is None: raise DataError(f'Nie można otworzyć {path}')
        if not layer and ds.GetLayerCount()!=1: raise DataError('Podaj layer dla wielowarstwowego źródła.')
        lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
        if lyr is None: raise DataError(f'Brak warstwy {layer}')
        sr = lyr.GetSpatialRef()
        if not source_crs and sr is None: raise DataError('Nieznany CRS źródła.')
        source = CRS.from_user_input(source_crs or sr.ExportToWkt())
        for f in lyr:
            geom = f.GetGeometryRef()
            rows.append(dict(properties=dict(f.items()),geometry=shapely.from_wkb(bytes(geom.ExportToWkb())) if geom else None))
    else:
        raise DataError(f'Nieznany adapter wejścia: {io_backend}')
    if not rows: raise DataError(f'Pusta warstwa: {path}')
    from datetime import datetime,date
    for row in rows:
        for k,v in row['properties'].items():
            if isinstance(v,(datetime,date)): row['properties'][k]=v.isoformat()
    if source != target:
        converter = Transformer.from_crs(source,target,always_xy=True,allow_ballpark=False)
        for row in rows:
            if row['geometry'] is not None:
                row['geometry'] = transform(converter.transform,row['geometry'])
    if any(r['geometry'] is None or r['geometry'].is_empty for r in rows):
        raise DataError('Warstwa zawiera puste geometrie.')
    return rows


def save_features(path, rows, crs):
    # Internal checkpoints carry explicit WKT; not advertised as RFC 7946 GeoJSON.
    save_json(path,dict(crs=CRS.from_user_input(crs).to_wkt(),features=[
        dict(properties=r['properties'],geometry=mapping(r['geometry'])) for r in rows]))
    # A separate RFC 7946 sidecar makes diagnostics inspectable in GIS.
    converter=Transformer.from_crs(crs,4326,always_xy=True,allow_ballpark=False)
    save_json(Path(path).with_suffix('.geojson'),dict(type='FeatureCollection',features=[
        dict(type='Feature',properties=r['properties'],geometry=mapping(transform(converter.transform,r['geometry']))) for r in rows]))


def load_features(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    return [dict(properties=f['properties'],geometry=shape(f['geometry'])) for f in data['features']], data['crs']


def prepare_boundaries(rows, city, number_field, teryt_field=None):
    grouped=defaultdict(list)
    for row in rows:
        p,g=row['properties'],row['geometry']
        if teryt_field and teryt(p[teryt_field]) != teryt(city): continue
        if g.geom_type not in ('Polygon','MultiPolygon') or not g.is_valid:
            raise DataError(f'Niepoprawny poligon: {p.get(number_field)}: {shapely.is_valid_reason(g)}')
        number=integer(p.get(number_field),'numer poligonu',1)
        grouped[number].append(g)
    if not grouped: raise DataError('Brak poligonów wybranego miasta.')
    return [dict(geometry=shapely.union_all(geoms),properties=dict(ID_OBWODU=key(city,n),
        TERYT=teryt(city),NR_KOMISJI=n,LICZBA_CZESCI_ZRODLOWYCH=len(geoms))) for n,geoms in sorted(grouped.items())]


def audit(rows, boundary=None):
    geoms=[r['geometry'] for r in rows]
    invalid=[i for i,g in enumerate(geoms) if not g.is_valid or g.is_empty]
    if invalid: return dict(invalid=invalid,overlap_area_m2=None)
    union=shapely.union_all(geoms)
    overlaps=[]; tree=STRtree(geoms)
    for i,g in enumerate(geoms):
        for j in tree.query(g,predicate='intersects'):
            if int(j)>i:
                area=g.intersection(geoms[int(j)]).area
                if area>1e-6: overlaps.append(dict(a=i,b=int(j),area_m2=area))
    holes=sum(shapely.Polygon(r).area for p in shapely.get_parts(union) if p.geom_type=='Polygon' for r in p.interiors)
    return dict(invalid=[],features=len(rows),area_m2=union.area,
        overlap_area_m2=max(0,sum(g.area for g in geoms)-union.area),overlaps=overlaps,
        interior_holes_m2=holes,missing_area_m2=boundary.difference(union).area if boundary is not None else None,
        outside_area_m2=union.difference(boundary).area if boundary is not None else None)

"""Open-source algorithms, independent of ArcGIS license level."""
from __future__ import annotations
from collections import Counter, defaultdict
import numpy as np
import shapely
from shapely.geometry import MultiPoint, Point, shape
from shapely.strtree import STRtree
from scipy.spatial import cKDTree
from .common import DataError


class PythonBackend:
    def neighbors(self, points, k=5, max_distance=250, min_neighbors=3, minimum_share=.6, apply=False):
        if not 1<=min_neighbors<=k or max_distance<=0 or not .5<minimum_share<=1:
            raise DataError('Niepoprawne parametry sąsiedztwa.')
        if any(p['geometry'].geom_type!='Point' for p in points): raise DataError('Sąsiedztwo wymaga punktów.')
        output=[dict(geometry=p['geometry'],properties=dict(p['properties'])) for p in points]
        # Reference set is frozen. Newly inferred points cannot vote in this run.
        by_city=defaultdict(list)
        for i,p in enumerate(points):
            a=p['properties']
            if a.get('NR_KOMISJI') is not None and a.get('STATUS') not in ('KONFLIKT','SASIEDZTWO','DO_KONTROLI'):
                by_city[a['TERYT']].append(i)
        trees={c:cKDTree([(points[i]['geometry'].x,points[i]['geometry'].y) for i in indices]) for c,indices in by_city.items()}
        for result in output:
            props=result['properties']; original=props.get('NR_KOMISJI')
            props['NR_PIERWOTNY']=original
            if original is not None or props.get('STATUS')=='KONFLIKT': continue
            city=props['TERYT']; geom=result['geometry']
            props.update(PROPONOWANY_NR=None,PEWNOSC=None,SASIEDZI='',STATUS='BRAK_SASIADOW')
            if city not in trees: continue
            indices=by_city[city]; tree=trees[city]
            distances, near=tree.query([geom.x,geom.y],k=min(k+1,len(indices)),distance_upper_bound=max_distance)
            pairs=[(float(d),indices[int(j)]) for d,j in zip(np.atleast_1d(distances),np.atleast_1d(near)) if np.isfinite(d)]
            if len(pairs)>k and abs(pairs[k][0]-pairs[k-1][0])<1e-8:
                props['STATUS']='REMIS_ODLEGLOSCI'; continue
            pairs=pairs[:k]
            props['SASIEDZI']='|'.join(f'{points[i]["properties"]["ID_ADRESU"]}:{d:.3f}' for d,i in pairs)
            props['LICZBA_SASIADOW']=len(pairs)
            if len(pairs)<min_neighbors: props['STATUS']='ZA_MALO_SASIADOW'; continue
            votes=Counter(points[i]['properties']['NR_KOMISJI'] for d,i in pairs)
            ranked=votes.most_common(); top=ranked[0][1]; share=top/len(pairs)
            props['PEWNOSC']=share
            if len(ranked)>1 and ranked[1][1]==top: props['STATUS']='REMIS_GLOSOW'; continue
            props['PROPONOWANY_NR']=ranked[0][0]
            if share<minimum_share: props['STATUS']='SLABA_WIEKSZOSC'; continue
            props['STATUS']='PROPOZYCJA'
            if apply: props.update(NR_KOMISJI=ranked[0][0],STATUS='SASIEDZTWO')
        return output

    def voronoi(self, points, boundary):
        if boundary.is_empty or not boundary.is_valid or boundary.geom_type not in ('Polygon','MultiPolygon'):
            raise DataError('Wymagana poprawna granica obszaru.')
        coords={}
        for p in points:
            g,a=p['geometry'],p['properties']
            if g.geom_type!='Point': raise DataError('Voronoi wymaga geometrii Point.')
            if a.get('NR_KOMISJI') is None: raise DataError('Voronoi: pozostały nieprzypisane adresy; najpierw rozstrzygnij ich status.')
            if not boundary.covers(g): raise DataError(f'Adres poza granicą miasta: {a.get("ID_ADRESU")}')
            xy=(g.x,g.y); label=(a['TERYT'],a['NR_KOMISJI'])
            if xy in coords and coords[xy]!=label: raise DataError(f'Sprzeczne komisje w jednej lokalizacji: {xy}')
            coords[xy]=label
        if not coords: raise DataError('Brak punktów do Voronoi.')
        sites=[Point(xy) for xy in coords]; tree=STRtree(sites); labels=list(coords.values())
        cells=[boundary] if len(sites)==1 else list(shapely.get_parts(shapely.voronoi_polygons(MultiPoint(sites),extend_to=boundary.envelope)))
        grouped=defaultdict(list)
        for cell in cells:
            found=tree.query(cell,predicate='covers')
            if len(found)!=1: raise DataError('Nie można jednoznacznie powiązać komórki Voronoi z punktem.')
            clipped=cell.intersection(boundary)
            if not clipped.is_empty: grouped[labels[int(found[0])]].append(clipped)
        rows=[dict(geometry=shapely.union_all(cells),properties=dict(TERYT=city,NR_KOMISJI=number,ID_OBWODU=f'{city}_{number}',METODA='VORONOI')) for (city,number),cells in sorted(grouped.items())]
        from .spatial import audit
        check=audit(rows,boundary)
        if check['overlap_area_m2']>1e-4 or check['missing_area_m2']>1e-4 or check['outside_area_m2']>1e-4:
            raise DataError(f'Niepoprawne pokrycie Voronoi: {check}')
        return rows

    def raster(self, path, boundary, seeds, crs, target_rgb=(220,0,0), color_tolerance=100,
               closing_pixels=1, min_seeds=3, minimum_share=.75, boundary_margin=2,
               max_pixels=25000000):
        import rasterio
        from rasterio.features import geometry_mask, shapes
        from rasterio.warp import transform_geom
        from scipy import ndimage as nd
        from pyproj import CRS, Transformer
        from shapely.ops import transform
        if min_seeds<1 or not .5<minimum_share<=1 or closing_pixels<0 or boundary_margin<0:
            raise DataError('Niepoprawne parametry rekonstrukcji rastra.')
        with rasterio.open(path) as src:
            if src.crs is None: raise DataError('Raster nie ma CRS/georeferencji.')
            if src.width*src.height>max_pixels: raise DataError('Raster przekracza limit max_pixels; przygotuj mniejszy wycinek.')
            if src.count<3: raise DataError('Wymagany raster RGB.')
            affine=src.transform
            mask_geometry=transform_geom(CRS.from_user_input(crs).to_wkt(),src.crs,shapely.geometry.mapping(boundary))
            from shapely.geometry import box
            if not box(*src.bounds).covers(shape(mask_geometry)):
                raise DataError('Raster nie obejmuje całego obszaru analizy.')
            inside=geometry_mask([mask_geometry],(src.height,src.width),affine,invert=True)
            valid=src.dataset_mask()>0
            if np.any(inside & ~valid): raise DataError('NoData wewnątrz obszaru; nie można odtworzyć pełnego pokrycia.')
            image=src.read([1,2,3]).astype('float32')
            color=np.asarray(target_rgb,dtype='float32')[:,None,None]
            barrier=np.sqrt(np.sum((image-color)**2,axis=0))<=color_tolerance
            barrier &= inside
            if closing_pixels:
                barrier=nd.binary_closing(barrier | ~inside,iterations=int(closing_pixels),border_value=1) & inside
            labels,count=nd.label(inside & ~barrier)
            if count<2: raise DataError('Nie wykryto podziału rastra. Sprawdź kolor, skalę i domknięcie linii.')
            # Restore line pixels by nearest interior region; never fill NoData.
            nearest=nd.distance_transform_edt(labels==0,return_distances=False,return_indices=True)
            filled=labels[tuple(nearest)].astype('int32'); filled[~inside]=0
            convert=Transformer.from_crs(src.crs,crs,always_xy=True).transform
            polygons=[(int(n),transform(convert,shape(g)).intersection(boundary))
                      for g,n in shapes(filled,mask=inside,transform=affine) if n]
        grouped=defaultdict(list)
        for n,g in polygons: grouped[n].append(g)
        rows=[]
        for n,parts in sorted(grouped.items()):
            geom=shapely.union_all(parts)
            votes=Counter(p['properties']['NR_KOMISJI'] for p in seeds
                if p['properties'].get('NR_KOMISJI') is not None and geom.contains(p['geometry'])
                and p['geometry'].distance(geom.boundary)>boundary_margin)
            ranked=votes.most_common(); total=sum(votes.values()); number=None; confidence=None
            if ranked:
                confidence=ranked[0][1]/total
                if ranked[0][1]>=min_seeds and confidence>=minimum_share and (len(ranked)==1 or ranked[0][1]>ranked[1][1]):
                    number=ranked[0][0]
            rows.append(dict(geometry=geom,properties=dict(REGION=n,NR_KOMISJI=number,
                PEWNOSC=confidence,LICZBA_PUNKTOW=total,STATUS='ROZPOZNANY' if number is not None else 'DO_KONTROLI',METODA='RASTER_RGB')))
        return rows

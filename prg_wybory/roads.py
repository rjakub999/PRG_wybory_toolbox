import shapely
from shapely.strtree import STRtree
from .common import DataError
from .road_geometry import parts, shared_chains, road_route, rebuild_pair, check_addresses


def fit(rows, roads, points, max_distance=30, min_length=40, min_support=.7, angle=30):
    if max_distance<=0 or min_length<=0 or not 0<min_support<=1 or not 0<angle<90:
        raise DataError('Niepoprawne parametry dopasowania ulic.')
    geoms=[r['geometry'] for r in rows]
    if not shapely.coverage_is_valid(geoms):
        raise DataError('Dopasowanie wymaga poprawnego pokrycia wejściowego. Sprawdź raport topologii.')
    lines=[p for r in roads for p in parts(r['geometry'],'LineString') if p.length>0]
    if not lines: raise DataError('Brak linii ulic.')
    tree=STRtree(lines); point_geoms=[p['geometry'] for p in points]; ptree=STRtree(point_geoms)
    report=[]
    # Recompute each pair intersection after accepted edits; never use stale chains.
    pairs=sorted({(i,j) for i,j,c in shared_chains(geoms)})
    for i,j in pairs:
        chains=parts(geoms[i].boundary.intersection(geoms[j].boundary),'LineString')
        for chain in chains:
            if chain.length<min_length or chain.is_ring: continue
            row=dict(A=rows[i]['properties']['NR_KOMISJI'],B=rows[j]['properties']['NR_KOMISJI'],STATUS='ZACHOWANO',DLUGOSC_M=chain.length)
            try:
                replacement,distance=road_route(chain,lines,tree,max_distance,min_support=min_support,angle=angle)
                a,b=geoms[i],geoms[j]; na,nb=rebuild_pair(a,b,chain,replacement)
                check_addresses(a,b,na,nb,(i,j),point_geoms,None,ptree)
                candidate=list(geoms); candidate[i]=na; candidate[j]=nb
                if not shapely.coverage_is_valid(candidate): raise ValueError('ZMIANA_TOPOLOGII')
                geoms=candidate; row.update(STATUS='DOPASOWANO',PRZESUNIECIE_M=float(distance))
            except ValueError as exc:
                row['POWOD']=str(exc)
            report.append(row)
    return [dict(properties=dict(r['properties']),geometry=g) for r,g in zip(rows,geoms)],report

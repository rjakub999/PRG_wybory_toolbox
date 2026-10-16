from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import sys
import traceback
import uuid
import shapely
from . import __version__
from .common import DataError, load_config, resolve, save_json, save_csv, key, integer
from .spatial import read_features, save_features, load_features, prepare_boundaries, audit, metric_crs
from .backends import backend, OPERATIONS
from . import elections

STAGES=('boundaries','results','join','validate','export','maps','project')


def diagnostics():
    packages={}
    for name in ('shapely','scipy','numpy','pyproj','matplotlib','openpyxl','rasterio','networkx'):
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name]=None
    try:
        import arcpy
        arcgis=dict(version=arcpy.GetInstallInfo().get('Version'),license=arcpy.ProductInfo())
    except (ImportError,RuntimeError) as exc:
        arcgis=dict(error=str(exc))
    return dict(toolbox=__version__,python=sys.version,packages=packages,arcgis=arcgis,
        backends={'python':'implemented','esri':'specification_only'})


def source_fingerprints(cfg):
    result={}
    specs=[cfg.get(k) for k in ('polygons','boundary','addresses','roads','descriptions','raster')]
    specs+=cfg.get('rounds',[])
    for spec in specs:
        if not spec or not spec.get('path'): continue
        p=Path(resolve(cfg,spec['path']))
        # A feature class is a logical path within a GDB; hash its physical database.
        actual=p
        if not actual.exists():
            candidates=[parent for parent in p.parents if parent.suffix.lower()=='.gdb']
            if candidates: actual=candidates[0]
        if not actual.exists(): raise DataError(f'Brak źródła: {p}')
        if actual.is_dir():
            entries=[(str(f.relative_to(actual)),f.stat().st_size,f.stat().st_mtime_ns) for f in sorted(actual.rglob('*')) if f.is_file() and not f.name.endswith('.lock')]
            digest=hashlib.sha256(json.dumps(entries).encode()).hexdigest()
            method='directory_size_mtime'
        else:
            digest=hashlib.sha256(actual.read_bytes()).hexdigest(); method='sha256'
            if actual.suffix.lower()=='.shp':
                for suffix in ('.shx','.dbf','.prj','.cpg'):
                    companion=actual.with_suffix(suffix)
                    if companion.exists(): result[str(companion)]={'method':'sha256','value':hashlib.sha256(companion.read_bytes()).hexdigest()}
        result[str(p)]={'method':method,'value':digest}
    return result


def preflight(cfg):
    crs=metric_crs(cfg.get('crs','EPSG:2180'))
    cfg['crs']=crs.to_string()
    if cfg.get('mode','polygons') not in ('polygons','addresses','raster'): raise DataError('Nieznany mode.')
    if len(cfg.get('rounds',[]))!=2: raise DataError('Podaj dokładnie dwie tury w rounds.')
    if int(shapely.__version__.split('.')[0])<2 or tuple(map(int,shapely.__version__.split('.')[:2]))<(2,1):
        raise DataError('Wymagane Shapely >= 2.1.')
    # A reserved backend must fail before any processing, never silently fallback.
    for operation in OPERATIONS: backend(cfg,operation)
    report=diagnostics()
    needed=['shapely','pyproj','numpy','scipy','matplotlib']
    if cfg.get('mode')=='raster': needed.append('rasterio')
    if cfg.get('roads'): needed.append('networkx')
    if any(str(s.get('path','')).lower().endswith('.xlsx') for s in cfg['rounds']+[cfg.get('descriptions',{})]): needed.append('openpyxl')
    missing=[p for p in needed if not report['packages'][p]]
    if missing: raise DataError('Brak bibliotek: '+', '.join(missing))
    if cfg.get('io_backend','arcpy')=='arcpy' and 'error' in report['arcgis']:
        raise DataError('Uruchom wewnątrz ArcGIS Pro z aktywną licencją: '+report['arcgis']['error'])
    return report


def read(cfg,spec):
    if not spec or not spec.get('path'): raise DataError('Brak opisu źródła path.')
    return read_features(resolve(cfg,spec['path']),cfg['crs'],spec.get('layer'),spec.get('source_crs'),cfg.get('io_backend','arcpy'))


def stage_boundaries(cfg,out):
    mode=cfg.get('mode','polygons'); city=cfg['teryt']; points=None
    if mode=='polygons':
        spec=cfg['polygons']
        source=read(cfg,spec); repairs=[]
        for r in source:
            geom=r['geometry']
            if geom.is_valid: continue
            report=dict(number=r['properties'].get(spec['number_field']),reason=shapely.is_valid_reason(geom),area_before=geom.area,applied=False)
            repairs.append(report)
            if spec.get('repair_invalid',False):
                valid=shapely.make_valid(geom)
                from .spatial import parts
                polygons=parts(valid,'Polygon')
                if not polygons: raise DataError('Naprawa nie zwróciła poligonów.')
                repaired=shapely.union_all(polygons)
                report.update(applied=True,area_after=repaired.area,area_change_m2=repaired.area-geom.area,
                    discarded_nonpolygon_parts=valid.geom_type=='GeometryCollection')
                if abs(repaired.area-geom.area)>spec.get('max_repair_area_change_m2',1):
                    save_json(out/'01_naprawy_geometrii.json',repairs)
                    raise DataError('Naprawa zmienia powierzchnię powyżej progu; wymagana kontrola ręczna.')
                r['geometry']=repaired
        save_json(out/'01_naprawy_geometrii.json',repairs)
        rows=prepare_boundaries(source,city,spec['number_field'],spec.get('teryt_field'))
    else:
        boundary=shapely.union_all([r['geometry'] for r in read(cfg,cfg['boundary'])])
        if boundary.geom_type not in ('Polygon','MultiPolygon') or not boundary.is_valid: raise DataError('Niepoprawna granica miasta.')
        from .addresses import prepare_points,assign
        points=prepare_points(read(cfg,cfg['addresses']),city,cfg['addresses'].get('fields',{}))
        if cfg.get('descriptions'):
            d=cfg['descriptions']
            points,expanded,report=assign(points,resolve(cfg,d['path']),city,d.get('mapping'))
            save_json(out/'01_granice_rozbite.json',expanded); save_json(out/'01_reguly_raport.json',report)
            save_csv(out/'01_granice_rozbite.csv',expanded); save_csv(out/'01_reguly_raport.csv',report)
            save_features(out/'01_adresy_reguly.json',points,cfg['crs'])
            if cfg.get('strict_rules',True) and any(r['STATUS']!='PRG' for r in report):
                raise DataError('Reguły adresowe wymagają kontroli: 01_reguly_raport.json. Uzupełnij źródło przed ponownym przebiegiem.')
        if mode=='addresses':
            options=cfg.get('neighbors',{})
            if options.get('enabled',False):
                points=backend(cfg,'neighbors').neighbors(points,**{k:v for k,v in options.items() if k!='enabled'})
            save_features(out/'01_adresy.json',points,cfg['crs'])
            rows=backend(cfg,'voronoi').voronoi(points,boundary)
        else:
            spec=cfg['raster']
            regions=backend(cfg,'raster').raster(resolve(cfg,spec['path']),boundary,points,cfg['crs'],**spec.get('options',{}))
            for r in regions:
                a=r['properties']; override=spec.get('assignments',{}).get(str(a['REGION']))
                if override is not None: a.update(NR_KOMISJI=integer(override,minimum=1),STATUS='RECZNE_PRZYPISANIE')
            save_features(out/'01_regiony_rastra.json',regions,cfg['crs'])
            save_json(out/'01_raster_topologia.json',audit(regions,boundary))
            if any(r['properties']['NR_KOMISJI'] is None for r in regions):
                raise DataError('Nierozpoznane regiony rastra: sprawdź 01_regiony_rastra.json i podaj raster.assignments albo popraw punkty referencyjne.')
            for r in regions: r['properties']['TERYT']=city
            rows=prepare_boundaries(regions,city,'NR_KOMISJI')
            for r in rows: r['properties']['METODA']='RASTER_RGB'
            from shapely.strtree import STRtree
            tree=STRtree([r['geometry'] for r in rows]); address_check=[]
            for p in points:
                hits=tree.query(p['geometry'],predicate='intersects')
                found=rows[int(hits[0])]['properties']['NR_KOMISJI'] if len(hits)==1 else None
                old=p['properties'].get('NR_KOMISJI')
                address_check.append(dict(ID_ADRESU=p['properties']['ID_ADRESU'],NR_PIERWOTNY=old,
                    NR_Z_RASTRA=found,STATUS='ZGODNY' if found==old and found is not None else 'DO_KONTROLI'))
            save_json(out/'01_adresy_wzgled_rastra.json',address_check)
        check=audit(rows,boundary)
        if check['missing_area_m2']>1e-3 or check['overlap_area_m2']>1e-3: raise DataError(f'Niekompletna rekonstrukcja: {check}')
    if cfg.get('roads'):
        from .roads import fit
        if points is None:
            from .addresses import prepare_points
            if not cfg.get('addresses'): raise DataError('Dopasowanie do ulic wymaga punktów kontrolnych addresses.')
            points=prepare_points(read(cfg,cfg['addresses']),city,cfg['addresses'].get('fields',{}))
        rows,report=fit(rows,read(cfg,cfg['roads']),points,**cfg['roads'].get('options',{}))
        save_json(out/'01_dopasowanie_ulic.json',report)
    for r in rows: r['properties']['ELEKCJA']=cfg['election']
    save_features(out/'01_obwody.json',rows,cfg['crs'])
    check=audit(rows); save_json(out/'01_topologia.json',check)
    return check


def stage_results(cfg,out):
    rounds=[elections.prepare(resolve(cfg,s['path']),cfg['teryt'],s.get('mapping')) for s in cfg['rounds']]
    for t,table in enumerate(rounds,1): save_json(out/f'02_wyniki_T{t}.json',table)
    return {str(t):{'wszystkie':len(r['rows']),'stale':sum(x['STALY'] for x in r['rows']),'odrebne':sum(not x['STALY'] for x in r['rows'])} for t,r in enumerate(rounds,1)}


def get_rounds(out):
    return [json.loads((out/f'02_wyniki_T{t}.json').read_text(encoding='utf-8')) for t in (1,2)]


def stage_join(cfg,out):
    rows,crs=load_features(out/'01_obwody.json'); rounds=get_rounds(out)
    joined=elections.join(rows,rounds)
    save_features(out/'03_obwody_wyniki.json',joined,crs)
    return {'features':len(joined)}


def stage_validate(cfg,out):
    rows,crs=load_features(out/'03_obwody_wyniki.json'); original,_=load_features(out/'01_obwody.json')
    original={r['properties']['ID_OBWODU']:r['geometry'] for r in original}
    rounds=get_rounds(out); checks={'geometrie_bez_zmian':True,'tury':{},'topologia':audit(rows)}
    for r in rows:
        a=r['properties']
        if not r['geometry'].equals_exact(original[a['ID_OBWODU']],0): raise DataError('Geometria zmieniła się przy złączeniu.')
        for t,table in enumerate(rounds,1):
            expected=next(x for x in table['rows'] if x['ID_OBWODU']==a['ID_OBWODU'])
            if any(a[f'T{t}_GLOSY_{c}']!=v for c,v in expected['votes'].items()): raise DataError('Niezgodność głosów po złączeniu.')
            valid=a[f'T{t}_GLOSY_WAZNE']
            if valid and abs(sum(a[f'T{t}_PCT_{c}'] for c in table['candidates'])-100)>1e-7: raise DataError('Udziały nie sumują się do 100%.')
    for t,table in enumerate(rounds,1):
        checks['tury'][t]={'obwody':len(rows),'glosy_wazne':sum(r['properties'][f'T{t}_GLOSY_WAZNE'] for r in rows),
            'kandydaci':{c:sum(r['properties'][f'T{t}_GLOSY_{c}'] for r in rows) for c in table['candidates']}}
    save_json(out/'04_kontrola.json',checks)
    if checks['topologia']['invalid']: raise DataError('Niepoprawne geometrie.')
    return checks


def stage_export(cfg,out):
    rows,crs=load_features(out/'03_obwody_wyniki.json'); rounds=get_rounds(out)
    from .export import write_ogr,write_arcpy
    target=write_arcpy(out,rows,crs,rounds,cfg.get('export_gpkg',False)) if cfg.get('io_backend','arcpy')=='arcpy' else write_ogr(out/'wyniki.gpkg',rows,crs,rounds)
    save_json(out/'05_eksport.json',{'target':target}); return {'target':target}


def stage_maps(cfg,out):
    from .cartography import export_maps
    rows,crs=load_features(out/'03_obwody_wyniki.json')
    summary=export_maps(rows,get_rounds(out),out,cfg['city'],cfg['election'],cfg['crs'])
    save_json(out/'06_kartogramy.json',summary); return summary


def stage_project(cfg,out):
    if not cfg.get('add_to_project',True) or cfg.get('io_backend','arcpy')!='arcpy':
        return {'status':'pominięto zgodnie z konfiguracją / adapterem CLI'}
    from .export import add_to_project
    rows,crs=load_features(out/'03_obwody_wyniki.json')
    target=json.loads((out/'05_eksport.json').read_text())['target']
    return {'project':add_to_project(target,rows,get_rounds(out),out,cfg.get('project','CURRENT'))}


def run(config_path,through='all',resume=None,log=print):
    cfg=load_config(config_path); environment=preflight(cfg)
    provenance=source_fingerprints(cfg)
    signature=hashlib.sha256(json.dumps(dict(config={k:v for k,v in cfg.items() if k!='_config_dir'},sources=provenance,version=__version__),sort_keys=True).encode()).hexdigest()
    if through!='all' and through not in STAGES: raise DataError('Nieznany etap: '+through)
    if resume:
        out=Path(resume).resolve()
        manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        if manifest['signature']!=signature: raise DataError('Zmieniła się konfiguracja lub źródła. Rozpocznij nowy przebieg.')
        for file,digest in manifest.get('checkpoint_hashes',{}).items():
            if not (out/file).exists() or hashlib.sha256((out/file).read_bytes()).hexdigest()!=digest:
                raise DataError('Zmieniono plik etapu: '+file)
    else:
        parent=Path(resolve(cfg,cfg.get('output','wyniki')))
        out=parent/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
        out.mkdir(parents=True,exist_ok=False)
        manifest=dict(version=__version__,signature=signature,sources=provenance,environment=environment,
            started=datetime.now(timezone.utc).isoformat(),stages={},checkpoint_hashes={})
        save_json(out/'config.json',cfg)
    save_json(out/'manifest.json',manifest)
    log('Wyniki: '+str(out))
    until=len(STAGES) if through=='all' else STAGES.index(through)+1
    try:
        for stage in STAGES[:until]:
            if manifest['stages'].get(stage,{}).get('status')=='complete':
                log('Zweryfikowany etap: '+stage); continue
            log('Etap: '+stage)
            result=globals()['stage_'+stage](cfg,out)
            if stage in ('boundaries','validate'):
                topology=result.get('topologia',result)
                if topology.get('overlap_area_m2',0)>1e-4 or topology.get('interior_holes_m2',0)>1e-4:
                    log('UWAGA: źródłowe pokrycie ma nakładania lub otwory. Szczegóły w raporcie topologii; przebieg kartograficzny zachowuje je.')
            manifest['stages'][stage]=dict(status='complete',result=result)
            for p in out.glob('*.json'):
                if p.name not in ('manifest.json','error.json'): manifest['checkpoint_hashes'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
            save_json(out/'manifest.json',manifest)
    except Exception as exc:
        save_json(out/'error.json',dict(error=str(exc),traceback=traceback.format_exc()))
        log('Zatrzymano. Szczegóły: '+str(out/'error.json'))
        raise
    return out

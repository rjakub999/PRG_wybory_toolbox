from collections import defaultdict
from .common import DataError, integer, teryt, norm
from .elections import read_table, column
from .address_rules import StreetIndex, split_description, resolve, split_rule, check_feature_type


def prepare_points(rows, city, fields):
    selected=[]; seen=set()
    tf=fields.get('teryt','TERYT_GMI'); nf=fields.get('number','NR_KOMISJI')
    for r in rows:
        a=r['properties']
        if teryt(a[tf])!=teryt(city): continue
        identity=str(a.get(fields.get('id','ID_IIP')) or '').strip()
        if not identity or identity in seen: raise DataError(f'Puste lub powtórzone ID adresu: {identity}')
        if r['geometry'].geom_type!='Point': raise DataError('Adres musi mieć geometrię Point.')
        seen.add(identity)
        number=a.get(nf)
        properties=dict(a)
        properties.update(ID_ADRESU=identity,TERYT=teryt(city),
            NAZWA_ULC=str(a.get(fields.get('street','NAZWA_ULC')) or ''),
            NUMER_PORZ=str(a.get(fields.get('house','NUMER_PORZ')) or ''),
            NR_KOMISJI=integer(number,minimum=1) if number not in (None,'') else None)
        properties.setdefault('STATUS','ZRODLO' if properties['NR_KOMISJI'] else 'BRAK_PRZYPISANIA')
        selected.append(dict(geometry=r['geometry'],properties=properties))
    if not selected: raise DataError('Brak adresów wybranej gminy.')
    return selected


def assign(points, description_path, city, mapping=None):
    m=mapping or {}
    headers,rows=read_table(description_path,m.get('sheet'),m.get('encoding'),m.get('delimiter'))
    nf=column(headers,m.get('number'),('numer','nr komisji','numer obwodu glosowania','nr obwodu'))
    tf=column(headers,m.get('teryt'),('teryt','teryt gminy','kod teryt','kod teryt gminy'))
    df=column(headers,m.get('description'),('opis granic',))
    kf=column(headers,m.get('kind'),('typ obwodu',))
    index=StreetIndex([p['properties'] for p in points])
    streets=defaultdict(list)
    for i,p in enumerate(points): streets[p['properties']['NAZWA_ULC'].casefold()].append(i)
    regular=defaultdict(set); special=defaultdict(set); audit=[]; expanded=[]
    for row in rows:
        if teryt(row[tf])!=teryt(city): continue
        n=integer(row[nf],minimum=1); item=dict(row)
        for j,fragment in enumerate(split_description(row[df]),1):
            text,status,hints=resolve(fragment,index)
            item[f'Granica_{j:02d}']=text
            report=dict(NR_KOMISJI=n,FRAGMENT=fragment,WYNIK=text,STATUS=status,SUGESTIE=hints,LICZBA_ADRESOW=0)
            audit.append(report)
            try:
                name,restriction=split_rule(fragment,index); check_feature_type(fragment,name)
                selected=regular if norm(row[kf])=='staly' else special
                for i in streets[name.casefold()]:
                    if restriction.accepts(points[i]['properties']['NUMER_PORZ']):
                        selected[i].add(n); report['LICZBA_ADRESOW']+=1
                if not report['LICZBA_ADRESOW']: report['STATUS']='BRAK_ADRESOW'
            except ValueError as exc:
                report.update(STATUS='DO_KONTROLI',UWAGI=str(exc))
        expanded.append(item)
    output=[]
    for i,p in enumerate(points):
        a=dict(p['properties']); candidates=sorted(regular[i])
        original=a.get('NR_KOMISJI')
        if original is not None and candidates and original not in candidates:
            candidates=sorted(set(candidates)|{original})
        a.update(NR_PIERWOTNY=original,NR_KOMISJI=candidates[0] if len(candidates)==1 else None,
            KOMISJE_STALE='|'.join(map(str,candidates)),KOMISJE_ODREBNE='|'.join(map(str,sorted(special[i]))),
            STATUS='REGULA' if len(candidates)==1 else ('KONFLIKT' if candidates else 'BRAK_PRZYPISANIA'))
        output.append(dict(geometry=p['geometry'],properties=a))
    return output,expanded,audit

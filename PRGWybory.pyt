"""Add this Python toolbox in ArcGIS Pro Catalog. Python 3.11+ / Pro 3.7."""
import sys
from pathlib import Path
import json
import arcpy

ROOT=Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))


def parameter(name,label,datatype,required=True,default=None,direction="Input"):
    p=arcpy.Parameter(displayName=label,name=name,datatype=datatype,
        parameterType='Required' if required else 'Optional',direction=direction)
    if default is not None: p.value=default
    return p


class Toolbox:
    def __init__(self):
        self.label='PRG — obwody i wyniki wyborów'; self.alias='prgwybory'
        self.tools=[Diagnostyka,Konfiguracja,CalyProces,Granice,Protokoly,Polaczenie,Kontrola,Eksport,Kartogramy,Projekt]


class Diagnostyka:
    def __init__(self):
        self.label='00. Sprawdź środowisko i licencję'; self.description='Sprawdza pakiety i aktywną licencję; niczego nie instaluje.'
        self.canRunInBackground=False
    def getParameterInfo(self): return []
    def execute(self,parameters,messages):
        try:
            from prg_wybory.pipeline import diagnostics
            arcpy.AddMessage(json.dumps(diagnostics(),ensure_ascii=False,indent=2))
        except ImportError as exc:
            arcpy.AddError('Brak zależności. Zobacz README i requirements-core.txt. '+str(exc)); raise


class Konfiguracja:
    def __init__(self):
        self.label='01. Utwórz konfigurację miasta'; self.description='Tworzy konfigurację wariantu z gotowymi poligonami. Pozostałe warianty: przykłady JSON w examples.'
        self.canRunInBackground=False
    def getParameterInfo(self):
        p=[parameter('city','Nazwa miasta','GPString'),parameter('teryt','TERYT gminy (6 cyfr PKW lub 7 cyfr PRG)','GPString'),
           parameter('election','Identyfikator wyborów','GPString',default='prezydent_2025'),
           parameter('polygons','Poligony: ścieżka do GeoJSON lub klasy obiektów','GPString'),
           parameter('number_field','Pole numeru obwodu w poligonach','GPString',default='NR_OBWODU'),
           parameter('round1','Protokoły I tury (CSV/XLSX)','DEFile'),parameter('round2','Protokoły II tury (CSV/XLSX)','DEFile'),
           parameter('folder','Folder wyników','DEFolder'),parameter('epsg','EPSG układu obliczeniowego w metrach','GPLong',default=2180),
           parameter('config','Ścieżka nowej konfiguracji JSON','DEFile',direction='Output'),
           parameter('voronoi','Backend Voronoi','GPString',default='python'),
           parameter('neighbors','Backend sąsiedztwa','GPString',default='python'),
           parameter('raster','Backend rekonstrukcji rastra','GPString',default='python')]
        p[9].filter.list=['json']
        for item in p[10:]: item.filter.type='ValueList'; item.filter.list=['python','esri']
        return p
    def updateParameters(self,p):
        if p[9].valueAsText:
            path=Path(p[9].valueAsText)
            if not path.suffix:
                p[9].value=str(path.with_suffix('.json'))
    def updateMessages(self,p):
        if p[9].valueAsText:
            path=Path(p[9].valueAsText)
            if path.exists():
                p[9].setErrorMessage('Ten plik już istnieje. Wskaż nową nazwę JSON lub użyj istniejącego pliku w narzędziu 02.')
            elif path.suffix.lower()!='.json':
                p[9].setErrorMessage('Nazwa pliku musi mieć rozszerzenie .json.')
    def execute(self,p,messages):
        from prg_wybory.common import save_json,teryt
        config=Path(p[9].valueAsText)
        if not config.suffix: config=config.with_suffix('.json')
        if config.suffix.lower()!='.json': raise ValueError('Nazwa pliku musi mieć rozszerzenie .json.')
        if config.exists(): raise ValueError('Konfiguracja istnieje. Wskaż nowy plik albo edytuj istniejący.')
        cfg=dict(schema_version=1,city=p[0].valueAsText,teryt=teryt(p[1].valueAsText),election=p[2].valueAsText,
            mode='polygons',crs=f'EPSG:{p[8].valueAsText}',io_backend='arcpy',output=p[7].valueAsText,
            polygons=dict(path=p[3].valueAsText,number_field=p[4].valueAsText),
            rounds=[dict(path=p[5].valueAsText),dict(path=p[6].valueAsText)],
            backends=dict(voronoi=p[10].valueAsText,neighbors=p[11].valueAsText,raster=p[12].valueAsText),
            export_gpkg=False,add_to_project=True)
        save_json(config,cfg); p[9].value=str(config); arcpy.AddMessage(str(config))
        if 'esri' in cfg['backends'].values(): arcpy.AddWarning('Zapisano przyszły backend Esri; nie jest jeszcze zaimplementowany. Obliczenia nie uruchomią się w tym trybie.')


class RunBase:
    stage='all'; title='Uruchom'
    def __init__(self):
        self.label=self.title
        self.description='Wykonuje etapy do wybranego włącznie. Wznowienie pomija wyłącznie ukończone, zweryfikowane etapy z niezmienioną konfiguracją i źródłami.'
        self.canRunInBackground=False
    def getParameterInfo(self):
        cfg=parameter('config','Konfiguracja miasta JSON','DEFile'); cfg.filter.list=['json']
        resume=parameter('resume','Wznów katalog przebiegu z manifest.json (opcjonalnie)','DEFolder',False)
        output=arcpy.Parameter(displayName='Katalog wyników',name='run_output',datatype='DEFolder',parameterType='Derived',direction='Output')
        return [cfg,resume,output]
    def execute(self,p,messages):
        from prg_wybory.pipeline import run
        try:
            output=run(p[0].valueAsText,self.stage,p[1].valueAsText,arcpy.AddMessage)
            p[2].value=str(output)
        except Exception as exc:
            arcpy.AddError(str(exc)); raise


class CalyProces(RunBase): title='02. Wykonaj cały proces'
class Granice(RunBase): stage='boundaries'; title='03. Przygotuj lub odtwórz granice'
class Protokoly(RunBase): stage='results'; title='04. Przygotuj protokoły obu tur'
class Polaczenie(RunBase): stage='join'; title='05. Połącz obwody z wynikami'
class Kontrola(RunBase): stage='validate'; title='06. Sprawdź kompletność i sumy'
class Eksport(RunBase): stage='export'; title='07. Zapisz GDB / GPKG'
class Kartogramy(RunBase): stage='maps'; title='08. Wygeneruj kartogramy PNG/PDF'
class Projekt(RunBase): stage='project'; title='09. Dodaj warstwy i zapisz kopię projektu ArcGIS Pro'

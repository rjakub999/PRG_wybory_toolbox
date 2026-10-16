# Raport weryfikacji — 16 października 2026

## Środowiska

- ArcGIS Pro 3.7, Python 3.13.13, licencja `ArcView` (Basic).
- Izolowane zależności testowe: Shapely 2.2.0, pyproj 3.8.0, rasterio 1.5.2.
- Drugi przebieg: Python QGIS 3.12 / GDAL, Shapely 2.1.2, GEOS 3.14.1.
- Nie zmieniano domyślnego środowiska ArcGIS Pro; dodatkowe biblioteki do testów
  zainstalowano w oddzielnych katalogach tymczasowych.

## Zakres testów automatycznych

`tests/test_core.py` obejmuje:

- TERYT z zerem wiodącym i 7-cyfrowym kodem PRG;
- odrzucanie liczb ułamkowych, NaN, ujemnych, duplikatów i niezgodnych sum;
- brak głosów ważnych i remisy;
- brakujące obwody stałe przy złączeniu;
- większość sąsiadów 3:2, zachowanie źródłowych przypisań;
- remisy odległości, izolację gmin i brak kaskadowego przypisywania;
- Voronoi dla punktów współliniowych, otworu granicy i sprzecznych duplikatów;
- zakresy/parzystość numeracji, cyfry w nazwie ulicy, polskie znaki;
- wspólną zmianę granicy i ochronę adresu, który zostałby przeniesiony;
- segmentację syntetycznego rastra RGB, domykanie przy krawędzi i brak zasięgu;
- odmowę wznowienia po zmianie konfiguracji lub pliku pośredniego;
- odmowę uruchomienia niezaimplementowanego backendu Esri.

Wszystkie **13 testów** przeszło w Pythonie 3.13 ArcGIS Pro.

## Rzeczywiste dane Łodzi

Wejścia lokalne użytkownika: `lodz_obwody.geojson`, `Lodz_I_tura.csv`,
`Lodz_II_tura.csv`. Nie są dołączone do repozytorium.

- 283 poligony stałe, wszystkie połączone z wynikami obu tur.
- 323 protokoły w każdej turze: 283 stałe + 40 odrębnych.
- Głosy ważne w obwodach stałych: I tura **342 601**, II tura **361 264**.
- I tura: Trzaskowski prowadził w 283 obwodach.
- II tura: Trzaskowski w 282, Nawrocki w 1; brak remisów.
- Zapis GPKG przez GDAL oraz zapis GDB/GPKG przez ArcPy Basic zakończył się sukcesem.
- ArcGIS zaimportował 10 narzędzi z `PRGWybory.pyt`.
- Wygenerowano PNG/PDF obu tur; sprawdzono wizualnie PNG.
- Zapisano `.lyrx` i kopię APRX za pomocą ArcPy Basic.
- Końcowy przebieg wykonano przez `arcpy.ImportToolbox(...).CalyProces(...)`,
  a nie tylko przez wywołanie wewnętrznych funkcji. Czas narzędzia około 37 s.
- Ponownie otwarto GDB, GPKG i APRX: 283 rekordy w obu bazach, zgodne sumy głosów,
  dwie nieuszkodzone warstwy obiektowe z rendererami UniqueValueRenderer.

## Problemy wejścia ujawnione przez kontrolę

Samoprzecięcia pierścieni w obwodach **79, 229 i 234**. Opcjonalne `make_valid`
usunęło błędy; zmiany powierzchni poniżej 0,000001 m². Raport zapisuje każdy przypadek.
Źródło ma też nadmiar powierzchni wynikający z nakładania około **12 268,33 m²**
oraz otwory w sumie geometrii około **6 777,08 m²**. Nie usuwano ich automatycznie.
Nie wszystkie otwory muszą być błędami merytorycznymi.

## Granice potwierdzenia

Testy rastrowe i dopasowania ulic w tej wersji są syntetyczne; pełnego nowego
przebiegu rekonstrukcji Lublina nie wykonywano. Wariant rastra nie ma OCR.
Narzędzia nie gwarantują zgodności hipotetycznej granicy Voronoi z uchwałą.
Warstwa oficjalna i protokoły muszą dotyczyć tej samej elekcji.
Nie przetestowano interakcji ręcznych z formularzami w GUI; przetestowano ArcPy,
import skrzynki i działanie jej kodu na licencji Basic.
Przyszły backend Esri nie zawiera kodu i nie został przetestowany.

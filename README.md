# PRG Wybory Toolbox

Python Toolbox dla **ArcGIS Pro 3.7 Basic**, do przygotowania granic obwodów,
połączenia wyników dwóch tur wyborów i utworzenia kartogramów dla kolejnych miast.
Interfejs i komunikaty są po polsku. Wersja 0.1.0.

## Szybki start w ArcGIS Pro

1. Pobierz repozytorium / ZIP do folderu projektu. Nie przenoś samego `.pyt`:
   folder `prg_wybory` musi znajdować się obok.
2. W **Ustawienia → Menedżer pakietów** sklonuj `arcgispro-py3`, np. jako
   `prg-wybory`, i aktywuj klon. Nie instaluj pakietów do domyślnego środowiska.
3. W Python Command Prompt tego klonu sprawdź `python -c "import sys; print(sys.prefix)"`.
   Z katalogu projektu zainstaluj brakujące zależności:

   ```powershell
   python -m pip install -r requirements-core.txt
   # Tylko gdy potrzebne są ulice lub raster:
   python -m pip install -r requirements-optional.txt
   ```

   Nie instaluj `arcpy` z pip. Zależności ArcGIS dostarcza instalacja Pro.
   Jeżeli resolver proponuje wymianę pakietów zastrzeżonych przez Esri, przerwij
   instalację i dobierz wersje do klonu; zakresy requirements nie są lockfile.
4. Uruchom ponownie Pro. W Katalogu: **Skrzynki narzędziowe → Dodaj skrzynkę**,
   wskaż `PRGWybory.pyt`.
5. Uruchom **00. Sprawdź środowisko i licencję**.
6. Dla Łodzi użyj `examples/lodz.json`. Pliki `lodz_obwody.geojson`,
   `Lodz_I_tura.csv`, `Lodz_II_tura.csv` powinny leżeć w głównym folderze projektu.
   Dane użytkownika nie są publikowane w repozytorium.
7. Uruchom **02. Wykonaj cały proces**, wybierając konfigurację. Pole wznowienia
   pozostaw puste przy pierwszym przebiegu.

Dla kolejnego miasta narzędzie **01. Utwórz konfigurację miasta** tworzy JSON
z formularza. Nietypowe nagłówki, wariant adresowy i rastrowy konfiguruje się
w JSON według przykładów. Edycja JSON to obecnie interfejs zaawansowanych parametrów;
wersja 0.1 nie zawiera osobnego wizualnego edytora tych ustawień.

## Etapy i wyniki

| Etap | Wynik |
|---|---|
| Granice | `01_obwody.json`, raport topologii i ewentualnych napraw |
| Reguły adresowe (opcjonalne) | `01_granice_rozbite.json` z Granica_01 itd., punkty i raport reguł |
| Raster (opcjonalny) | Regiony, pewność identyfikacji, raport pokrycia |
| Protokoły | `02_wyniki_T1.json`, `02_wyniki_T2.json`, również obwody odrębne |
| Połączenie | `03_obwody_wyniki.json`, po jednym rekordzie na obwód stały |
| Kontrola | `04_kontrola.json`: sumy, procenty, kompletność, geometrie |
| Eksport ArcGIS | `wyniki.gdb/obwody_wyniki`, tabele `protokoly_T1`, `protokoly_T2` |
| Eksport opcjonalny | `wyniki.gpkg/obwody_wyniki` przy `export_gpkg: true` |
| Kartogramy | PNG/PDF obu tur z legendą, skalą i strzałką północy |
| Projekt ArcGIS | Warstwy `.lyrx` i kopia projektu `wybory.aprx` |

Wariant ArcGIS dodaje nową mapę do bieżącego projektu i zapisuje jego kopię;
nie zapisuje zmian do oryginalnego pliku APRX. Pliki PNG/PDF są renderowane
przez matplotlib; w APRX są edytowalne warstwy ze stylami, bez układu wydruku.
Wewnętrzne JSON z geometrią zawierają jawny CRS i służą do wznowienia;
nie są plikami GeoJSON RFC 7946. Obok każdego powstaje `.geojson` w WGS84
do kontroli w GIS (w ArcGIS można użyć JSON To Features). Rozbite opisy i raport
reguł są też zapisywane jako CSV. Główne dane wynikowe znajdują się w GDB/GPKG.

Każdy przebieg tworzy nowy folder z datą i losowym identyfikatorem. Źródła nie są
nadpisywane. `manifest.json` zapisuje konfigurację, biblioteki i identyfikatory źródeł.
Pliki mają SHA-256, a geobazy katalogowe — odcisk nazw, rozmiarów i czasów modyfikacji
(bez plików blokad). Ten drugi odcisk nie jest kryptograficznym skrótem zawartości GDB.

Narzędzia etapowe wykonują wszystkie brakujące etapy do wybranego włącznie.
Do wznowienia wskaż ten sam plik konfiguracji i katalog konkretnego przebiegu.
Zmiana źródła lub konfiguracji wymaga nowego przebiegu; plików pośrednich nie należy
edytować. Błąd zostawia raport `error.json`. Wznowienie po błędzie eksportu może
wymagać nowego przebiegu, ponieważ częściowa GDB nie jest automatycznie usuwana.

## Trzy warianty

### Gotowe poligony (`mode: polygons`)

Wymagany jest numer obwodu. Dla źródła zawierającego wiele miast należy ustawić
`polygons.teryt_field` lub wcześniej wydzielić jedno miasto. Plik bez tego pola
jest traktowany jako świadomie wybrany zbiór jednego miasta.
Łączenie: sześciocyfrowy TERYT gminy + numer obwodu, z identyfikatorem elekcji
w konfiguracji i wynikach. Części tego samego obwodu są agregowane.

Naprawa niepoprawnych poligonów jest domyślnie wyłączona. Ustawienie
`polygons.repair_invalid: true` uruchamia `make_valid`, zapisuje przyczynę i zmianę
powierzchni. Próg `max_repair_area_change_m2` domyślnie wynosi 1 m². Mniejsza zmiana
powierzchni nie gwarantuje identycznej granicy — sprawdź wynik. Nakładania i otwory
w oficjalnych danych są raportowane, lecz nie usuwane automatycznie na etapie
kartogramu. Nie każdy otwór jest błędem: może wynikać z definicji zasięgu.

W przykładzie Łodzi naprawa jest włączona po wykryciu samoprzecięć obwodów
79, 229 i 234. Zmiany powierzchni były na poziomie błędu numerycznego.

### Adresy i opisy (`mode: addresses`)

Przykład: `examples/adresy.json`. Wymagane: granica miasta, adresy PRG z trwałym
identyfikatorem i TERYT, opisy granic (opcjonalne, jeżeli adresy są już przypisane).
Parser obsługuje całe ulice, listy numerów, zakresy, parzystość i `od … do końca`.
Złożone wyjątki, niejednoznaczne nazwy i konflikty nie są zgadywane. Nazwa wynikowa
pochodzi z wybranego PRG; brak stałej listy miast ani nazw kandydatów.

Sąsiedztwo: `k`, `max_distance` w metrach, `min_neighbors`, `minimum_share` i `apply`.
Pole PEWNOSC oznacza udział głosów punktów referencyjnych, nie statystyczne
prawdopodobieństwo poprawności przypisania.
Domyślne `apply: false` tworzy propozycje. `apply: true` przypisuje tylko punkty
bez komisji i bez konfliktu, przy spełnieniu progów. Adresy już przypisane nie są
zmieniane. Sąsiedzi z innej gminy nie głosują; nowe przypisania nie głosują w tym
samym przebiegu. Remis głosów lub odległości na granicy k oznacza brak rozstrzygnięcia.
Voronoi jest zatrzymywane, jeżeli pozostają nieprzypisane punkty, punkty poza miastem
lub różne komisje pod tymi samymi współrzędnymi. Specjalne obwody są zapisane osobno
w `KOMISJE_ODREBNE` i nie stają się klasami Voronoi.

Opcjonalne `roads`: dopasowanie wspólnej granicy obu poligonów jednocześnie.
Zmiana jest przyjmowana tylko po zachowaniu zasięgu, topologii i położenia wszystkich
punktów kontrolnych po tej samej stronie granicy. Przy braku pewnego dopasowania
zostaje granica pierwotna. Wejściowe pokrycie musi być topologicznie poprawne.

### Raster RGB (`mode: raster`)

Przykład: `examples/raster.json`. Wymagany raster z georeferencją, obejmujący całe
miasto, granica miasta oraz wiarygodne punkty referencyjne z numerami obwodów.
Konfigurowalne: kolor linii i tolerancja RGB, domykanie linii w pikselach,
minimalna liczba punktów, udział większości i odległość punktu od granicy.
Raster jest przetwarzany w pamięci; domyślny limit to 25 mln pikseli.

To rekonstrukcja kolorowych linii i identyfikacja regionów za pomocą punktów,
**bez automatycznego OCR w wersji 0.1**. Numery można uzupełnić w `raster.assignments`,
np. `{"12": 140}` przypisuje regionowi 12 obwód 140. Identyfikatory regionów odnoszą
się do konkretnego rastra i parametrów segmentacji. Po zmianie rastra, granicy lub
parametrów usuń stare przypisania i sprawdź regiony ponownie. Nierozpoznane regiony
blokują końcowe połączenie. Napisy, przerwane linie lub podobne kolory podkładu mogą
powodować błędną segmentację nawet przy zgodnej liczbie regionów — wynik wymaga kontroli.
Numery z punktów nie są niezależnym dowodem ich poprawności.

## Nagłówki PKW

Obsługiwane są CSV UTF-8/CP1250 z przecinkiem, średnikiem lub tabulatorem oraz XLSX.
Automatyczne rozpoznanie dotyczy typowych kolumn PKW i eksportów ArcGIS z podkreśleniami.
Jeśli skoroszyt ma wiele arkuszy, podaj `mapping.sheet`.
Nietypowe źródło można jawnie zmapować:

```json
{
  "path": "T1.csv",
  "mapping": {
    "teryt": "Kod gminy",
    "number": "Obwód",
    "kind": "Rodzaj",
    "valid": "Głosy ważne",
    "invalid": "Głosy nieważne",
    "candidates": {"KANDYDAT_A": "Jan Kowalski", "KANDYDAT_B": "Anna Nowak"}
  }
}
```

Nie dopuszczamy duplikatów kluczy, ujemnych głosów, obcięcia części ułamkowej,
niezgodności sum kandydatów z głosami ważnymi ani brakujących obwodów stałych.
Brak głosów ważnych ma własną kategorię, a nie remis. W wynikach są wszystkie
kolumny głosów kandydatów, procenty i sumy ważnych/nieważnych głosów; pozostałe pola
protokołu (np. pełnomocnicy, karty) pozostają w plikach źródłowych.
TERYT należy zachować jako tekst, szczególnie 7-cyfrowy kod PRG z zerem na początku.

## Backend Python / przyszły Esri

```json
"backends": {"voronoi": "python", "neighbors": "python", "raster": "python"}
```

Wartość `esri` jest zarezerwowana i zgłasza czytelny błąd przed przetwarzaniem.
Nie ma automatycznego przełączania, kodu wykonawczego wyższej licencji ani wywołań
CreateThiessenPolygons, Near/GenerateNearTable czy narzędzi Spatial Analyst.
Kontrakty i wymagania przyszłej implementacji: [docs/BACKENDS.md](docs/BACKENDS.md).

## Testy i uruchomienie bez interfejsu

```powershell
python -m unittest discover -s tests -v
python -m prg_wybory --diagnostics
python -m prg_wybory --config examples/lodz.json
python -m prg_wybory --config examples/lodz.json --through validate
```

Testy rdzenia nie potrzebują licencji ArcGIS; test rastra wymaga rasterio.
Wersja 0.1 korzysta z dostarczonych plików PKW i danych przestrzennych;
nie pobiera automatycznie arkuszy PKW ani kafli usług miejskich.
Adapter `io_backend: ogr` służy do testów/CLI w środowisku GDAL, zapisuje GPKG i nie
tworzy APRX. Adapter `arcpy` służy do ArcGIS Pro Basic. Żaden wariant obliczeniowy
Python nie wymaga instalacji QGIS.

Historia kodu: parser adresów i funkcje dopasowania wspólnych granic wydzielono
z wcześniejszego projektu Lublina, usuwając stałe miasta i ścieżki.
Raport wykonanych testów: [docs/TEST_REPORT.md](docs/TEST_REPORT.md).

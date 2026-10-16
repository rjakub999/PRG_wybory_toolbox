from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import subprocess
import hashlib
import json
import tempfile

root=Path(__file__).resolve().parents[1]
destination=root/'dystrybucja'
destination.mkdir(exist_ok=True)
archive=destination/'PRG_Wybory_Toolbox_v0.1.2_2026-10-16.zip'
if archive.exists(): raise FileExistsError(archive)
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\0')
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip()
files={name:(root/name).read_bytes() for name in tracked if name}
for name in ['lodz_obwody.geojson','Lodz_I_tura.csv','Lodz_II_tura.csv','schema.ini']:
    files[name]=(root/name).read_bytes()
instructions='''PRG WYBORY TOOLBOX 0.1.2 — START DLA ODBIORCY
Paczka z 16 października 2026 r.

CO ZAWIERA PACZKA
Kod Python Toolbox, moduły obliczeniowe, testy, dokumentację, przykładowe
konfiguracje i komplet wejść Łodzi do pierwszego uruchomienia: poligony
obwodów oraz protokoły I i II tury wyborów prezydenckich 2025.
Nie trzeba pobierać tych danych ponownie ani zmieniać ścieżek w przykładzie Łodzi.
Nie dołączono instalacji ArcGIS Pro, licencji, środowiska Python, pakietów
binarnych, prywatnych projektów APRX ani folderów wcześniejszych przebiegów.

WYMAGANIA
Windows i aktywna licencja ArcGIS Pro. Kod przetestowano na ArcGIS Pro 3.7
(Python 3.13) z licencją Basic. Wersja Standard lub Advanced również może
uruchamiać ten sam wariant. Na innej wersji Pro zgodność wymaga sprawdzenia.
Potrzebne są możliwość utworzenia klonu środowiska Python, zapis w folderze
wynikowym oraz internet/repozytorium pakietów do pierwszej instalacji zależności.
Samo przetwarzanie dołączonych danych nie wymaga pobierania danych z sieci.
Wymagania dotyczące połączenia dla licencji ArcGIS zależą od jej konfiguracji.

UWAGA O WYŻSZEJ LICENCJI
We wszystkich konfiguracjach pozostaw backend "python". Ten wariant działa
także przy wyższej licencji. Wartość "esri" oznacza zaplanowany, lecz jeszcze
niezaimplementowany wariant natywnych algorytmów. Jej wybranie zatrzyma proces.
Paczka nie zawiera kodu algorytmów przeznaczonych wyłącznie dla wyższej licencji.
Wspólna integracja odczytu, eksportu i symbolizacji korzysta z ArcPy Basic.

INSTALACJA — JEDNORAZOWO
1. Rozpakuj CAŁĄ paczkę do lokalnego, zapisywalnego folderu, np.
   C:\\GIS\\PRG_Wybory_Toolbox. Nie uruchamiaj narzędzi bezpośrednio z ZIP.
   PRGWybory.pyt i folder prg_wybory muszą znajdować się obok siebie.
2. W ArcGIS Pro: Ustawienia -> Menedżer pakietów. Sklonuj domyślne środowisko
   arcgispro-py3, np. jako prg-wybory. Aktywuj klon i zrestartuj Pro.
3. Otwórz Python Command Prompt dla wybranego klonu. Zweryfikuj poleceniem:
      python -c "import sys; print(sys.prefix)"
   Ścieżka ma wskazywać klon, a nie domyślne arcgispro-py3.
4. Przejdź w tym oknie do folderu z requirements-core.txt, np.:
      cd /d C:\\GIS\\PRG_Wybory_Toolbox
   Zainstaluj zależności podstawowe:
      python -m pip install -r requirements-core.txt
   Dla modułów dopasowania do ulic i rekonstrukcji rastra dodatkowo:
      python -m pip install -r requirements-optional.txt
   Nie instaluj arcpy z pip. Dostarcza je ArcGIS Pro.
   Nie modyfikuj domyślnego środowiska. Jeżeli instalator zgłosi konflikt
   z ograniczeniami pakietów Esri, dobierz wersje w klonie z administratorem.
5. Zrestartuj ArcGIS Pro, otwórz dowolny projekt lokalny. W panelu Katalog:
   Skrzynki narzędziowe -> Dodaj skrzynkę -> PRGWybory.pyt.
6. Uruchom "00. Sprawdź środowisko i licencję". Brakujące pakiety pokaże
   diagnostyka; importowanie samego .pyt nie zastępuje ich instalacji.

PIERWSZY TEST — ŁÓDŹ
1. W skrzynce uruchom "02. Wykonaj cały proces".
2. Jako konfigurację wybierz examples\\lodz.json z rozpakowanej paczki.
3. Pole wznowienia pozostaw puste i uruchom narzędzie.
4. Wyniki znajdziesz w wyniki\\<data_i_id_przebiegu> obok kodu.
   Otrzymasz wyniki.gdb, kartogramy PNG/PDF obu tur, style LYRX, kopię projektu
   wybory.aprx oraz raporty kontroli. W aktywnym projekcie pojawi się nowa mapa.
   Oryginalny plik APRX nie jest automatycznie zapisywany.
5. Aby dodatkowo otrzymać GPKG, przed nowym przebiegiem ustaw w konfiguracji
   "export_gpkg": true. Zmiana konfiguracji wymaga nowego przebiegu.

OCZEKIWANY WYNIK TESTU
283 obwody stałe z wynikami obu tur; po 323 protokoły w tabelach (283 stałe
i 40 odrębnych). Suma głosów ważnych dla stałych: I tura 342601, II tura 361264.
Źródło ma samoprzecięcia trzech poligonów — przykład jawnie włącza naprawę
z raportem. Pozostałe nakładania i otwory są raportowane, nie usuwane automatycznie.
Szczegóły: docs\\TEST_REPORT.md.

KOLEJNE MIASTA
Użyj "01. Utwórz konfigurację miasta" dla gotowych poligonów. Podaj TERYT,
pole numeru obwodu, wyniki dwóch tur oraz folder wyjściowy. Dla rekonstrukcji
z adresów lub rastra dostosuj examples\\adresy.json / examples\\raster.json.
Te dwa pliki są szablonami; wymagają własnych wejść. Raster RGB wymaga
referencyjnych punktów lub ręcznego przypisania regionów, nie ma jeszcze OCR.
Pełna instrukcja: README.md. Projekt przyszłego backendu: docs\\BACKENDS.md.

JEŚLI WYSTĄPI BŁĄD
Prześlij autorowi komunikaty narzędzia, wersję Pro, wynik diagnostyki,
konfigurację i error.json z katalogu przebiegu. Nie przesyłaj haseł ani licencji.
Do wznowienia służy katalog konkretnego przebiegu z manifest.json; po zmianie
źródeł albo konfiguracji rozpocznij nowy przebieg.

Integralność plików: MANIFEST_PACZKI.json zawiera SHA-256 wszystkich składników.
Repozytorium: https://github.com/rjakub999/PRG_wybory_toolbox
'''
instructions+='\nAKTUALIZACJA 0.1.2: Zobacz docs/WYDANIE_0.1.2.txt i docs/PLAN_ESRIADDINX.txt.\n'
files['START_TUTAJ.txt']=instructions.encode('utf-8-sig')
manifest=dict(version='0.1.2',date='2026-10-16',commit=commit,
    files={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in sorted(files.items())})
files['MANIFEST_PACZKI.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
prefix='PRG_Wybory_Toolbox/'
with ZipFile(archive,'w',compression=ZIP_DEFLATED,compresslevel=9) as z:
    for name,data in sorted(files.items()):
        if Path(name).is_absolute() or '..' in Path(name).parts: raise ValueError(name)
        z.writestr(prefix+name.replace('\\','/'),data)
with ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(files)
    for name,entry in manifest['files'].items():
        assert hashlib.sha256(z.read(prefix+name)).hexdigest()==entry['sha256']
    with tempfile.TemporaryDirectory(prefix='prg_zip_check_') as tmp:
        z.extractall(tmp)
        package=Path(tmp)/'PRG_Wybory_Toolbox'
        c=json.loads((package/'examples/lodz.json').read_text(encoding='utf-8'))
        for s in [c['polygons'],*c['rounds']]:
            assert (package/'examples'/s['path']).resolve().is_file()
        for f in package.rglob('*.py'): compile(f.read_text(encoding='utf-8-sig'),str(f),'exec')
        compile((package/'PRGWybory.pyt').read_text(encoding='utf-8-sig'),'PRGWybory.pyt','exec')
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
(destination/'START_TUTAJ.txt').write_bytes(files['START_TUTAJ.txt'])
print(json.dumps(dict(zip=str(archive),bytes=archive.stat().st_size,files=len(files),sha256=digest,verified=True),indent=2))

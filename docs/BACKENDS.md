# Kontrakt wymiennych modułów

Implementacja `python` jest aktywna. `esri` jest wyłącznie nazwą przyszłego wariantu.
Na życzenie użytkownika w tym repozytorium nie ma implementacji algorytmów dla
wyższej licencji. ArcPy Basic służący do odczytu, eksportu i symbolizacji jest
częścią wspólnej integracji aplikacji, niezależną od wyboru tych trzech modułów.

## Dane wspólne

Moduły dostają rekordy `{"geometry": ShapelyGeometry, "properties": {...}}`.
Geometrie są już w jednym projektowanym CRS w metrach. `TERYT` to tekst 6-cyfrowy,
`NR_KOMISJI` to dodatnia liczba całkowita lub None, `ID_ADRESU` identyfikuje punkt.
Nie wolno zmieniać identyfikatorów, używać stopni jako metrów ani modyfikować
obiektów wejściowych. Błędy danych mają być jawne; nie wybieramy pierwszego rekordu
w konflikcie i nie wybieramy po cichu innego backendu.

## voronoi(points, boundary)

Wyjście: jeden rekord poligonowy (może być wieloczęściowy) na parę TERYT/numer.
Zasięg wyniku równy boundary, brak dodatniej powierzchni nakładania i nowych luk.
Duplikaty lokalizacji o tym samym przypisaniu mogą być scalone; duplikaty sprzeczne
muszą zatrzymać obliczenia. Każdy punkt musi leżeć w obwodzie własnej klasy.
Przyszły Esri: dobór narzędzi i weryfikacja licencji przed startem; Create Thiessen
Polygons wymaga Advanced. Wynik trzeba przyciąć i zagregować do kontraktu.

## neighbors(points, k, max_distance, min_neighbors, minimum_share, apply)

Wyjście: te same punkty i liczba rekordów, plus NR_PIERWOTNY, PROPONOWANY_NR,
PEWNOSC, SASIEDZI, LICZBA_SASIADOW i STATUS. Istniejące przypisania pozostają.
Wykluczyć inne gminy, konflikty i punkty przypisane inferencyjnie jako referencje.
Zamrożony zbiór referencyjny; brak kaskady. Maksymalny dystans i minimalna liczba
sąsiadów obowiązują równocześnie. Remis na k-tej odległości wymaga kontroli.
Przyszły Esri może wyznaczać sąsiadów natywnymi narzędziami, ale te same reguły
decyzji muszą obowiązywać; licencję konkretnego narzędzia sprawdzimy przy wdrożeniu.

## raster(path, boundary, seeds, crs, options)

Wyjście: wszystkie regiony wewnątrz boundary, także nierozpoznane. Pola REGION,
NR_KOMISJI, PEWNOSC, LICZBA_PUNKTOW, STATUS, METODA. Regionu bez dowodów nie wolno
usuwać ani przypisywać na podstawie kolejności. Uzupełnienie powierzchni linii
nie może wypełniać NoData. Numery regionów zależą od wejścia, więc ręczne mapowanie
nie jest przenośne między zmienionymi rastrami.
Przyszły wariant Esri będzie wymagał doboru narzędzi raster calculator / morfologii /
grupowania i wektoryzacji, oraz sprawdzenia rozszerzeń. Sam Advanced nie gwarantuje
wszystkich potrzebnych rozszerzeń. OCR byłby osobnym etapem poza obecnym kontraktem
segmentacji, z raportowaniem niepewności i możliwością ręcznych etykiet.

## Test zgodności przyszłej implementacji

Użyć tych samych testów punktów współlokalizowanych, współliniowych, otworów,
remisów, izolowanych punktów i rastra RGB. Porównać kompletność, pokrycie, przypisania
adresów i deterministyczność, nie kolejność wierzchołków czy bajty geometrii.
Tolerancje muszą wynikać z rozdzielczości rastra i precyzji CRS.

Rejestr backendów zostanie rozszerzony dopiero po dostarczeniu i przetestowaniu
implementacji natywnej. W konfiguracji już można zapisać osobny wybór dla każdego modułu.

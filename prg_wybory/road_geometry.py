"""Shared-boundary geometry routines from the validated Lublin workflow."""

import math
from collections import defaultdict

import networkx as nx

import shapely

from shapely.geometry import LineString, Point, MultiPolygon

from shapely.ops import polygonize, unary_union, linemerge

from shapely.strtree import STRtree

def parts(geometry, kind):
    if geometry.geom_type == kind:
        return [geometry]
    if hasattr(geometry, 'geoms'):
        return [part for geom in geometry.geoms for part in parts(geom, kind)]
    return []

def signature(geometry):
    polygons = parts(geometry, 'Polygon')
    return len(polygons), sum(len(p.interiors) for p in polygons)

def street_evidence(chain, roads, tree, max_distance, angle=35):
    """Udział granicy, przy której bliska ulica biegnie podobnym kierunkiem."""
    samples = max(3, math.ceil(chain.length / 20))
    aligned = 0
    for index in range(samples):
        distance = (index + 0.5) * chain.length / samples
        point = chain.interpolate(distance)
        road = roads[int(tree.nearest(point))]
        if point.distance(road) > max_distance:
            continue
        old_a = chain.interpolate(max(0, distance - 30))
        old_b = chain.interpolate(min(chain.length, distance + 30))
        position = road.project(point)
        road_a = road.interpolate(max(0, position - 20))
        road_b = road.interpolate(min(road.length, position + 20))
        u = (old_b.x-old_a.x, old_b.y-old_a.y)
        v = (road_b.x-road_a.x, road_b.y-road_a.y)
        denominator = math.hypot(*u) * math.hypot(*v)
        if denominator and abs(u[0]*v[0]+u[1]*v[1])/denominator >= math.cos(math.radians(angle)):
            aligned += 1
    return aligned / samples

def road_route(chain, roads, road_tree, max_distance, step=10, min_support=0.6, angle=35):
    """Najkrótsza ważona trasa ulicami w korytarzu wspólnej granicy."""
    corridor = chain.buffer(max_distance)
    indices = road_tree.query(corridor, predicate='intersects')
    if not len(indices):
        raise ValueError('BRAK_ULIC_W_KORYTARZU')
    if street_evidence(chain, roads, road_tree, max_distance, angle) < min_support:
        raise ValueError('ULICA_NIE_BIEGNIE_WZDLUZ_GRANICY')
    local = unary_union([roads[int(i)].intersection(corridor) for i in indices])
    segments = []
    for line in parts(local, 'LineString'):
        coordinates = list(line.coords)
        for a, b in zip(coordinates, coordinates[1:]):
            if math.dist(a, b) > 1e-6:
                segments.append(LineString([a, b]))
    if not segments:
        raise ValueError('BRAK_ODCINKOW_ULIC')
    tree = STRtree(segments)
    start, end = Point(chain.coords[0]), Point(chain.coords[-1])
    projections = []
    splits = defaultdict(list)
    for point in (start, end):
        index = int(tree.nearest(point))
        segment = segments[index]
        projected = segment.interpolate(segment.project(point))
        if point.distance(projected) > max_distance:
            raise ValueError('KONIEC_POZA_TOLERANCJA')
        projections.append(projected)
        splits[index].append(projected)
    graph = nx.Graph()
    node = lambda p: (round(p.x, 6), round(p.y, 6))
    for i, segment in enumerate(segments):
        points = [Point(segment.coords[0]), *splits[i], Point(segment.coords[-1])]
        points.sort(key=segment.project)
        for a, b in zip(points, points[1:]):
            u, v = node(a), node(b)
            if u == v:
                continue
            length = math.dist(u, v)
            midpoint = Point((u[0] + v[0]) / 2, (u[1] + v[1]) / 2)
            weight = length * (1 + 3 * midpoint.distance(chain) / max_distance)
            if not graph.has_edge(u, v) or weight < graph[u][v]['weight']:
                graph.add_edge(u, v, weight=weight)
    try:
        route = nx.shortest_path(graph, node(projections[0]), node(projections[1]), weight='weight')
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        raise ValueError('BRAK_CIAGLEJ_TRASY_ULICAMI') from exc
    if len(route) < 2:
        raise ValueError('ZBYT_KROTKA_TRASA')
    coordinates = [chain.coords[0], *route, chain.coords[-1]]
    cleaned = [coordinates[0]]
    for coordinate in coordinates[1:]:
        if math.dist(cleaned[-1], coordinate) > 1e-7:
            cleaned.append(coordinate)
    replacement = LineString(cleaned)
    if not replacement.is_simple:
        raise ValueError('TRASA_PRZECINA_SAMA_SIEBIE')
    if replacement.length > chain.length * 1.5 + max_distance * 2:
        raise ValueError('ZBYT_DLUGI_OBJAZD')
    # Wzajemna odległość, sprawdzana także pomiędzy oryginalnymi wierzchołkami.
    dense_old = shapely.segmentize(chain, step)
    dense_new = shapely.segmentize(replacement, step)
    displacement = shapely.hausdorff_distance(dense_old, dense_new)
    if displacement > max_distance + 1e-5:
        raise ValueError('TRASA_POZA_TOLERANCJA')
    if replacement.length - math.dist(chain.coords[0], projections[0].coords[0]) - math.dist(chain.coords[-1], projections[1].coords[0]) < chain.length * 0.4:
        raise ValueError('ZA_MALO_PRZEBIEGU_ULICAMI')
    return replacement, float(displacement)

def street_subchains(chain, roads, tree, max_distance, min_length):
    """Fragmenty oryginalnych krawędzi najbliższe tej samej osi ulicy.

    Podział wyłącznie w istniejących wierzchołkach zachowuje dokładne wspólne
    końce obu poligonów. Segmentów dalekich od ulic nie przesuwamy.
    """
    coordinates = list(chain.coords)
    groups, current, previous = [], [], None
    for a, b in zip(coordinates, coordinates[1:]):
        midpoint = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        road_id = int(tree.nearest(midpoint))
        if midpoint.distance(roads[road_id]) > max_distance:
            road_id = None
        if road_id != previous:
            if len(current) > 1:
                groups.append((previous, LineString(current)))
            current = [a]
        if road_id is not None:
            if not current:
                current = [a]
            current.append(b)
        previous = road_id
    if len(current) > 1:
        groups.append((previous, LineString(current)))
    return [(road_id, line) for road_id, line in groups
            if road_id is not None and line.length >= min_length and not line.equals(chain)]

def residual_subchains(chain, roads, tree, min_length, street_lock=0.75):
    """Fragmenty do uproszczenia; odcinki już na osiach ulic są zablokowane."""
    groups, current = [], []
    for a, b in zip(chain.coords, list(chain.coords)[1:]):
        midpoint = Point((a[0]+b[0])/2, (a[1]+b[1])/2)
        locked = midpoint.distance(roads[int(tree.nearest(midpoint))]) <= street_lock
        if locked:
            if len(current) > 1:
                groups.append(LineString(current))
            current = []
        else:
            if not current:
                current = [a]
            current.append(b)
    if len(current) > 1:
        groups.append(LineString(current))
    return [line for line in groups if line.length >= min_length]

def shared_chains(geometries):
    tree = STRtree(geometries)
    result = []
    for i, geometry in enumerate(geometries):
        for index in tree.query(geometry, predicate='intersects'):
            j = int(index)
            if j <= i:
                continue
            lines = parts(geometry.boundary.intersection(geometries[j].boundary), 'LineString')
            if lines:
                for line in parts(linemerge(lines), 'LineString'):
                    result.append((i, j, line))
    return sorted(result, key=lambda item: (-item[2].length, item[0], item[1]))

def full_boundary_lines(geometries):
    """Każda wspólna granica raz, plus cały niezmienny obrys zewnętrzny."""
    shared = shared_chains(geometries)
    external = parts(unary_union(geometries).boundary, 'LineString')
    complete = [line for _, _, line in shared] + external
    expected = unary_union([g.boundary for g in geometries])
    actual = unary_union(complete)
    if expected.difference(actual).length > 1e-5 or actual.difference(expected).length > 1e-5:
        raise ValueError('NIEKOMPLETNA_WARSTWA_GRANIC')
    return shared, external

def rebuild_pair(a, b, chain, replacement):
    """Jedna nowa linia rozdziela oba poligony bez niezależnego snapowania."""
    union = a.union(b)
    if replacement.difference(union).length > 1e-5:
        raise ValueError('TRASA_WCHODZI_W_INNY_OBWOD')
    remaining_a = a.boundary.difference(chain)
    remaining_b = b.boundary.difference(chain)
    network = unary_union([remaining_a, remaining_b, replacement])
    faces = [p for p in polygonize(network) if union.covers(p.representative_point())]
    assigned = [[], []]
    for face in faces:
        overlaps = [face.intersection(a).area, face.intersection(b).area]
        assigned[0 if overlaps[0] > overlaps[1] else 1].append(face)
    if not all(assigned):
        raise ValueError('ZANIK_POLIGONU')
    new_a, new_b = (unary_union(group) for group in assigned)
    if not new_a.is_valid or not new_b.is_valid:
        raise ValueError('NIEPOPRAWNA_GEOMETRIA')
    if signature(new_a) != signature(a) or signature(new_b) != signature(b):
        raise ValueError('ZMIANA_LICZBY_CZESCI_LUB_OTWOROW')
    if not shapely.coverage_is_valid([new_a, new_b]):
        raise ValueError('NIEZGODNE_KRAWEDZIE_LUB_NAKLADANIE')
    if new_a.union(new_b).symmetric_difference(union).area > 1e-4:
        raise ValueError('ZMIANA_ZEWNETRZNEGO_POKRYCIA')
    # Zewnętrzne krawędzie pary nie mogą zmienić kształtu ani nodingu.
    if new_a.union(new_b).boundary.hausdorff_distance(union.boundary) > 1e-6:
        raise ValueError('ZMIANA_ZEWNETRZNYCH_KRAWEDZI')
    return new_a, new_b

def check_addresses(a, b, new_a, new_b, pair_keys, points, point_keys, point_tree):
    changed = a.symmetric_difference(new_a).union(b.symmetric_difference(new_b))
    if changed.is_empty:
        return
    for index in point_tree.query(changed, predicate='intersects'):
        index = int(index)
        point = points[index]
        for original, updated, own_key in zip((a, b), (new_a, new_b), pair_keys):
            # Kontrola rzeczywistego położenia każdego punktu, również NULL
            # i rekordów z niespójną etykietą komisji.
            if original.covers(point) != updated.covers(point):
                raise ValueError('ZMIANA_PRZYPISANIA_ADRESU')
            if original.contains(point) and not updated.contains(point):
                raise ValueError('ADRES_PRZENIESIONY_NA_GRANICE')

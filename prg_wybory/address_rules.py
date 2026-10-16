"""Parser extracted and generalized from the Lublin project; no city defaults."""

import re, unicodedata, difflib

from collections import defaultdict

from dataclasses import dataclass

def key(text):
    """Normalizacja wyłącznie do porównania; wynik zachowuje pisownię PRG."""
    text = str(text or '').casefold().replace('ł', 'l')
    text = ''.join(c for c in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(c))
    text = re.sub(r'\b(?:ksiedza|ks)\b', 'ks', text)
    text = re.sub(r'\b(?:generala|general|gen)\b', 'gen', text)
    text = re.sub(r'\b(?:doktora|dra|dr)\b', 'dr', text)
    text = re.sub(r'\b(?:profesora|prof)\b', 'prof', text)
    text = re.sub(r'\b(?:imienia|im)\b', '', text)
    text = re.sub(r'[^\w\s-]', ' ', text)
    return ' '.join(text.split())

def name_key(text):
    text = key(text)
    # Powtórzone oznaczenia, np. „pl. Plac ...”, „ul. Aleja ...”.
    return re.sub(r'^(?:(?:ul|ulica|al|aleja|aleje|pl|plac|skwer)\s+)+', '', text)

class StreetIndex:
    def __init__(self, records):
        self.literal = defaultdict(set)
        self.exact = defaultdict(set)
        self.alias = defaultdict(set)
        self.names = set()
        for record in records:
            name = str(record.get('NAZWA_ULC') or '').strip()
            if not name:
                continue
            self.names.add(name)
            self.literal[' '.join(name.casefold().split())].add(name)
            self.exact[key(name)].add(name)
            self.alias[name_key(name)].add(name)
            # PRG przechowuje człony patrona również w oddzielnych polach.
            term1 = str(record.get('NAZWA_TER1') or '').strip()
            term2 = str(record.get('NAZWA_TER2') or '').strip()
            if term1:
                self.alias[name_key(f'{term2} {term1}')].add(name)
            # Brak tytułu w opisie: tylko jednoznaczne dopasowanie.
            without_title = re.sub(r'^(?:dr|ks|prof|gen)\s+', '', name_key(name))
            self.alias[without_title].add(name)
        if not self.names:
            raise ValueError('Nie znaleziono nazw ulic w wybranych danych PRG.')

    def match(self, name):
        matches = (self.literal.get(' '.join(name.casefold().split()))
                   or self.exact.get(key(name)) or self.alias.get(name_key(name), set()))
        return sorted(matches)

def split_description(text):
    """Przecinki wewnątrz nawiasów i listy numerów pozostają przy ulicy."""
    text = re.sub(r'^\s*ULICA\s*:\s*', '', str(text or ''), flags=re.I)
    parts, buffer, depth = [], [], 0
    for char in text:
        if char == '(':
            depth += 1
        elif char == ')':
            depth = max(0, depth - 1)
        if char in ',;\n' and depth == 0:
            parts.append(''.join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
    parts.append(''.join(buffer).strip())
    result = []
    for part in filter(None, parts):
        # 3 Maja i 11 Listopada to nazwy ulic, a nie kolejne numery.
        if result and re.match(r'^\d+[A-Za-z]?(?:\s*(?:[-–—,/]|\(|$))', part):
            result[-1] += ', ' + part
        else:
            result.append(part)
    return result

def resolve(fragment, index):
    clean = re.sub(r'^(?:ul\.|ulica\s*:)\s*', '', fragment, flags=re.I).strip()
    # Szukamy najdłuższej nazwy; cyfry mogą należeć do nazwy (3 Maja).
    cuts = [len(clean)] + [m.start() for m in re.finditer(r'\s+', clean)][::-1]
    for cut in cuts:
        name, suffix = clean[:cut].strip(), clean[cut:].strip()
        if suffix and not re.match(r'^(?:\d|\(|od\b|do\b)', suffix, re.I):
            continue
        candidates = index.match(name)
        if len(candidates) == 1:
            return candidates[0] + (' ' + suffix if suffix else ''), 'PRG', ''
        if len(candidates) > 1:
            return fragment, 'NIEJEDNOZNACZNE', ' | '.join(candidates)
    suggestions = difflib.get_close_matches(name_key(clean), index.alias.keys(), n=3, cutoff=0.65)
    suggested_names = sorted({n for k in suggestions for n in index.alias[k]})
    return fragment, 'BRAK_W_PRG', ' | '.join(suggested_names)

def number(value):
    match = re.fullmatch(r'(\d+)([^\W\d_]*)', str(value).strip(), re.UNICODE)
    if not match:
        raise ValueError(f'Numer złożony lub niepoprawny: {value}')
    return int(match[1]), match[2].upper()

@dataclass
class Restriction:
    parity: int | None
    intervals: list
    exact: set

    def accepts(self, value):
        # Cała ulica obejmuje również numery złożone w PRG.
        if self.parity is None and not self.intervals and not self.exact:
            return True
        num, letter = number(value)
        if self.parity is not None and num % 2 != self.parity:
            return False
        if not self.intervals and not self.exact:
            return True
        if (num, letter) in self.exact:
            return True
        for lower, upper in self.intervals:
            # Goły koniec 41 obejmuje też 41A; koniec 41B ogranicza litery.
            above = lower is None or num > lower[0] or (num == lower[0] and letter >= lower[1])
            below = upper is None or num < upper[0] or (num == upper[0] and (not upper[1] or letter <= upper[1]))
            if above and below:
                return True
        return False

def parse_restriction(suffix):
    suffix = suffix.strip().casefold().replace('–', '-').replace('—', '-')
    parity = None
    tags = re.findall(r'\(([^()]*)\)', suffix)
    for tag in tags:
        if tag.strip() not in ('parzyste', 'nieparzyste'):
            raise ValueError(f'Nieobsługiwany nawias: {tag}')
        current = 0 if tag.strip() == 'parzyste' else 1
        if parity is not None and parity != current:
            raise ValueError('Sprzeczna parzystość')
        parity = current
    suffix = re.sub(r'\([^()]*\)', '', suffix).strip()
    if not suffix:
        return Restriction(parity, [], set())
    atom = r'\d+[^\W\d_]*'
    intervals, exact = [], set()
    for part in re.split(r'\s*[,;]\s*', suffix):
        open_range = re.fullmatch(fr'od\s+({atom})\s+do\s+końca', part)
        closed = re.fullmatch(fr'(?:od\s+)?({atom})\s*(?:-|do)\s*({atom})', part)
        if open_range:
            intervals.append((number(open_range[1]), None))
        elif closed:
            lower, upper = number(closed[1]), number(closed[2])
            if lower > upper:
                raise ValueError('Odwrócony zakres numerów')
            intervals.append((lower, upper))
        elif re.fullmatch(atom, part):
            exact.add(number(part))
        else:
            raise ValueError(f'Nieobsługiwane ograniczenie: {part}')
    return Restriction(parity, intervals, exact)

def split_rule(fragment, index):
    text, status, _ = resolve(fragment, index)
    if status != 'PRG':
        raise ValueError(f'Nazwa ulicy: {status}')
    names = [name for name in index.names if text == name or text.startswith(name + ' ')]
    name = max(names, key=len)
    return name, parse_restriction(text[len(name):])

def check_feature_type(original, name):
    if re.match(r'^(?:pl\.|plac\b|skwer\b)', original.strip(), re.I) and not re.match(r'^(?:pl\.|plac\b|skwer\b)', name, re.I):
        raise ValueError('Opis źródłowy oznacza plac/skwer, a nazwa PRG ulicę: ' + original)

from __future__ import annotations
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path


class DataError(ValueError):
    pass


def norm(value):
    text = str(value or '').casefold().replace('ł', 'l')
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def integer(value, label='liczba', minimum=0):
    try:
        number = Decimal(str(value).strip().replace('\u00a0', '').replace(' ', '').replace(',', '.'))
    except InvalidOperation as exc:
        raise DataError(f'{label}: niepoprawna liczba {value!r}') from exc
    if not number.is_finite() or number != number.to_integral_value() or number < minimum:
        raise DataError(f'{label}: oczekiwano liczby całkowitej >= {minimum}: {value!r}')
    return int(number)


def teryt(value):
    number = integer(value, 'TERYT')
    raw = str(value).strip()
    match = re.fullmatch(r'(\d+)(?:[.,]0+)?', raw)
    text = (match[1] if match else str(number)).zfill(6)
    if len(text) == 7:  # PRG TERC includes the municipality type digit.
        text = text[:6]
    if len(text) != 6:
        raise DataError(f'Niepoprawny kod gminy: {value}')
    return text


def key(city, number):
    return f'{teryt(city)}_{integer(number, "numer obwodu", 1)}'


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def save_csv(path, rows):
    import csv
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,delimiter=';')
        writer.writeheader(); writer.writerows(rows)


def load_config(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text(encoding='utf-8-sig'))
    if cfg.get('schema_version') != 1:
        raise DataError('Wymagana schema_version: 1')
    cfg['teryt'] = teryt(cfg['teryt'])
    if not str(cfg.get('election', '')).strip():
        raise DataError('Podaj election, np. prezydent_2025')
    cfg['_config_dir'] = str(path.parent)
    for spec in [cfg.get(k) for k in ('polygons','boundary','addresses','roads','descriptions','raster')]+cfg.get('rounds',[]):
        if spec and spec.get('path'): spec['path']=resolve(cfg,spec['path'])
    cfg['output']=resolve(cfg,cfg.get('output','wyniki'))
    return cfg


def resolve(cfg, path):
    p = Path(path)
    return str(p if p.is_absolute() else Path(cfg['_config_dir']) / p)

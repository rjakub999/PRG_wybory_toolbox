import unittest
import tempfile
import json
from pathlib import Path
from collections import Counter
import numpy as np
import shapely
from shapely.geometry import Point,box,LineString
from prg_wybory.common import integer,teryt,DataError
from prg_wybory.elections import prepare,vote_fields,join,read_table
from prg_wybory.basic import PythonBackend
from prg_wybory.backends import backend
from prg_wybory.spatial import audit,prepare_boundaries
from prg_wybory.address_rules import parse_restriction,StreetIndex,resolve,split_description
from prg_wybory.roads import fit


def point(x,y,n,identity,city='106101'):
    return dict(geometry=Point(x,y),properties=dict(TERYT=city,NR_KOMISJI=n,ID_ADRESU=identity,STATUS='ZRODLO' if n else 'BRAK_PRZYPISANIA'))


class TableTests(unittest.TestCase):
    def test_integer_and_teryt(self):
        self.assertEqual(integer('1.000000000000000'),1)
        self.assertEqual(teryt('0663011'),'066301')
        for v in ('NaN','2.2','-1',''):
            with self.assertRaises(DataError): integer(v)

    def test_sum_duplicate_and_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'t.csv'
            header='Numer;Teryt;Typ obwodu;Liczba głosów ważnych oddanych łącznie;ALFA Jan;BETA Anna\n'
            p.write_text(header+'1;066301;stały;10;6;4\n',encoding='utf-8-sig')
            t=prepare(p,'066301'); self.assertEqual(t['rows'][0]['ID_OBWODU'],'066301_1')
            p.write_text(header+'1;066301;stały;11;6;4\n',encoding='utf-8')
            with self.assertRaises(DataError): prepare(p,'066301')
            p.write_text(header+'1;066301;stały;10;6;4\n1;066301;stały;10;6;4\n',encoding='utf-8')
            with self.assertRaises(DataError): prepare(p,'066301')
        a=vote_fields(dict(GLOSY_WAZNE=0,GLOSY_NIEWAZNE=1,votes={'A':0,'B':0}),1)
        self.assertEqual(a['T1_LIDER'],'BRAK_GLOSOW'); self.assertIsNone(a['T1_PCT_A'])
        a=vote_fields(dict(GLOSY_WAZNE=10,GLOSY_NIEWAZNE=1,votes={'A':5,'B':5}),2)
        self.assertEqual(a['T2_LIDER'],'REMIS'); self.assertEqual(a['T2_KLASA'],3)

    def test_missing_regular_blocks_join(self):
        boundary=prepare_boundaries([dict(geometry=box(0,0,1,1),properties={'n':1})],'106101','n')
        table={'rows':[dict(ID_OBWODU='106101_2',STALY=True)]}
        with self.assertRaises(DataError): join(boundary,[table,table])


class BackendTests(unittest.TestCase):
    def test_esri_unimplemented(self):
        with self.assertRaisesRegex(DataError,'niezaimplementowany'):
            backend({'backends':{'voronoi':'esri'}},'voronoi')

    def test_vote_majority_and_preservation(self):
        pts=[point(x,0,1 if i<3 else 2,str(i)) for i,x in enumerate([1,2,3,4,5])]+[point(0,0,None,'target')]
        out=PythonBackend().neighbors(pts,apply=True)
        self.assertEqual(out[-1]['properties']['NR_KOMISJI'],1)
        self.assertEqual(out[-1]['properties']['PEWNOSC'],.6)
        self.assertIsNone(pts[-1]['properties']['NR_KOMISJI'])
        self.assertEqual([r['properties']['NR_KOMISJI'] for r in out[:-1]],[1,1,1,2,2])

    def test_distance_tie_and_city(self):
        pts=[point(-1,0,1,'a'),point(1,0,2,'b'),point(0,0,None,'c')]
        out=PythonBackend().neighbors(pts,k=1,min_neighbors=1)
        self.assertEqual(out[-1]['properties']['STATUS'],'REMIS_ODLEGLOSCI')
        pts=[point(1,0,1,'a','066301'),point(0,0,None,'b')]
        out=PythonBackend().neighbors(pts,k=1,min_neighbors=1)
        self.assertIsNone(out[-1]['properties']['PROPONOWANY_NR'])

    def test_no_cascade(self):
        pts=[point(0,0,1,'a'),point(9,0,None,'b'),point(18,0,None,'c')]
        out=PythonBackend().neighbors(pts,k=1,min_neighbors=1,max_distance=10,apply=True)
        self.assertEqual(out[1]['properties']['NR_KOMISJI'],1)
        self.assertIsNone(out[2]['properties']['NR_KOMISJI'])

    def test_voronoi_collinear_holes_duplicates(self):
        boundary=box(0,0,10,10).difference(box(4,4,6,6))
        pts=[point(1,1,1,'a'),point(5,1,2,'b'),point(9,1,3,'c')]
        result=PythonBackend().voronoi(pts,boundary)
        report=audit(result,boundary)
        self.assertAlmostEqual(report['missing_area_m2'],0)
        self.assertAlmostEqual(report['overlap_area_m2'],0)
        for p in pts:
            own=next(r for r in result if r['properties']['NR_KOMISJI']==p['properties']['NR_KOMISJI'])
            self.assertTrue(own['geometry'].covers(p['geometry']))
        with self.assertRaisesRegex(DataError,'Sprzeczne'):
            PythonBackend().voronoi([point(1,1,1,'a'),point(1,1,2,'b')],boundary)


class AddressTests(unittest.TestCase):
    def test_parity_ranges(self):
        rule=parse_restriction('1-11 (nieparzyste)')
        self.assertTrue(rule.accepts('11A')); self.assertFalse(rule.accepts('10'))
        self.assertFalse(rule.accepts('13'))
        with self.assertRaises(ValueError): parse_restriction('z wyjątkiem 5')

    def test_street_digits_and_diacritics(self):
        index=StreetIndex([{'NAZWA_ULC':s} for s in ['3 Maja','Sadowa','Sądowa']])
        self.assertEqual(resolve('ul. 3 Maja 1-11',index)[0],'3 Maja 1-11')
        self.assertEqual(resolve('Sądowa 1',index)[0],'Sądowa 1')
        self.assertEqual(len(split_description('3 Maja 1, 3, 5; Sadowa 2')),2)


class RoadTests(unittest.TestCase):
    def test_shared_boundary_and_address_protection(self):
        left=shapely.Polygon([(0,0),(5,0),(4,5),(5,10),(0,10)])
        right=box(0,0,10,10).difference(left)
        rows=[dict(geometry=g,properties={'NR_KOMISJI':i}) for i,g in enumerate([left,right],1)]
        roads=[dict(geometry=LineString([(5,0),(5,10)]))]
        pts=[point(2,5,1,'a'),point(8,5,2,'b')]
        out,report=fit(rows,roads,pts,max_distance=2,min_length=.1,min_support=.5,angle=40)
        self.assertTrue(shapely.union_all([r['geometry'] for r in out]).equals(box(0,0,10,10)))
        self.assertAlmostEqual(audit(out)['overlap_area_m2'],0)
        protected=pts+[point(4.5,5,2,'c')]
        out,report=fit(rows,roads,protected,max_distance=2,min_length=.1,min_support=.5,angle=40)
        self.assertTrue(out[0]['geometry'].equals(left))


class RasterTests(unittest.TestCase):
    def test_rgb_two_regions(self):
        import rasterio
        from rasterio.transform import from_origin
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.tif'
            rgb=np.full((3,20,20),255,dtype='uint8'); rgb[:, :, 10]=np.array([220,0,0])[:,None]
            with rasterio.open(p,'w',driver='GTiff',height=20,width=20,count=3,dtype='uint8',crs='EPSG:2180',transform=from_origin(0,20,1,1)) as dst: dst.write(rgb)
            seeds=[point(3,10,1,'a'),point(16,10,2,'b')]
            rows=PythonBackend().raster(p,box(0,0,20,20),seeds,'EPSG:2180',closing_pixels=0,min_seeds=1,boundary_margin=0)
            self.assertEqual({r['properties']['NR_KOMISJI'] for r in rows},{1,2})
            self.assertAlmostEqual(audit(rows,box(0,0,20,20))['missing_area_m2'],0)
            # Default closing must not open the separating line at the raster edge.
            closed=PythonBackend().raster(p,box(0,0,20,20),seeds,'EPSG:2180',closing_pixels=1,min_seeds=1,boundary_margin=0)
            self.assertEqual({r['properties']['NR_KOMISJI'] for r in closed},{1,2})
            with self.assertRaisesRegex(DataError,'całego'):
                PythonBackend().raster(p,box(-5,0,20,20),seeds,'EPSG:2180')


class ResumeTests(unittest.TestCase):
    def test_changed_config_and_checkpoint_are_rejected(self):
        from unittest.mock import patch
        from prg_wybory.pipeline import run
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cfg=root/'cfg.json'
            cfg.write_text(json.dumps(dict(schema_version=1,teryt='106101',election='test',city='Test',output='out')),encoding='utf-8')
            def stage(config,out):
                (out/'01_test.json').write_text('{}',encoding='utf-8')
                return {}
            with patch('prg_wybory.pipeline.preflight',return_value={}),patch('prg_wybory.pipeline.source_fingerprints',return_value={}),patch('prg_wybory.pipeline.stage_boundaries',side_effect=stage):
                out=run(cfg,through='boundaries',log=lambda _:None)
                run(cfg,through='boundaries',resume=out,log=lambda _:None)
                (out/'01_test.json').write_text('{"changed":true}',encoding='utf-8')
                with self.assertRaisesRegex(DataError,'Zmieniono plik'):
                    run(cfg,through='boundaries',resume=out,log=lambda _:None)
                c=json.loads(cfg.read_text()); c['election']='other'; cfg.write_text(json.dumps(c))
                with self.assertRaisesRegex(DataError,'Zmieniła'):
                    run(cfg,through='boundaries',resume=out,log=lambda _:None)

if __name__=='__main__': unittest.main()

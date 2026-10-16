"""ArcPy integration checks; skipped in environments without ArcGIS."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

try:
    import arcpy
except (ImportError, RuntimeError):
    arcpy = None

@unittest.skipIf(arcpy is None, 'Requires licensed ArcPy')
class ConfigurationTests(unittest.TestCase):
    def test_output_dialog_and_default_extension(self):
        path = Path(__file__).resolve().parents[1] / 'PRGWybory.pyt'
        loader = importlib.machinery.SourceFileLoader('prg_toolbox_config_test', str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        tool = module.Konfiguracja()
        params = tool.getParameterInfo()
        self.assertEqual(params[9].direction, 'Output')
        self.assertEqual(params[9].filter.list, ['json'])
        self.assertEqual(module.CalyProces().getParameterInfo()[0].direction, 'Input')
        with tempfile.TemporaryDirectory() as temp:
            params[9].value = str(Path(temp) / 'nowa_konfiguracja')
            tool.updateParameters(params)
            self.assertTrue(params[9].valueAsText.endswith('.json'))

    def test_create_new_configuration_through_geoprocessing(self):
        path = Path(__file__).resolve().parents[1] / 'PRGWybory.pyt'
        toolbox = arcpy.ImportToolbox(str(path))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ['T1.csv', 'T2.csv']:
                (root / name).write_text('a;b\n1;2\n', encoding='utf-8')
            output = root / 'new.json'
            args = ['Test', '106101', 'prezydent_2025', str(root/'obwody.geojson'),
                    'NR_OBWODU', str(root/'T1.csv'), str(root/'T2.csv'), str(root),
                    2180, str(output), 'python', 'python', 'python']
            result = toolbox.Konfiguracja(*args)
            self.assertTrue(output.is_file())
            self.assertEqual(Path(result.getOutput(0)), output)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['teryt'], '106101')
            before = output.read_bytes()
            with self.assertRaises(Exception):
                toolbox.Konfiguracja(*args)
            self.assertEqual(output.read_bytes(), before)

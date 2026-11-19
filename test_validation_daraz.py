"""La validation d'un echantillon ne doit jamais ecraser le CSV complet."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import validate_daraz as validation


class ValidationTests(unittest.TestCase):
    def test_sample_keeps_main_dataset_unchanged(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                target = Path("output/produits_daraz.csv")
                target.parent.mkdir()
                target.write_bytes(b"dataset complet a conserver")
                product = {"id": 1, "url": "https://www.daraz.pk/a", "sous_categorie": "Montres", "categorie": "Electronique"}

                def fake_run(**kwargs):
                    kwargs["output"].write_text("echantillon", encoding="utf-8")

                with patch.object(validation.main, "read_products", return_value=[product]), patch.object(validation.main, "run", side_effect=fake_run), patch.object(validation, "capture_pages", return_value=(validation.ds.fetch, validation.pm.navigate)), patch.object(validation, "analyse", return_value={}), contextlib.redirect_stdout(io.StringIO()):
                    validation.run_stage("first10")
                self.assertEqual(target.read_bytes(), b"dataset complet a conserver")
                self.assertEqual(Path("output/validation/first10/produits_daraz.csv").read_text(), "echantillon")
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()

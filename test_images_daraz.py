"""Tests hors reseau de la reprise et des reponses incompletes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import download_images_daraz as dl


class DownloadTests(unittest.TestCase):
    def test_resume_skips_decodable_image_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "1").mkdir()
            Image.new("RGB", (240, 240)).save(root / "1/image_1.png")
            with patch.object(dl, "IMAGES_ROOT", root), patch.object(dl, "get_session") as session:
                self.assertEqual(dl.download_one(("1", 1, "https://example.test/a", True))[0], "skip")
                session.assert_not_called()

    def test_invalid_existing_file_is_retried_and_html_never_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "1").mkdir()
            bad = root / "1/image_1.jpg"
            bad.write_bytes(b"")
            with patch.object(dl, "IMAGES_ROOT", root), patch.object(dl, "get_session") as factory:
                response = factory.return_value.get.return_value
                response.iter_content.return_value = [b"<html>blocked</html>"]
                self.assertEqual(dl.download_one(("1", 1, "https://example.test/a", True))[0], "error")
                self.assertEqual(bad.read_bytes(), b"")
                self.assertTrue((root / "1/image_1.part").exists())

    def test_original_format_detected_from_bytes_and_atomic_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (240, 240)).save(source)
            with patch.object(dl, "IMAGES_ROOT", root), patch.object(dl, "get_session") as factory:
                factory.return_value.get.return_value.iter_content.return_value = [source.read_bytes()]
                status, name = dl.download_one(("1", 1, "https://example.test/a.jpg", True))
                self.assertEqual(status, "ok")
                self.assertEqual(Path(name).suffix, ".png")
                self.assertFalse((root / "1/image_1.part").exists())


if __name__ == "__main__":
    unittest.main()

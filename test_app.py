import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from app import repack, normalize_db_padding


class DestinationProtection(unittest.TestCase):
    def test_new_page_padding_is_repaired_without_changing_sqlite_content(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'pages.db'
            original = bytearray(b'X' * 2048)
            original[:16] = b'SQLite format 3\0'
            original[16:18] = b'\x04\x00'
            original[20] = 16
            original[1008:1024] = b'\x10' * 16
            original[2032:2048] = bytes(16)
            path.write_bytes(original)
            self.assertEqual(normalize_db_padding(path), 1)
            result = path.read_bytes()
            self.assertEqual(result[:2032], original[:2032])
            self.assertEqual(result[2032:], b'\x10' * 16)
            self.assertEqual(normalize_db_padding(path), 0)

    def test_output_inside_input_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            original = root / 'original.lpk'
            original.write_bytes(b'original')
            with self.assertRaisesRegex(ValueError, 'fuera'):
                repack(original, root, root / 'new.lpk', threading.Event(), lambda _: None)

    def test_corrupt_database_never_publishes_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            original = root / 'original.lpk'
            original.write_bytes(b'original')
            source = root / 'source'
            source.mkdir()
            (source / 'broken.db').write_bytes(b'not sqlite')
            with patch('app.call_backend', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'SQLite'):
                    repack(original, source, root / 'new.lpk', threading.Event(), lambda _: None)
            self.assertFalse((root / 'new.lpk').exists())
            self.assertFalse(list(root.glob('loa_repack_*')))

    def test_cancel_discards_temporary_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            original = root / 'original.lpk'
            original.write_bytes(b'original')
            source = root / 'source'
            source.mkdir()
            (source / 'test.txt').write_bytes(b'content')
            event = threading.Event()
            event.set()
            with patch('app.call_backend', return_value=[]):
                with self.assertRaisesRegex(RuntimeError, 'cancelada'):
                    repack(original, source, root / 'new.lpk', event, lambda _: None)
            self.assertFalse((root / 'new.lpk').exists())
            self.assertFalse(list(root.glob('loa_repack_*')))

    def test_original_and_existing_destination_are_never_overwritten(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            original = root / 'original.lpk'
            database = root / 'source'
            database.mkdir()
            existing = root / 'existing.lpk'
            for path in (original, existing):
                path.write_bytes(b'keep me')
            for output in (original, existing):
                with self.assertRaises(ValueError):
                    repack(original, database, output, threading.Event(), lambda _: None)
                self.assertEqual(output.read_bytes(), b'keep me')

    def test_uncommitted_wal_blocks_repack(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            original = root / 'original.lpk'
            database = root / 'source'
            database.mkdir()
            original.write_bytes(b'keep me')
            (database / 'test.db-wal').touch()
            output = root / 'new.lpk'
            with self.assertRaisesRegex(ValueError, 'WAL'):
                repack(original, database, output, threading.Event(), lambda _: None)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()

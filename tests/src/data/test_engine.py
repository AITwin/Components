import unittest
from unittest.mock import Mock, patch

from sqlalchemy.engine.base import Engine

from src.data.engine import LazyEngineVariable, lazy_engine


class TestLazyEngineVariable(unittest.TestCase):
    def test_engine_initialization(self):
        # Mock os.environ.get
        with patch("os.environ.get") as mock_get:
            # IN memory database
            mock_get.return_value = "sqlite:///:memory:"
            self.assertEqual(lazy_engine.engine.url.database, ":memory:")

    def test_connection_property(self):
        mock_engine = Mock(spec=Engine)
        lazy_engine = LazyEngineVariable()
        lazy_engine._engine = mock_engine

        connection = lazy_engine.connection

        self.assertEqual(connection, mock_engine.connect.return_value)
        mock_engine.connect.assert_called_once()

    def test_engine_disposal_on_del(self):
        mock_engine = Mock(spec=Engine)
        lazy_engine = LazyEngineVariable()
        lazy_engine._engine = mock_engine

        del lazy_engine

        mock_engine.dispose.assert_called_once()

from __future__ import annotations

from skyrict_common.logging import configure_logging, get_logger


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test")
        assert logger is not None


class TestConfigureLogging:
    def test_configure_json(self):
        configure_logging(log_level="DEBUG", json_output=True)
        logger = get_logger("test_config")
        assert logger is not None

    def test_configure_console(self):
        configure_logging(log_level="INFO", json_output=False)
        logger = get_logger("test_console")
        assert logger is not None

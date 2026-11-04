import logging
import os
from unittest.mock import MagicMock, patch

from config import Settings, _mask_dsn, _resolve_env_file


def test_mask_dsn():
    assert _mask_dsn(None) == "None"
    assert _mask_dsn("") == "None"
    assert _mask_dsn("postgresql://user:secret@localhost:5432/db") == "postgresql://user:****@localhost:5432/db"
    assert _mask_dsn("postgresql://localhost:5432/db") == "postgresql://localhost:5432/db"


def test_resolve_env_file_default():
    with patch.dict(os.environ, {}, clear=True):
        res = _resolve_env_file()
        assert res.endswith(".env")


def test_resolve_env_file_custom(tmp_path):
    custom_env = tmp_path / "custom.env"
    custom_env.write_text("GRAPH_DATA_MODE=live\n")
    with patch.dict(os.environ, {"ENV_CONFIG_FILE": str(custom_env)}):
        res = _resolve_env_file()
        assert res == str(custom_env)


def test_crm_compute_pool_in_settings_and_summary():
    # Defaults to None and surfaces in the config summary. Disable .env loading
    # (_env_file=None) and drop the var from the shell env so the default is
    # observable even after live infra populates the repo .env.
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FLINK_CRM_COMPUTE_POOL_ID", None)
        default_settings = Settings(_env_file=None)
        assert default_settings.FLINK_CRM_COMPUTE_POOL_ID is None
        assert default_settings.summary()["FLINK_CRM_COMPUTE_POOL_ID"] == "None"
    # Carries a provided value through to the summary.
    settings = Settings(FLINK_CRM_COMPUTE_POOL_ID="lfcp-crm", _env_file=None)
    assert settings.FLINK_CRM_COMPUTE_POOL_ID == "lfcp-crm"
    assert settings.summary()["FLINK_CRM_COMPUTE_POOL_ID"] == "lfcp-crm"


def test_settings_summary_and_log():
    settings = Settings(
        DATABASE_URL="postgresql://user:secret@localhost:5432/mydb",
    )
    summary = settings.summary()
    assert summary["DATABASE_URL"] == "postgresql://user:****@localhost:5432/mydb"

    mock_logger = MagicMock(spec=logging.Logger)
    settings.log_summary(mock_logger)
    assert mock_logger.info.called

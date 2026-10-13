from contextlib import contextmanager
from dataclasses import replace

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.config.settings import Settings, load_settings
from app.db.checkpoint import build_conninfo, open_checkpointer

ENV_VALUES = {
    "DEEPSEEK_API_KEY": "test-key",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "test-password",
    "POSTGRES_DB": "zhizhou",
    "POSTGRES_PORT": "5432",
}


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    for key in ENV_VALUES:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in ENV_VALUES.items()),
        encoding="utf-8",
    )
    return path


def test_file_settings_and_environment_priority(env_file, monkeypatch):
    import os

    before = dict(os.environ)
    settings = load_settings(env_file)
    assert settings.postgres_port == 5432
    assert settings.postgres_host == "127.0.0.1"
    assert settings.model_name == "deepseek-flash"
    assert settings.model_base_url == "https://api.deepseek.com"
    assert dict(os.environ) == before
    assert "test-key" not in repr(settings)
    assert "test-password" not in repr(settings)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-key")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    settings = load_settings(env_file)
    assert settings.deepseek_api_key == "environment-key"
    assert settings.postgres_port == 5433


@pytest.mark.parametrize("key", ENV_VALUES)
@pytest.mark.parametrize("value", ["", " \t"])
def test_required_settings_reject_blank_environment_override(
    env_file, monkeypatch, key, value
):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=key):
        load_settings(env_file)


@pytest.mark.parametrize("port", ["not-a-number", "0", "65536"])
def test_invalid_port_does_not_disclose_value(env_file, monkeypatch, port):
    monkeypatch.setenv("POSTGRES_PORT", port)
    with pytest.raises(ValueError, match="POSTGRES_PORT") as error:
        load_settings(env_file)
    if port == "not-a-number":
        assert port not in str(error.value)


def test_missing_file_can_use_environment_only(tmp_path, monkeypatch):
    for key, value in ENV_VALUES.items():
        monkeypatch.setenv(key, value)
    assert load_settings(tmp_path / "missing.env").postgres_db == "zhizhou"


def test_missing_settings_are_named(tmp_path, monkeypatch):
    for key in ENV_VALUES:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError) as error:
        load_settings(tmp_path / "missing.env")
    assert all(key in str(error.value) for key in ENV_VALUES)


@pytest.fixture
def settings():
    return Settings("key", "postgres", "password", "zhizhou", 5432)


def test_connection_parameters_preserve_special_characters(settings):
    password = " p@ss:/?#='\\ word "
    settings = replace(
        settings, postgres_password=password, postgres_user="user name", postgres_db="db'name"
    )
    values = conninfo_to_dict(build_conninfo(settings))
    assert values["password"] == password
    assert values["user"] == "user name"
    assert values["dbname"] == "db'name"
    assert values["port"] == "5432"


@pytest.mark.parametrize("failure", [None, "setup", "body"])
def test_checkpointer_initializes_and_closes_even_on_failure(
    settings, monkeypatch, failure
):
    from app.db import checkpoint

    events = []

    class Saver:
        def setup(self):
            events.append("setup")
            if failure == "setup":
                raise RuntimeError("setup failed")

    saver = Saver()

    @contextmanager
    def connection(conninfo):
        assert conninfo_to_dict(conninfo)["dbname"] == "zhizhou"
        events.append("open")
        try:
            yield saver
        finally:
            events.append("close")

    monkeypatch.setattr(checkpoint.PostgresSaver, "from_conn_string", connection)

    def use_connection():
        with open_checkpointer(settings) as actual:
            assert actual is saver
            events.append("body")
            if failure == "body":
                raise RuntimeError("body failed")

    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            use_connection()
    else:
        use_connection()
    assert events == (["open", "setup", "close"] if failure == "setup" else [
        "open", "setup", "body", "close"
    ])

import asyncio
import gc
import threading
import warnings

import pytest

import tabsight.settings as cfg
from tabsight.warnings import InvalidSpecError, TabsightError, TabsightWarning, safe_repr, warn


@pytest.fixture(autouse=True)
def _reset() -> None:
    cfg.reset_defaults()


def test_defaults() -> None:
    s = cfg.current()
    assert s.locale == "en_US" and s.currency == "USD" and s.strict is False


def test_set_defaults_is_process_wide() -> None:
    cfg.set_defaults(locale="en_IE", currency="EUR")
    seen: list[str] = []
    t = threading.Thread(target=lambda: seen.append(cfg.current().locale))
    t.start()
    t.join()
    assert seen == ["en_IE"]


def test_scoped_config_restores_and_nests() -> None:
    with cfg.config(locale="de_DE"):
        assert cfg.current().locale == "de_DE"
        with cfg.config(currency="EUR"):
            assert cfg.current().locale == "de_DE"
            assert cfg.current().currency == "EUR"
        assert cfg.current().currency == "USD"
    assert cfg.current().locale == "en_US"


def test_scoped_config_is_isolated_between_concurrent_tasks() -> None:
    async def request(locale: str) -> str:
        with cfg.config(locale=locale):
            await asyncio.sleep(0.01)
            return cfg.current().locale

    async def main() -> list[str]:
        return list(await asyncio.gather(request("de_DE"), request("fr_FR"), request("en_IN")))

    assert asyncio.run(main()) == ["de_DE", "fr_FR", "en_IN"]


def test_scoped_config_is_isolated_between_threads() -> None:
    results: dict[str, str] = {}
    barrier = threading.Barrier(2)

    def worker(locale: str) -> None:
        with cfg.config(locale=locale):
            barrier.wait()
            results[locale] = cfg.current().locale

    threads = [threading.Thread(target=worker, args=(loc,)) for loc in ("de_DE", "fr_FR")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == {"de_DE": "de_DE", "fr_FR": "fr_FR"}


def test_config_without_with_warns() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg.config(locale="de_DE")
        gc.collect()
    assert any("only works in a `with` block" in str(w.message) for w in caught)
    assert cfg.current().locale == "en_US"


def test_resolve_per_call_wins_and_ignores_none() -> None:
    with cfg.config(locale="de_DE"):
        assert cfg.resolve(locale="fr_FR", currency=None).locale == "fr_FR"
        assert cfg.resolve().locale == "de_DE"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("locale", "en-US"),
        ("locale", "<script>"),
        ("currency", "euro"),
        ("currency", "EU"),
        ("fiscal_start", 13),
        ("fiscal_start", True),
        ("week_start", "friday"),
        ("tz", "Europe/Dublin; rm -rf"),
        ("theme", "Dark Mode"),
        ("palette", "x" * 40),
        ("top", 0),
        ("strict", "yes"),
        ("max_size_mb", 10_000),
        ("min_group_size", 1),
    ],
)
def test_invalid_settings_are_rejected(name: str, value: object) -> None:
    with pytest.raises(InvalidSpecError):
        cfg.set_defaults(**{name: value})
    with pytest.raises(InvalidSpecError), cfg.config(**{name: value}):
        pass


def test_unknown_setting_suggests_a_name() -> None:
    with pytest.raises(InvalidSpecError, match="did you mean 'currency'"):
        cfg.set_defaults(curency="EUR")


def test_strict_mode_turns_warnings_into_errors() -> None:
    with pytest.warns(TabsightWarning):
        warn("hello")
    with cfg.config(strict=True), pytest.raises(TabsightError):
        warn("hello")


def test_safe_repr_truncates_and_escapes() -> None:
    text = safe_repr("line1\nline2\x1b[31m" + "x" * 500)
    assert "\n" not in text and "\x1b" not in text
    assert len(text) <= 60

    class Hostile:
        def __repr__(self) -> str:
            raise RuntimeError("boom")

    assert safe_repr(Hostile()) == "<Hostile>"

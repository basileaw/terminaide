"""Theme typography/spacing options and their CSS custom-property wiring.

ThemeConfig keys are exposed to the page as ``--<key>`` CSS custom
properties, with underscores mapped to hyphens (``border_radius`` ->
``--border-radius``). The template must reference exactly those names, or
the option silently does nothing.
"""

from pathlib import Path

from terminaide.core.models import ThemeConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_TEMPLATE = REPO_ROOT / "terminaide" / "templates" / "terminal.html"


def test_theme_backward_compatible_defaults():
    """New options default to None so existing themes are unaffected."""
    theme = ThemeConfig()
    for field in ("padding", "border_radius", "box_shadow"):
        assert getattr(theme, field) is None


def test_theme_accepts_styling_options():
    theme = ThemeConfig(padding="0", border_radius="0px", box_shadow="none")
    dumped = theme.model_dump()
    assert dumped["padding"] == "0"
    assert dumped["border_radius"] == "0px"
    assert dumped["box_shadow"] == "none"


def test_styling_keys_survive_model_dump():
    """The route rendering path serializes the theme with model_dump(); the
    styling keys must be present for the template to consume."""
    keys = ThemeConfig().model_dump().keys()
    assert {"padding", "border_radius", "box_shadow"} <= set(keys)


def test_template_underscore_theme_keys_become_hyphenated_css_vars():
    """The template must translate snake_case keys to hyphenated CSS vars."""
    html = TERMINAL_TEMPLATE.read_text(encoding="utf-8")
    assert "key.replace(/_/g, '-')" in html


def test_template_css_reads_the_documented_var_names():
    html = TERMINAL_TEMPLATE.read_text(encoding="utf-8")
    assert "var(--padding," in html
    assert "var(--border-radius," in html
    assert "var(--box-shadow," in html
    # The underscore spellings would never match the emitted properties.
    assert "var(--border_radius" not in html
    assert "var(--box_shadow" not in html

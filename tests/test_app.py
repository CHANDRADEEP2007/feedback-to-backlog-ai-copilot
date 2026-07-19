from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_app_renders_without_exception() -> None:
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)

    app.run()

    assert not app.exception
    architecture_control = next(
        control for control in app.radio if control.label == "Architecture view"
    )
    assert architecture_control.value == "Current state"

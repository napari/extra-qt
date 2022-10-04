from enum import EnumMeta
from importlib import import_module
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from jinja2 import pass_context
from qtpy.QtCore import QObject, Signal
from qtpy.QtWidgets import QApplication

if TYPE_CHECKING:
    from mkdocs_macros.plugin import MacrosPlugin

EXAMPLES = Path(__file__).parent.parent / "examples"
IMAGES = Path(__file__).parent / "images"
IMAGES.mkdir(exist_ok=True, parents=True)
# for p in IMAGES.glob("*.png"):
#     p.unlink()


def define_env(env: "MacrosPlugin"):
    @env.macro
    @pass_context
    def insert_example(context, example: str, width: int = 500) -> list[Path]:
        """Grab the top widgets of the application."""
        if example.strip().startswith("```"):
            src = dedent(example.strip())
            src = "\n".join(src.split("\n")[1:-1])
            key = context["page"].title
        else:
            if not example.endswith(".py"):
                example += ".py"
            src = (EXAMPLES / example).read_text()
            key = example.replace(".py", "")
        output = f"```python\n{src}\n```\n\n"

        dest = IMAGES / f"{key}.png"
        if not (dest).exists():
            src = src.replace(
                "QApplication([])", "QApplication.instance() or QApplication([])"
            )
            src = src.replace("app.exec_()", "")
            _clear_widgets()
            exec(src)
            _grab(dest, width)

        output += f"![Image title](../images/{dest.name}){{ loading=lazy; width={width} }}\n\n"
        return output

    @env.macro
    def show_members(cls: str):
        # import class
        module, name = cls.rsplit(".", 1)
        _cls = getattr(import_module(module), name)
        inheritted_members = set()

        first_q = next(
            (
                b.__name__
                for b in _cls.__mro__
                if issubclass(b, QObject) and ".Qt" in b.__module__
            ),
            None,
        )

        for base in _cls.__bases__:
            inheritted_members.update({k for k in dir(base) if not k.startswith("_")})

        new_signals = {
            k
            for k, v in vars(_cls).items()
            if not k.startswith("_") and isinstance(v, Signal)
        }

        self_members = {
            k
            for k in _cls.__dict__.keys()
            if not k.startswith("_") and k not in inheritted_members | new_signals
        }

        enums = []
        for m in list(self_members):
            if isinstance(getattr(_cls, m), EnumMeta):
                self_members.remove(m)
                enums.append(m)

        out = ""
        if first_q:
            url = f"https://doc.qt.io/qt-6/{first_q.lower()}.html"
            out += f"## Qt Class\n\n<a href='{url}'>`{first_q}`</a>\n\n"

        out += ""

        if new_signals:
            out += "## New Signals\n\n"
            for sig in new_signals:
                out += f"### `{_cls.__name__}.{sig}`\n\n"

        if enums:
            out += "## Enums\n\n"
            for e in enums:
                out += f"### `{_cls.__name__}.{e}`\n\n"
                for m in getattr(_cls, e):
                    out += f"- `{m.name}`\n\n"

        out += dedent(
            f"""
        ## Methods

        ::: {cls}
            options:
              show_root_toc_entry: True
              heading_level: 3
              show_source: False
              show_inherited_members: false
              show_signature_annotations: True
              members: {self_members}
              docstring_style: numpy
              show_bases: False
        """
        )

        return out


def _grab(dest: str | Path, width) -> list[Path]:
    """Grab the top widgets of the application."""

    w = QApplication.topLevelWidgets()[-1]
    w.setFixedWidth(width)
    w.setMinimumHeight(50)
    w.grab().save(str(dest))


def _clear_widgets() -> None:
    for i in QApplication.topLevelWidgets():
        i.close()
        i.deleteLater()
        QApplication.processEvents()

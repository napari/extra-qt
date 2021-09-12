from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, FrozenSet, Optional, Tuple, Type, Union

from superqt.qtcompat import QT_VERSION
from superqt.qtcompat.QtCore import QObject, QPoint, QRect, QSize, Qt
from superqt.qtcompat.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QIconEngine,
    QPainter,
    QPalette,
    QPixmap,
    QTransform,
)
from superqt.qtcompat.QtWidgets import QApplication, QWidget

from ._animations import Animation

# A 16 pixel-high icon yields a font size of 14, which is pixel perfect
# for font-awesome. 16 * 0.875 = 14
# The reason why the glyph size is smaller than the icon size is to
# account for font bearing.
DEFAULT_SCALING_FACTOR = 0.875
DEFAULT_OPACITY = 1
ValidColor = Union[
    QColor,
    int,
    str,
    Qt.GlobalColor,
    Tuple[int, int, int, int],
    Tuple[int, int, int],
    None,
]
Unset = object()
_DEFAULT_STATE = (QIcon.State.Off, QIcon.Mode.Normal)
_states: Dict[FrozenSet[str], tuple[QIcon.State, QIcon.Mode]] = {
    frozenset({"on"}): (QIcon.State.On, QIcon.Mode.Normal),
    frozenset({"off"}): _DEFAULT_STATE,
    frozenset({"normal"}): _DEFAULT_STATE,
    frozenset({"active"}): (QIcon.State.Off, QIcon.Mode.Active),
    frozenset({"selected"}): (QIcon.State.Off, QIcon.Mode.Selected),
    frozenset({"disabled"}): (QIcon.State.Off, QIcon.Mode.Disabled),
    frozenset({"on", "normal"}): (QIcon.State.On, QIcon.Mode.Normal),
    frozenset({"on", "active"}): (QIcon.State.On, QIcon.Mode.Active),
    frozenset({"on", "selected"}): (QIcon.State.On, QIcon.Mode.Selected),
    frozenset({"on", "disabled"}): (QIcon.State.On, QIcon.Mode.Disabled),
    frozenset({"off", "normal"}): _DEFAULT_STATE,
    frozenset({"off", "active"}): (QIcon.State.Off, QIcon.Mode.Active),
    frozenset({"off", "selected"}): (QIcon.State.Off, QIcon.Mode.Selected),
    frozenset({"off", "disabled"}): (QIcon.State.Off, QIcon.Mode.Disabled),
}


@dataclass
class IconOptions:
    """The set of options needed to render a font in a single State/Mode."""

    glyph_key: str
    scale_factor: float = DEFAULT_SCALING_FACTOR
    color: ValidColor = None
    opacity: float = DEFAULT_OPACITY
    animation: Optional[Animation] = None
    transform: Optional[QTransform] = None

    @classmethod
    def _from_kwargs(
        cls, kwargs: dict, defaults: Optional[IconOptions] = None
    ) -> IconOptions:
        defaults = defaults or cls._defaults()
        kwargs = {
            f: getattr(defaults, f) if kwargs[f] is None else kwargs[f]
            for f in IconOptions.__dataclass_fields__  # type: ignore
        }
        return IconOptions(**kwargs)

    __defaults = None

    @classmethod
    def _defaults(cls):
        if cls.__defaults is None:
            cls.__defaults = IconOptions("")
        return cls.__defaults


class _QFontIconEngine(QIconEngine):
    def __init__(self, options: IconOptions):
        super().__init__()
        self._default_opts = options
        self._opts: DefaultDict[
            QIcon.State, Dict[QIcon.Mode, Optional[IconOptions]]
        ] = DefaultDict(dict)

    def clone(self) -> QIconEngine:  # pragma: no cover
        ico = _QFontIconEngine(None)  # type: ignore
        ico._opts = self._opts.copy()
        return ico

    def _get_opts(self, state, mode: QIcon.Mode) -> IconOptions:
        opts = self._opts[state].get(mode) or self._default_opts
        if opts.color is None:
            # use current palette in absense of color
            role = {
                QIcon.Mode.Disabled: QPalette.ColorGroup.Disabled,
                QIcon.Mode.Selected: QPalette.ColorGroup.Current,
                QIcon.Mode.Normal: QPalette.ColorGroup.Normal,
                QIcon.Mode.Active: QPalette.ColorGroup.Active,
            }
            opts.color = QApplication.palette().color(role[mode], QPalette.ButtonText)
        return opts

    def paint(
        self,
        painter: QPainter,
        rect: QRect,
        mode: QIcon.Mode,
        state: QIcon.State,
    ) -> None:
        opts = self._get_opts(state, mode)

        char, family, style = QFontIconStore.key2glyph(opts.glyph_key)

        # font
        font = QFont()
        font.setFamily(family)  # set sepeartely for Qt6
        font.setPixelSize(round(rect.height() * opts.scale_factor))
        if style:
            font.setStyleName(style)

        # color
        color_args = opts.color if isinstance(opts.color, tuple) else (opts.color,)

        # animation
        if opts.animation is not None:
            opts.animation.animate(painter, rect)

        # animation
        if opts.transform is not None:
            painter.setTransform(opts.transform, True)

        painter.save()
        painter.setPen(QColor(*color_args))
        painter.setOpacity(opts.opacity)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, char)
        painter.restore()

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, QRect(QPoint(0, 0), size), mode, state)
        return pixmap


class QFontIcon(QIcon):
    def __init__(self, options):
        self._engine = _QFontIconEngine(options)
        super().__init__(self._engine)

    def addState(
        self,
        state: QIcon.State = QIcon.State.Off,
        mode: QIcon.Mode = QIcon.Mode.Normal,
        glyph_key: Optional[str] = None,
        font_family: Optional[str] = None,
        font_style: Optional[str] = None,
        scale_factor: float = DEFAULT_SCALING_FACTOR,
        color: ValidColor = None,
        opacity: float = DEFAULT_OPACITY,
        animation: Optional[Animation] = None,
        transform: Optional[QTransform] = None,
    ):
        """Set icon options for a specific mode/state."""
        opts = IconOptions._from_kwargs(locals(), self._engine._default_opts)
        self._engine._opts[state][mode] = opts


class QFontIconStore(QObject):

    # map of key -> (font_family, font_style)
    _LOADED_KEYS: Dict[str, Tuple[str, Optional[str]]] = dict()

    # map of (font_family, font_style) -> character (char may include key)
    _CHARMAPS: Dict[Tuple[str, Optional[str]], Dict[str, str]] = dict()

    # singleton instance, use `instance()` to retrieve
    __instance: Optional[QFontIconStore] = None

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent=parent)
        if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
            # QT6 drops this
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    @classmethod
    def instance(cls) -> QFontIconStore:
        if cls.__instance is None:
            cls.__instance = cls()
        return cls.__instance

    @classmethod
    def clear(cls) -> None:
        cls._LOADED_KEYS.clear()
        cls._CHARMAPS.clear()
        QFontDatabase.removeAllApplicationFonts()

    @classmethod
    def _key2family(cls, key: str) -> Tuple[str, Optional[str]]:
        """Return (family, style) given a font `key`"""
        key = key.split(".", maxsplit=1)[0]
        if key not in cls._LOADED_KEYS:
            from . import _plugins

            try:
                font_cls = _plugins.get_font_class(key)
                result = cls.addFont(
                    font_cls.__font_file__, key, charmap=font_cls.__dict__
                )
                if not result:  # pragma: no cover
                    raise Exception("Invalid font file")
                cls._LOADED_KEYS[key] = result
            except Exception as e:
                raise ValueError(
                    f"Unrecognized font key: {key!r}.\n"
                    f"Known plugin keys include: {_plugins.available()}.\n"
                    f"Loaded keys include: {list(cls._LOADED_KEYS)}."
                ) from e
        return cls._LOADED_KEYS[key]

    @classmethod
    def _ensure_char(cls, char: str, family: str, style: str) -> str:
        """make sure that `char` is a glyph provided by `family` and `style`."""
        if len(char) == 1 and ord(char) > 256:
            return char
        try:
            charmap = cls._CHARMAPS[(family, style)]
        except KeyError:
            raise KeyError(f"No charmap registered for font '{family} ({style})'")
        if char in charmap:
            # split in case the charmap includes the key
            return charmap[char].split(".", maxsplit=1)[-1]

        ident = _ensure_identifier(char)
        if ident in charmap:
            return charmap[ident].split(".", maxsplit=1)[-1]

        ident = f"{char!r} or {ident!r}" if char != ident else repr(ident)
        raise ValueError(f"Font '{family} ({style})' has no glyph with the key {ident}")

    @classmethod
    def key2glyph(cls, glyph_key: str) -> tuple[str, str, Optional[str]]:
        """Return (char, family, style) given a `glyph_key`"""
        font_key, char = glyph_key.split(".", maxsplit=1)
        family, style = cls._key2family(font_key)
        char = cls._ensure_char(char, family, style)
        return char, family, style

    @classmethod
    def addFont(
        cls, filepath: str, prefix: str, charmap: Optional[Dict[str, str]] = None
    ) -> Optional[Tuple[str, str]]:
        """Add font at `filepath` to the registry under `key`.

        If you'd like to later use a fontkey in the form of `key.some-name`, then
        `charmap` must be provided and provide a mapping for all of the glyph names
        to their unicode numbers. If a charmap is not provided, glyphs must be directly
        accessed with their unicode as something like `key.\uffff`.

        Parameters
        ----------
        filepath : str
            Path to an OTF or TTF file containing the fonts
        key : str
            A key that will represent this font file when used for lookup.  For example,
            'fa5s' for 'Font-Awesome 5 Solid'.
        charmap : Dict[str, str], optional
            optional mapping for all of the glyph names to their unicode numbers.
            See note above.

        Returns
        -------
        Tuple[str, str], optional
            font-family and font-style for the file just registered, or None if
            something goes wrong.
        """
        assert prefix not in cls._LOADED_KEYS, f"Prefix {prefix} already loaded"
        assert Path(filepath).exists(), f"Font file doesn't exist: {filepath}"
        assert QApplication.instance() is not None, "Please create QApplication first."
        # TODO: remember filepath?

        fontId = QFontDatabase.addApplicationFont(str(Path(filepath).absolute()))
        if fontId < 0:  # pragma: no cover
            warnings.warn(f"Cannot load font file: {filepath}")
            return None

        families = QFontDatabase.applicationFontFamilies(fontId)
        if not families:  # pragma: no cover
            warnings.warn(f"Font file is empty!: {filepath}")
            return None
        family: str = families[0]

        # in Qt6, everything becomes a static member
        QFd: Union[QFontDatabase, Type[QFontDatabase]] = (
            QFontDatabase()
            if tuple(QT_VERSION.split(".")) < ("6", "0")
            else QFontDatabase
        )

        styles = QFd.styles(family)  # type: ignore
        style: str = styles[-1] if styles else ""
        if not QFd.isSmoothlyScalable(family, style):  # pragma: no cover
            warnings.warn(
                f"Registered font {family} ({style}) is not smoothly scalable. "
                "Icons may not look attractive."
            )

        cls._LOADED_KEYS[prefix] = (family, style)
        if charmap:
            cls._CHARMAPS[(family, style)] = charmap
        return (family, style)

    def icon(
        self,
        glyph_key: str,
        *,
        scale_factor: float = DEFAULT_SCALING_FACTOR,
        color: ValidColor = None,
        opacity: float = 1,
        animation: Optional[Animation] = None,
        transform: Optional[QTransform] = None,
        states: Dict[str, dict] = {},
    ) -> QFontIcon:
        self.key2glyph(glyph_key)  # make sure it's a valid glyph_key

        default_opts = IconOptions._from_kwargs(locals())

        icon = QFontIcon(default_opts)
        for kw, options in states.items():
            try:
                state, mode = _states[frozenset(kw.lower().split("_"))]
            except KeyError:
                raise ValueError(
                    f"{kw!r} is not a valid state key, must be a combination of {{on, "
                    "off, active, disabled, selected, normal} separated by underscore"
                )
            icon.addState(state, mode, **options)
        return icon

    def setTextIcon(self, widget: QWidget, glyph_key: str, size: float = None) -> None:
        """Sets text on a widget to a specific font & glyph.

        This is an alternative to setting a QIcon with a pixmap.  It may
        be easier to combine with dynamic stylesheets.
        """
        setText = getattr(widget, "setText", None)
        if not setText:  # pragma: no cover
            raise TypeError(f"Object does not a setText method: {widget}")

        glyph = self.key2glyph(glyph_key)[0]
        size = size or DEFAULT_SCALING_FACTOR
        size = size if size > 1 else widget.height() * size
        widget.setFont(self.font(glyph_key, int(size)))
        setText(glyph)

    def font(self, font_prefix: str, size: int = None) -> QFont:
        """Create QFont for `font_prefix`"""
        font_key, _ = font_prefix.split(".", maxsplit=1)
        family, style = self._key2family(font_key)
        font = QFont()
        font.setFamily(family)
        if style:
            font.setStyleName(style)
        if size:
            font.setPixelSize(int(size))
        return font


def _ensure_identifier(name: str) -> str:
    """Normalize string to valid identifier"""
    import keyword

    if not name:
        return ""

    # add _ to beginning of names starting with numbers
    if name[0].isdigit():
        name = f"_{name}"

    # add _ to end of reserved keywords
    if keyword.iskeyword(name):
        name += "_"

    # replace dashes and spaces with underscores
    name = name.replace("-", "_").replace(" ", "_")

    assert str.isidentifier(name), f"Could not canonicalize name: {name}"
    return name

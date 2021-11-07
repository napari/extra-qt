from qtpy.QtWidgets import QSlider

from ._generic_range_slider import _GenericRangeSlider
from ._generic_slider import _GenericSlider

class QDoubleRangeSlider(_GenericRangeSlider): ...
class QDoubleSlider(_GenericSlider): ...
class QRangeSlider(_GenericRangeSlider): ...
class QLabeledSlider(QSlider): ...
class QLabeledDoubleSlider(QDoubleSlider): ...
class QLabeledRangeSlider(QRangeSlider): ...
class QLabeledDoubleRangeSlider(QDoubleRangeSlider): ...

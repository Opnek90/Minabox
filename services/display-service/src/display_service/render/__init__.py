"""Screen renderers: pure PIL, no device, no I/O.

Every renderer here returns a mode-'1' image of panel size and touches no
hardware, which is what makes them testable without an SSD1306 attached.
"""

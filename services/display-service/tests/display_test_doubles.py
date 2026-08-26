"""Test doubles and builders for the display service tests."""

from __future__ import annotations

from display_service.config_schema import DisplayElement


def element(type_: str, area: int = 0, order: int = 0, enabled: bool = True, id_=None):
    return DisplayElement(
        id=id_ or type_,
        type=type_,
        area=area,
        order=order,
        enabled=enabled,
    )


class FakePanel:
    """Records what the service does to the device, and whether one exists."""

    def __init__(self, *, available: bool = False, init_succeeds: bool = True) -> None:
        self.available = available
        self.init_succeeds = init_succeeds
        self.calls: list[tuple] = []
        # Every screen reaches the panel through show_image now; the frames
        # are kept so a test can say which one was drawn.
        self.frames: list = []

    # -- the module-level functions main.py imported --------------------

    def is_available(self) -> bool:
        return self.available

    def init(self, bus, address, *, log_failure=True) -> bool:
        self.calls.append(("init", bus, address))
        if self.init_succeeds:
            self.available = True
        return self.init_succeeds

    def shutdown(self) -> None:
        self.calls.append(("shutdown",))
        self.available = False

    def clear(self) -> None:
        self.calls.append(("clear",))

    def show_areas(self, areas, font_size="medium", font="default") -> None:
        self.calls.append(("show_areas", font_size, font))

    def show_image(self, img) -> None:
        self.calls.append(("show_image", img))
        self.frames.append(img)

    def show_lines(self, lines) -> None:
        self.calls.append(("show_lines", tuple(lines)))

    # -- assertions -----------------------------------------------------

    @property
    def names(self) -> list[str]:
        return [c[0] for c in self.calls]

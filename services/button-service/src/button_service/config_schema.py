from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field, PositiveInt, model_validator

from shared_lib.config import EnvConfigBase

ButtonMode = Literal["basic", "advanced"]
ButtonType = Literal["push", "rotary"]


class ButtonConfig(BaseModel):
    """Configuration for a single physical button or rotary encoder."""

    id: str = Field(
        min_length=1,
        description="Internal button/encoder identifier (e.g. 'btn_1', 'enc_1').",
    )
    name: str = Field(
        min_length=1,
        description="Human-readable name for UI and logs (e.g. 'Play/Pause').",
    )
    mode: ButtonMode = Field(
        description=(
            "Mapping mode: 'basic' uses a single 'action' field, "
            "'advanced' uses an 'actions' map per event_type."
        ),
    )
    type: ButtonType = Field(
        description="Hardware type: 'push' for push button, 'rotary' for encoder.",
    )

    # Push button specific
    gpio: PositiveInt | None = Field(
        default=None,
        description="GPIO pin number for push buttons.",
    )

    # Rotary encoder specific
    clk: PositiveInt | None = Field(
        default=None,
        description="CLK pin of the rotary encoder.",
    )
    dt: PositiveInt | None = Field(
        default=None,
        description="DT pin of the rotary encoder.",
    )
    sw: PositiveInt | None = Field(
        default=None,
        description="SW (switch) pin of the rotary encoder.",
    )

    # Mapping definitions
    action: str | None = Field(
        default=None,
        description=(
            "Logical action name in basic mode (e.g. 'play_pause'). "
            "All event types map to this single action."
        ),
    )
    actions: Dict[str, str] | None = Field(
        default=None,
        description=(
            "Mapping from event_type (e.g. 'short_press', 'rotate_cw') to "
            "logical action name in advanced mode."
        ),
    )
    enabled: bool = Field(
        default=True,
        description=(
            "When False, the button fires no MQTT action. "
            "The raw-event is still published so hardware test-mode keeps working. "
            "Defaults to True so existing configs are unaffected."
        ),
    )

    @model_validator(mode="after")
    def _validate_mode_and_type(self) -> "ButtonConfig":
        """Ensure required fields are present based on mode and type."""
        errors: list[str] = []

        if self.type == "push":
            if self.gpio is None:
                errors.append("gpio must be set for push buttons")
            if self.clk is not None or self.dt is not None or self.sw is not None:
                errors.append("clk/dt/sw are not valid for push buttons")
        elif self.type == "rotary":
            if self.clk is None or self.dt is None or self.sw is None:
                errors.append("clk, dt and sw must be set for rotary encoders")
            if self.gpio is not None:
                errors.append("gpio is not valid for rotary encoders")

        if self.mode == "basic":
            if not self.action:
                errors.append("action must be set in basic mode")
            if self.actions is not None:
                errors.append("actions must be null/omitted in basic mode")
        elif self.mode == "advanced":
            if not self.actions:
                errors.append("actions must be set in advanced mode")
            if self.action is not None:
                errors.append("action must be null/omitted in advanced mode")

        if errors:
            raise ValueError("; ".join(errors))

        return self


class ButtonServiceConfig(BaseModel):
    """Top-level button configuration loaded from config/buttons.json."""

    buttons: List[ButtonConfig] = Field(
        default_factory=list,
        description="Configured buttons and encoders for this device.",
    )


class EnvConfig(EnvConfigBase):
    """Environment-based configuration for the button service (extends shared base)."""

    api_port: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="REST API port for the button service (issue #17).",
    )
    disable_gpio: bool = Field(
        default=False,
        description=(
            "Skip all hardware access. For development on a machine without "
            "GPIO; the API and MQTT stay available."
        ),
    )


class AppConfig(BaseModel):
    """Combined configuration for the button service.

    Holds the environment only. The button list is owned by the ConfigManager,
    which reloads it at runtime -- keeping a second copy here meant startup
    parsed the same file twice and then held a snapshot that went stale with
    the first reload.
    """

    env: EnvConfig

    @property
    def mqtt_topic_prefix(self) -> str:
        """Get MQTT topic prefix for this device."""
        return f"minabox/{self.env.minabox_device_id}"

    def get_mqtt_topic(self, domain: str, action: str) -> str:
        """Build a namespaced MQTT topic (issue #16).

        Args:
            domain: Service domain (e.g. 'button', 'audio', 'config').
            action: Action / sub-topic (e.g. 'play-pause', 'config/get').

        Returns:
            Full topic string: minabox/<device-id>/<domain>/<action>
        """
        return f"{self.mqtt_topic_prefix}/{domain}/{action}"

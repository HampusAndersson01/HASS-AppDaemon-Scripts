import logging
from typing import Optional, Any
import appdaemon.plugins.hass.hassapi as hass


class DashboardToNestHubApp(hass.Hass):
    """Manages dashboard display on Nest Hub based on presence detection and PC status."""

    MEDIA_PLAYER_ENTITY = "media_player.nesthub0445"
    PRESENCE_SENSOR = "binary_sensor.presence_detector"
    CPU_LOAD_SENSOR = "sensor.pc_cpuload"
    DASHBOARD_TYPE_DEFAULT = "lovelace"
    DASHBOARD_TYPE_PC = "dashboard"
    TRANSITION_DELAY = 1
    SOUND_DELAY = 10  # 10 second delay before unmuting

    def initialize(self) -> None:
        """Initialize the app and set up state listeners."""
        self.listen_state(self.handle_presence_change, self.PRESENCE_SENSOR)
        self.listen_state(self.handle_cpu_load_change, self.CPU_LOAD_SENSOR)
        self.cpu_load: Optional[str] = None
        self.current_dashboard: Optional[str] = None

    def handle_cpu_load_change(self, entity: str, attribute: str,
                               old: str, new: str, kwargs: dict) -> None:
        """Handle changes in CPU load and trigger dashboard update if needed."""
        self.cpu_load = new
        if self.get_state(self.PRESENCE_SENSOR) == "on":
            # Switch dashboard based on CPU load state
            desired_dashboard = (self.DASHBOARD_TYPE_PC
                                 if self.is_float(new)
                                 else self.DASHBOARD_TYPE_DEFAULT)

            if (not self.is_casting() and
                    self.current_dashboard != desired_dashboard):
                self.log(
                    f"CPU load changed to {new}, switching to {desired_dashboard}")
                self.run_in(self.activate_dashboard, self.TRANSITION_DELAY)

    def handle_presence_change(self, entity: str, attribute: str,
                               old: str, new: str, kwargs: dict) -> None:
        """Handle presence sensor state changes."""
        if new == "on":
            self.run_in(self.activate_dashboard, self.TRANSITION_DELAY)
        elif new == "off":
            self.run_in(self.deactivate_dashboard, self.TRANSITION_DELAY)

    def is_casting(self) -> bool:
        """Check if the media player is currently casting something."""
        state = self.get_state(self.MEDIA_PLAYER_ENTITY)
        return state not in ["off", "idle", None]

    def unmute_player(self, kwargs: dict) -> None:
        """Unmute the media player."""
        try:
            self.call_service("media_player/volume_mute",
                              entity_id=self.MEDIA_PLAYER_ENTITY,
                              is_volume_muted=False)
        except Exception as e:
            self.log(f"Error unmuting player: {str(e)}", level="ERROR")

    def activate_dashboard(self, kwargs: dict) -> None:
        """Activate appropriate dashboard based on CPU load state."""
        try:
            # Skip if already casting something
            if self.is_casting():
                self.log(
                    "Media player is currently casting, skipping dashboard activation")
                return

            self.call_service("media_player/volume_mute",
                              entity_id=self.MEDIA_PLAYER_ENTITY,
                              is_volume_muted=True)

            if self.cpu_load and self.is_float(self.cpu_load):
                if self.current_dashboard != self.DASHBOARD_TYPE_PC:
                    self.call_service("media_player/turn_off",
                                      entity_id=self.MEDIA_PLAYER_ENTITY)
                    self.call_service("shell_command/cast_dashboard")
                    self.current_dashboard = self.DASHBOARD_TYPE_PC
            else:
                if self.current_dashboard != self.DASHBOARD_TYPE_DEFAULT:
                    self.call_service("shell_command/stop_catt")
                    self.call_service(
                        "script/cast_lovelace_dashboard_to_nest_hub")
                    self.current_dashboard = self.DASHBOARD_TYPE_DEFAULT

            # Schedule unmute after delay
            self.run_in(self.unmute_player, self.SOUND_DELAY)

        except Exception as e:
            self.log(f"Error activating dashboard: {str(e)}", level="ERROR")

    def deactivate_dashboard(self, kwargs: dict) -> None:
        """Turn off the display and stop casting."""
        try:
            self.call_service("media_player/volume_mute",
                              entity_id=self.MEDIA_PLAYER_ENTITY,
                              is_volume_muted=True)

            self.call_service("media_player/turn_off",
                              entity_id=self.MEDIA_PLAYER_ENTITY)
            self.call_service("shell_command/stop_catt")
            self.current_dashboard = None

            # Schedule unmute after delay
            self.run_in(self.unmute_player, self.SOUND_DELAY)

        except Exception as e:
            self.log(f"Error deactivating dashboard: {str(e)}", level="ERROR")

    @staticmethod
    def is_float(value: Any) -> bool:
        """Check if a value can be converted to float."""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False

import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime

# Light settings constants
DEFAULT_SETTINGS = {
    "early_morning": {"brightness": 75, "color_temp": 250},
    "morning": {"brightness": 125, "color_temp": 200},
    "afternoon": {"brightness": 255, "color_temp": 153},
    "night": {"brightness": 10, "color_temp": 333},
    "focus": {"brightness": 255, "color_temp": 250}
}

COLORS = {
    "christmas_red": [255, 0, 0],
    "christmas_green": [0, 255, 0],
    "night_blue": [0, 0, 255]
}


class Lightning(hass.Hass):
    """App to control lighting based on presence and modes."""

    def initialize(self):
        """Initialize the app."""
        self.log("Lightning app initializing")

        # Initialize states
        self.mode = "default"
        self.running = False
        self.presence_enabled = self.get_state(
            self.args["presence_mode_switch"]) == "on"
        self.pattern_handle = None  # Add this line
        self.main_light_timer = None  # Add this line
        self.pattern_handles = []  # Add this line to track all pattern timers

        # Add a list of managed lights (lights that should be turned off)
        self.managed_lights = [
            self.args["main_light"],
            self.args["focus_light"]
        ]

        # Subscribe to state changes
        self._setup_listeners()

        # Check initial state
        self.check_and_set_mode()

        self.log("Lightning app initialized")

    def _setup_listeners(self):
        """Set up all state listeners."""
        # Core state changes
        self.listen_state(self.presence_change, self.args["presence_sensor"])
        self.listen_state(self.presence_mode_change,
                          self.args["presence_mode_switch"])

        # Mode changes
        for switch in ["night_mode_switch", "christmas_mode_switch", "focus_mode_switch"]:
            self.listen_state(self.mode_change, self.args[switch])

        # Combined phone and charger state changes for night mode
        self.listen_state(self.check_night_conditions,
                          self.args["phone_state_sensor"])
        self.listen_state(self.check_night_conditions,
                          self.args["charger_type_sensor"])

        # Replace multiple attribute listeners with single state listener
        self.listen_state(
            self.handle_main_light_change,
            self.args["main_light"],
            attribute="all"
        )

    def handle_main_light_change(self, entity, attribute, old, new, kwargs):
        """Handle changes to main light when in focus mode with debouncing."""
        if self.mode == "focus" and self.get_state(self.args["focus_mode_switch"]) == "on":
            # Cancel any pending timer
            if self.main_light_timer is not None:
                self.cancel_timer(self.main_light_timer)

            # Set new timer
            self.main_light_timer = self.run_in(self.reactivate_focus_light, 1)

    def reactivate_focus_light(self, kwargs):
        """Reactivate focus light with proper settings."""
        self.main_light_timer = None  # Clear the timer reference
        self.turn_on(
            self.args["focus_light"],
            brightness=DEFAULT_SETTINGS["focus"]["brightness"],
            color_temp=DEFAULT_SETTINGS["focus"]["color_temp"]
        )

    def presence_change(self, entity, attribute, old, new, kwargs):
        """Handle presence changes."""
        if not self.presence_enabled:
            return  # Don't react to presence changes if presence mode is disabled

        if new == "on":
            self.check_and_set_mode()
        elif self.presence_enabled:  # Only turn off lights if presence mode is enabled
            self.turn_off_all()

    def presence_mode_change(self, entity, attribute, old, new, kwargs):
        """Handle presence mode toggle."""
        self.presence_enabled = (new == "on")
        if new == "on":
            self.presence_change(self.args["presence_sensor"], None,
                                 None, self.get_state(self.args["presence_sensor"]), None)
        else:
            # When presence mode is disabled, check modes without presence requirement
            self.check_and_set_mode(ignore_presence=True)

    def mode_change(self, entity, attribute, old, new, kwargs):
        """Handle mode changes."""
        if new == "off":
            # When any mode is disabled
            if entity == self.args["focus_mode_switch"]:
                self.copy_reference_light_state()
                return

            if entity == self.args["christmas_mode_switch"]:
                self._cleanup_christmas_mode()

            # Only consider presence if presence mode is enabled
            if not self.presence_enabled or self.get_state(self.args["presence_sensor"]) == "on":
                self.activate_default_mode()
        else:
            self.check_and_set_mode()

    def copy_reference_light_state(self):
        """Copy state from reference light to main light."""
        try:
            reference_state = self.get_state(
                self.args["reference_light"], attribute="all")

            if not reference_state or reference_state.get('state') != 'on':
                self.turn_off(self.args["focus_light"])
                return

            attributes = reference_state.get('attributes', {})
            settings = {}

            # Copy basic attributes
            if 'brightness' in attributes:
                settings['brightness'] = attributes['brightness']

            # Handle different color modes
            color_mode = attributes.get('color_mode')
            if color_mode == 'color_temp' and 'color_temp' in attributes:
                settings['color_temp'] = attributes['color_temp']
            elif color_mode in ['rgb', 'xy'] and 'rgb_color' in attributes:
                settings['rgb_color'] = attributes['rgb_color']

            # Apply settings to main light
            self.call_service(
                "light/turn_on",
                entity_id=self.args["focus_light"],
                transition=1,
                **settings
            )

            self.log(f"Copied reference light state: {settings}")

        except Exception as e:
            self.log(
                f"Failed to copy reference light state: {str(e)}", level="ERROR")

    def check_and_set_mode(self, ignore_presence=False):
        """Check current states and set appropriate mode."""
        # Skip presence check if presence mode is disabled
        if self.presence_enabled and not ignore_presence:
            if self.get_state(self.args["presence_sensor"]) != "on":
                self.turn_off_all()
                return

        # Activate appropriate mode
        if self.get_state(self.args["night_mode_switch"]) == "on":
            self.activate_night_mode()
        elif self.get_state(self.args["christmas_mode_switch"]) == "on":
            self.activate_christmas_mode()
        elif self.get_state(self.args["focus_mode_switch"]) == "on":
            self.activate_focus_mode()
        else:
            self.activate_default_mode()

    def activate_christmas_mode(self):
        """Activate Christmas mode pattern."""
        self.mode = "christmas"
        self.running = True

        # Cancel any existing pattern
        if self.pattern_handle:
            self.cancel_timer(self.pattern_handle)

        # Start with red/green pattern
        self._run_christmas_pattern("red")

    def _cleanup_christmas_mode(self):
        """Clean up all Christmas mode patterns and timers."""
        self.running = False

        # Cancel all scheduled pattern changes
        if self.pattern_handle:
            self.cancel_timer(self.pattern_handle)
            self.pattern_handle = None

        # Cancel any other pending pattern timers
        for handle in self.pattern_handles:
            try:
                self.cancel_timer(handle)
            except:
                pass
        self.pattern_handles.clear()

    def _run_christmas_pattern(self, current_color):
        """Run the Christmas pattern with alternating colors."""
        if not self.running:
            return

        lights1 = self.args["christmas_lights_even"]
        lights2 = self.args["christmas_lights_odd"]
        delay = self.args.get("christmas_delay", 5)

        # Set current pattern
        if current_color == "red":
            self.call_service(
                "light/turn_on",
                entity_id=lights1,
                rgb_color=COLORS["christmas_red"],
                brightness=150,
                transition=1
            )
            self.call_service(
                "light/turn_on",
                entity_id=lights2,
                rgb_color=COLORS["christmas_green"],
                brightness=150,
                transition=1
            )
            next_color = "green"
        else:
            self.call_service(
                "light/turn_on",
                entity_id=lights1,
                rgb_color=COLORS["christmas_green"],
                brightness=150,
                transition=1
            )
            self.call_service(
                "light/turn_on",
                entity_id=lights2,
                rgb_color=COLORS["christmas_red"],
                brightness=150,
                transition=1
            )
            next_color = "red"

        # Schedule next pattern change if still running
        if self.running:
            handle = self.run_in(
                lambda kwargs: self._run_christmas_pattern(next_color),
                delay
            )
            self.pattern_handles.append(handle)
            self.pattern_handle = handle  # Keep track of most recent handle

    def activate_focus_mode(self):
        """Activate focus mode lighting."""
        self.mode = "focus"
        self.turn_on(self.args["focus_light"], **DEFAULT_SETTINGS["focus"])

    def activate_night_mode(self):
        """Activate night mode per README criteria."""
        self.mode = "night"

        # Get list of lights to turn off (all lights except presence_night_lights)
        night_lights = set(self.args["presence_night_lights"])
        lights_to_turn_off = [light for light in self.args["all_lights"]
                              if light not in night_lights]

        # Skip presence check if presence mode is disabled
        if not self.presence_enabled or self.get_state(self.args["presence_sensor"]) == "on":
            self.call_service(
                "light/turn_off",
                entity_id=lights_to_turn_off
            )
            self.run_in(self.turn_on_night_lights, 0)
        else:
            self.check_night_conditions(None, None, None, None, None)

    def turn_on_night_lights(self, kwargs):
        """Callback to turn on night lights after main lights turn off."""
        try:
            # Turn on all presence night lights in a single call
            self.call_service(
                "light/turn_on",
                entity_id=self.args["presence_night_lights"],
                brightness=DEFAULT_SETTINGS["night"]["brightness"],
                color_temp=DEFAULT_SETTINGS["night"]["color_temp"],
                transition=1
            )

            # Then check phone conditions for bedroom light
            self.check_night_conditions(None, None, None, None, None)
        except Exception as e:
            self.log(f"Error in turn_on_night_lights: {e}", level="ERROR")

    def check_night_conditions(self, entity, attribute, old, new, kwargs):
        """Check all conditions for night mode bedroom light."""
        if self.mode != "night":
            return False

        phone_state = self.get_state(self.args["phone_state_sensor"])
        charger_type = self.get_state(self.args["charger_type_sensor"])

        should_light_on = (
            phone_state in ["okänd", "offhook"] or
            charger_type == "usb"
        )

        if should_light_on:
            # Single service call for bedroom light
            self.call_service(
                "light/turn_on",
                entity_id=self.args["bedroom_night_light"],
                brightness=102,
                color_temp=454,
                transition=1
            )
        return should_light_on

    def activate_default_mode(self):
        """Activate default mode with time-based settings."""
        self.mode = "default"
        current_time = self.get_now()
        settings = self.get_time_based_settings(current_time)
        self.turn_on(self.args["main_light"], **settings)

    def get_time_based_settings(self, current_time):
        """Get light settings based on time of day."""
        hour = current_time.hour
        if 5 <= hour < 8:
            return DEFAULT_SETTINGS["early_morning"]
        elif 8 <= hour < 12:
            return DEFAULT_SETTINGS["morning"]
        elif 12 <= hour < 20:
            return DEFAULT_SETTINGS["afternoon"]
        else:
            return DEFAULT_SETTINGS["night"]

    def turn_off_all(self):
        """Turn off all managed lights."""
        self._cleanup_christmas_mode()

        # Only turn off lights that are explicitly managed
        self.call_service(
            "light/turn_off",
            entity_id=self.managed_lights
        )

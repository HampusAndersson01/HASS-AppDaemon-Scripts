import appdaemon.plugins.hass.hassapi as hass
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import asyncio
from enum import Enum


class LightMode(Enum):
    DEFAULT = "default"
    FOCUS = "focus"
    CHRISTMAS = "christmas"
    NIGHT = "night"


class LightState:
    def __init__(self):
        self.mode: LightMode = LightMode.DEFAULT
        self.is_running: bool = False
        self.last_update: Optional[datetime] = None


class PresenceLighting(hass.Hass):
    def initialize(self) -> None:
        """Initialize the app with proper error handling and state management"""
        try:
            self._setup_constants()
            self._setup_state()
            self._register_callbacks()
            self._activate_initial_mode()  # Add this line
            self.log("PresenceLighting initialized successfully")
        except Exception as e:
            self.error("Failed to initialize PresenceLighting", e)
            self._safe_cleanup()

    def _setup_constants(self) -> None:
        """Setup constant values"""
        self.ENTITIES = {
            'main': "light.ljus",
            'focus': "light.taklampa_lampa_3",
            'night': "light.vagglampa",
            'night_array': ["light.zigbee_night_lights"],
            'christmas_even': ["light.christmas2"],  # Even numbered lights
            'christmas_odd': ["light.christmas1"],   # Odd numbered lights
            'reference': "light.taklampa_lampa_1"  # Add reference light
        }

        self.LIGHT_SETTINGS = {
            'early_morning': {"brightness": 75, "color_temp": 250},
            'morning': {"brightness": 125, "color_temp": 200},
            'afternoon': {"brightness": 255, "color_temp": 153},
            'night': {"brightness": 50, "color_temp": 333}
        }

    def _setup_state(self) -> None:
        """Setup internal state with async lock"""
        self._lock = asyncio.Lock()
        self._state = LightState()
        self._callbacks: List[Any] = []
        self._presence_time: Optional[str] = None

    def _register_callbacks(self) -> None:
        """Register all event listeners"""
        events = {
            "binary_sensor.narvarodetektor_narvaro": self._handle_presence_sync,
            "input_boolean.christmas_mode": self._handle_christmas_mode_sync,
            "input_boolean.desk_focus_lights": self._handle_focus_mode_sync,
            "input_boolean.night_mode": self._handle_night_mode_sync,
            "sensor.hampus_zfold_phone_state": self._handle_phone_state_sync,
            "sensor.hampus_zfold_charger_type": self._handle_charger_type_sync,
            "input_boolean.presence_mode": self._handle_presence_mode_sync,
            # Monitor specific attributes
            "light.ljus": [self._handle_main_light_change_sync, ["state", "rgb_color", "color_temp", "brightness"]]
        }

        for entity, callback_info in events.items():
            if isinstance(callback_info, list):
                callback, attributes = callback_info
                for attribute in attributes:
                    self.listen_state(callback, entity, attribute=attribute)
            else:
                self.listen_state(callback_info, entity)

    async def _safe_operation(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operations with proper error handling and thread safety"""
        try:
            async with self._lock:
                result = await operation(*args, **kwargs)
                return result
        except Exception as e:
            self.error(f"Operation failed: {operation.__name__}", e)
            await self._safe_cleanup()
            return None

    def _handle_presence_mode_sync(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Synchronous handler for presence mode"""
        current_presence = self.get_state(
            "binary_sensor.narvarodetektor_narvaro")
        if new == "on" and current_presence == "on":
            self._presence_time = self.get_now().strftime("%H:%M")
            self._activate_mode_sync(self._state.mode)
        elif new == "off":
            self._deactivate_current_mode_sync()

    def _handle_presence_sync(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Synchronous handler for presence detection"""
        if self.get_state("input_boolean.presence_mode") != "on":
            return

        if new == "on":
            self._presence_time = self.get_now().strftime("%H:%M")
            self._activate_mode_sync(self._state.mode)
        else:
            self._deactivate_current_mode_sync()

    def _activate_mode_sync(self, mode: LightMode) -> None:
        """Synchronous mode activation"""
        if mode == self._state.mode:
            return

        # Cancel any running patterns/callbacks
        for callback in self._callbacks:
            try:
                self.cancel_timer(callback)
            except:
                pass
        self._callbacks = []

        mode_handlers = {
            LightMode.FOCUS: self._activate_focus_sync,
            LightMode.CHRISTMAS: self._activate_christmas_sync,
            LightMode.NIGHT: self._activate_night_sync,
            LightMode.DEFAULT: self._activate_default_sync
        }

        handler = mode_handlers.get(mode, self._activate_default_sync)
        handler()

    def _safe_cleanup_sync(self) -> None:
        """Synchronous cleanup"""
        self._state.is_running = False
        for callback in self._callbacks[:]:  # Create a copy of the list
            try:
                self.cancel_timer(callback)
            except:
                self.log(
                    f"Failed to cancel callback {callback}", level="WARNING")
        self._callbacks = []

    def _get_light_settings(self) -> dict:
        """Get light settings based on time of day"""
        now = self.get_now()  # Use AppDaemon's get_now() instead of datetime
        current_total_minutes = now.hour * 60 + now.minute

        if 300 <= current_total_minutes < 480:  # 5:00-8:00
            return self.LIGHT_SETTINGS['early_morning']
        elif 480 <= current_total_minutes < 720:  # 8:00-12:00
            return self.LIGHT_SETTINGS['morning']
        elif 720 <= current_total_minutes < 1200:  # 12:00-20:00
            return self.LIGHT_SETTINGS['afternoon']
        else:
            return self.LIGHT_SETTINGS['night']

    def _handle_christmas_mode_sync(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Synchronous christmas mode handler"""
        if self.get_state("binary_sensor.narvarodetektor_narvaro") != "on":
            return

        if new == "on":
            self._state.mode = LightMode.CHRISTMAS
            self._state.is_running = True
            self._activate_christmas_sync()
        else:
            self._state.is_running = False
            self._state.mode = LightMode.DEFAULT
            self._activate_default_sync()

    def _handle_focus_mode_sync(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Synchronous focus mode handler"""
        if self.get_state("binary_sensor.narvarodetektor_narvaro") != "on":
            return

        if new == "on":
            self._state.mode = LightMode.FOCUS
            self._activate_focus_sync()
        else:
            self._state.mode = LightMode.DEFAULT
            self._copy_reference_light_state()

    def _copy_reference_light_state(self) -> None:
        """Copy state from reference light with color mode awareness"""
        try:
            reference = self.ENTITIES['reference']
            state = self.get_state(reference, attribute="all")

            if state['state'] == 'on':
                attributes = state['attributes']
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

                self.turn_on(self.ENTITIES['main'], **settings)
            else:
                self.turn_off(self.ENTITIES['main'])

        except Exception as e:
            self.error(
                "Failed to copy reference light state", e)

    def _handle_night_mode_sync(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Synchronous night mode handler"""
        if self.get_state("binary_sensor.narvarodetektor_narvaro") != "on":
            return

        if new == "on":
            self._state.mode = LightMode.NIGHT
            self._activate_night_sync()
        else:
            self._state.mode = LightMode.DEFAULT
            self._activate_default_sync()

    async def _handle_presence_mode(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Handle presence mode toggle"""
        try:
            current_presence = self.get_state(
                "binary_sensor.narvarodetektor_narvaro")
            if new == "on" and current_presence == "on":
                self._presence_time = datetime.now().strftime("%H:%M")
                await self._safe_operation(self._activate_mode, self._state.mode)
            elif new == "off":
                await self._safe_operation(self._deactivate_current_mode)
        except Exception as e:
            self.error("Presence mode handling failed", e)

    async def _handle_presence(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Handle presence detection with proper state management"""
        try:
            if self.get_state("input_boolean.presence_mode") != "on":
                return

            if new == "on":
                self._presence_time = datetime.now().strftime("%H:%M")
                self.log(
                    f"Presence detected, start time: {self._presence_time}")
                await self._safe_operation(self._activate_mode, self._state.mode)
            else:
                await self._safe_operation(self._deactivate_current_mode)
        except Exception as e:
            self.error("Presence handling failed", e)

    async def _activate_mode(self, mode: LightMode) -> None:
        """Activate lighting mode with proper cleanup"""
        await self._safe_cleanup()

        mode_handlers = {
            LightMode.FOCUS: self._activate_focus,
            LightMode.CHRISTMAS: self._activate_christmas,
            LightMode.NIGHT: self._activate_night,
            LightMode.DEFAULT: self._activate_default
        }

        handler = mode_handlers.get(mode, self._activate_default)
        await handler()

    async def _safe_cleanup(self) -> None:
        """Safely cleanup all states and callbacks"""
        try:
            async with self._lock:
                self._state.is_running = False
                for callback in self._callbacks:
                    try:
                        self.cancel_timer(callback)
                    except:
                        pass
                self._callbacks = []

        except Exception as e:
            self.error("Cleanup failed", e)

    def error(self, message: str, error: Exception) -> None:
        """Unified error handling"""
        self.log(f"{message}: {str(error)}",
                 level="ERROR")

    async def _christmas_pattern(self, lights1: List[str], lights2: List[str],
                                 brightness: int, delay: int) -> None:
        """Thread-safe christmas pattern implementation"""
        try:
            self.log("Starting Christmas pattern")
            if not self._state.is_running:
                self.log("Christmas pattern aborted - not running")
                return

            current_colors = {
                'red': [255, 0, 0],
                'green': [0, 255, 0]
            }

            while self._state.is_running:
                self.log("Christmas pattern iteration")
                # Lock only the state check
                async with self._lock:
                    if not self._state.is_running:
                        break

                # Pattern 1
                await self._set_lights_color(lights1, current_colors['red'], brightness)
                await self._set_lights_color(lights2, current_colors['green'], brightness)
                await asyncio.sleep(delay)

                async with self._lock:
                    if not self._state.is_running:
                        break

                # Pattern 2
                await self._set_lights_color(lights1, current_colors['green'], brightness)
                await self._set_lights_color(lights2, current_colors['red'], brightness)
                await asyncio.sleep(delay)

        except Exception as e:
            self.error("Christmas pattern failed", e)
            self._state.is_running = False

    async def _set_lights_color(self, lights: List[str], color: List[int],
                                brightness: int) -> None:
        """Safe light color setting"""
        for light in lights:
            self.turn_on(light, rgb_color=color, brightness=brightness,
                         transition=1)

    async def _handle_christmas_mode(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Handle christmas mode state changes"""
        try:
            if new == "on":
                if self.get_state("binary_sensor.narvarodetektor_narvaro") == "on":
                    self._state.mode = LightMode.CHRISTMAS
                    self._state.is_running = True
                    await self._activate_christmas()
            else:
                self._state.is_running = False
                await self._safe_cleanup()
                if self.get_state("binary_sensor.narvarodetektor_narvaro") == "on":
                    await self._activate_default()
        except Exception as e:
            self.error("Christmas mode handling failed", e)

    async def _handle_focus_mode(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Handle focus mode state changes"""
        try:
            if new == "on" and self.get_state("binary_sensor.narvarodetektor_narvaro") == "on":
                self._state.mode = LightMode.FOCUS
                await self._activate_focus()
            elif new == "off":
                await self._activate_default()
        except Exception as e:
            self.error("Focus mode handling failed", e)

    async def _handle_night_mode(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Handle night mode state changes"""
        try:
            if new == "on":
                self._state.mode = LightMode.NIGHT
                await self._safe_cleanup()
                await self._activate_night()
            elif new == "off":
                await self._activate_default()
        except Exception as e:
            self.error("Night mode handling failed", e)

    def _activate_focus_sync(self) -> None:
        """Synchronous focus mode activation"""
        self._callbacks.append(self.run_in(self.set_focus_light, 0))

    def set_focus_light(self, kwargs):
        """Sync version for callback compatibility"""
        self.turn_on(self.ENTITIES['focus'], color_temp=250, brightness=255)

    async def _activate_focus(self) -> None:
        """Activate focus mode with original timing"""
        try:
            light_settings = self._get_light_settings()
            self.turn_on(self.ENTITIES['main'], **
                         light_settings)  # Use sync version
            # Use original timing mechanism
            self._callbacks.append(self.run_in(self.set_focus_light, 1))
        except Exception as e:
            self.error("Focus mode activation failed", e)

    def _activate_christmas_sync(self) -> None:
        """Synchronous christmas mode activation"""
        try:
            self.log("Activating Christmas mode synchronously")
            self._state.is_running = True

            def christmas_callback(kwargs):
                try:
                    self._state.is_running = True
                    # Create coroutine and run it
                    coro = self._christmas_pattern(
                        self.ENTITIES['christmas_even'],
                        self.ENTITIES['christmas_odd'],
                        150,  # brightness
                        5     # delay
                    )
                    self.create_task(coro)
                except Exception as e:
                    self.error("Christmas callback failed", e)

            # Schedule the Christmas pattern
            callback = self.run_in(christmas_callback, 0)
            if callback:
                self._callbacks.append(callback)
                self.log("Christmas callback scheduled successfully")
            else:
                self.error("Failed to schedule Christmas callback",
                           "Callback returned None")

        except Exception as e:
            self.error("Failed to activate Christmas mode", e)
            self._state.is_running = False

    async def _activate_christmas(self) -> None:
        """Activate christmas mode"""
        try:
            await self._christmas_pattern(
                self.ENTITIES['christmas_even'],
                self.ENTITIES['christmas_odd'],
                150,  # brightness
                5    # delay
            )
        except Exception as e:
            self.error("Christmas mode activation failed", e)

    async def _deactivate_christmas(self) -> None:
        """Deactivate christmas mode"""
        try:
            self._state.is_running = False
            # Turn off even and odd christmas lights
            for light_list in [self.ENTITIES['christmas_even'], self.ENTITIES['christmas_odd']]:
                for light in light_list:
                    self.turn_off(light)
        except Exception as e:
            self.error("Christmas mode deactivation failed", e)

    def _activate_night_sync(self) -> None:
        """Synchronous night mode activation"""
        self.turn_off_all_lights(callback=self.turn_on_night_lights)

    def turn_on_night_lights(self, kwargs=None):
        """Sync version for callback compatibility"""
        try:
            # Turn on array lights first
            for light in self.ENTITIES['night_array']:
                self.turn_on(light, brightness=64, color_temp=350)

            # Then check if bedroom light should be on
            if self.should_turn_on_bedroom_night_light():
                self.turn_on(self.ENTITIES['night'], rgb_color=[
                             0, 0, 255], brightness=102)
        except Exception as e:
            self.error("Failed to turn on night lights", e)

    async def _activate_night(self) -> None:
        """Activate night mode"""
        try:
            for light in self.ENTITIES['night_array']:
                # Use sync version
                self.turn_on(light, brightness=64, color_temp=350)
            if self.should_turn_on_bedroom_night_light():  # Use sync version
                self.turn_on(self.ENTITIES['night'], rgb_color=[
                             0, 0, 255], brightness=102)  # Use sync version
        except Exception as e:
            self.error("Night mode activation failed", e)

    def _activate_default_sync(self) -> None:
        """Synchronous default mode activation"""
        light_settings = self._get_light_settings()
        self.turn_on(self.ENTITIES['main'], **light_settings)

    async def _activate_default(self) -> None:
        """Activate default mode"""
        try:
            light_settings = self._get_light_settings()
            self.turn_on(self.ENTITIES['main'], **
                         light_settings)  # Use sync version
            self.log(f"Activated default mode with settings: {light_settings}")
        except Exception as e:
            self.error("Default mode activation failed", e)

    async def _handle_phone_state(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Handle phone state changes"""
        if self._state.mode == LightMode.NIGHT and new == "okänd":
            self.turn_on(self.ENTITIES['night'], rgb_color=[
                         0, 0, 255], brightness=102)

    async def _handle_charger_type(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Handle charger type changes"""
        if self._state.mode == LightMode.NIGHT and new == "usb":
            self.turn_on(self.ENTITIES['night'], rgb_color=[
                         0, 0, 255], brightness=102)

    async def _should_turn_on_bedroom_night_light(self) -> bool:
        """Check if bedroom night light should be turned on"""
        try:
            phone_state = self.get_state("sensor.hampus_zfold_phone_state")
            charger_type = self.get_state("sensor.hampus_zfold_charger_type")
            return phone_state == "okänd" and charger_type == "usb"
        except Exception as e:
            self.error("Night light check failed", e)
            return False

    def should_turn_on_bedroom_night_light(self) -> bool:
        """Restore original OR condition"""
        try:
            phone_state = self.get_state("sensor.hampus_zfold_phone_state")
            charger_type = self.get_state("sensor.hampus_zfold_charger_type")
            return phone_state == "okänd" or charger_type == "usb"  # Changed back to OR
        except Exception as e:
            self.error("Night light check failed", e)
            return False

    async def _deactivate_current_mode(self) -> None:
        """Deactivate current mode with proper cleanup"""
        try:
            self.log(f"Deactivating mode: {self._state.mode}")

            mode_handlers = {
                LightMode.FOCUS: self._deactivate_focus,
                LightMode.CHRISTMAS: self._deactivate_christmas,
                LightMode.NIGHT: self._deactivate_night,
                LightMode.DEFAULT: self._deactivate_default
            }

            handler = mode_handlers.get(
                self._state.mode, self._deactivate_default)
            await self._safe_cleanup()
            await handler()
            self._state.mode = LightMode.DEFAULT

        except Exception as e:
            self.error(f"Failed to deactivate mode {self._state.mode}", e)
            await self._safe_cleanup()

    def _deactivate_current_mode_sync(self) -> None:
        """Synchronous mode deactivation"""
        self._safe_cleanup_sync()
        self._state.mode = LightMode.DEFAULT

    async def _deactivate_focus(self) -> None:
        """Deactivate focus mode"""
        try:
            self.turn_off(self.ENTITIES['main'])
            self.turn_off(self.ENTITIES['focus'])
        except Exception as e:
            self.error("Focus mode deactivation failed", e)

    async def _deactivate_christmas(self) -> None:
        """Deactivate christmas mode"""
        try:
            self._state.is_running = False
            # Turn off even and odd christmas lights
            for light_list in [self.ENTITIES['christmas_even'], self.ENTITIES['christmas_odd']]:
                for light in light_list:
                    self.turn_off(light)
        except Exception as e:
            self.error("Christmas mode deactivation failed", e)

    async def _deactivate_night(self) -> None:
        """Deactivate night mode"""
        try:
            self.turn_off(self.ENTITIES['night'])
            for light in self.ENTITIES['night_array']:
                self.turn_off(light)
        except Exception as e:
            self.error("Night mode deactivation failed", e)

    async def _deactivate_default(self) -> None:
        """Deactivate default mode"""
        try:
            self.turn_off(self.ENTITIES['main'])
        except Exception as e:
            self.error("Default mode deactivation failed", e)

    def turn_on_night_lights(self, kwargs=None):
        """Sync version for callback compatibility"""
        for light in self.ENTITIES['night_array']:
            self.turn_on(light, brightness=64, color_temp=350)

    def turn_off_all_lights(self, callback=None):
        """Sync version for callback compatibility"""
        for entity in self.ENTITIES.values():
            if isinstance(entity, list):
                for light in entity:
                    self.turn_off(light)
            else:
                self.turn_off(entity)
        if callback:
            self._callbacks.append(self.run_in(callback, 1))

    def turn_on(self, entity_id, **kwargs):
        """Override turn_on to use proper service call"""
        try:
            self.call_service("light/turn_on", entity_id=entity_id, **kwargs)
        except Exception as e:
            self.error(f"Failed to turn on {entity_id}", e)

    def turn_off(self, entity_id, **kwargs):
        """Override turn_off to use proper service call"""
        try:
            self.call_service("light/turn_off", entity_id=entity_id, **kwargs)
        except Exception as e:
            self.error(f"Failed to turn off {entity_id}", e)

    def _handle_phone_state_sync(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Synchronous phone state handler"""
        if self._state.mode == LightMode.NIGHT and new == "okänd":
            self.turn_on(self.ENTITIES['night'], rgb_color=[
                         0, 0, 255], brightness=102)

    def _handle_charger_type_sync(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Synchronous charger type handler"""
        if self._state.mode == LightMode.NIGHT and new == "usb":
            self.turn_on(self.ENTITIES['night'], rgb_color=[
                         0, 0, 255], brightness=102)

    def _activate_initial_mode(self) -> None:
        """Activate the appropriate mode based on current states"""
        try:
            if self.get_state("input_boolean.presence_mode") != "on":
                return

            if self.get_state("binary_sensor.narvarodetektor_narvaro") != "on":
                return

            # Check modes in order of priority
            if self.get_state("input_boolean.night_mode") == "on":
                self._state.mode = LightMode.NIGHT
                self._activate_night_sync()
            elif self.get_state("input_boolean.christmas_mode") == "on":
                self._state.mode = LightMode.CHRISTMAS
                self._state.is_running = True
                self._activate_christmas_sync()
            elif self.get_state("input_boolean.desk_focus_lights") == "on":
                self._state.mode = LightMode.FOCUS
                self._activate_focus_sync()
            else:
                self._state.mode = LightMode.DEFAULT
                self._activate_default_sync()

        except Exception as e:
            self.error("Failed to activate initial mode", e)

    def _handle_main_light_change_sync(self, entity: str, attribute: str, old: str, new: str, kwargs: dict) -> None:
        """Handle changes to the main light when in focus mode"""
        try:
            # Only react if we're in focus mode
            if self._state.mode == LightMode.FOCUS:
                # Check if focus mode is still enabled
                if self.get_state("input_boolean.desk_focus_lights") == "on":
                    self.log(
                        f"Main light changed - attribute: {attribute}, old: {old}, new: {new}")
                    # Add small delay to allow all attributes to settle
                    self._callbacks.append(self.run_in(
                        lambda x: self._activate_focus_sync(), 1))
        except Exception as e:
            self.error("Failed to handle main light change", e)

import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime

class PresenceLighting(hass.Hass):
    def initialize(self):
        self.log("Initializing PresenceLighting app")
        self.light_entity = "light.ljus"
        self.focus_light = "light.taklampa_lampa_3"
        self.night_light = "light.vagglampa"  # Bedroom night light
        self.christmas_mode_running = False
        self.night_lights_array = ["light.zigbee_night_lights"]
        self.callbacks = []
        self.no_presence_start_time = None

        # Listen for presence sensor changes
        self.listen_state(self.presence_trigger, "binary_sensor.narvarodetektor_narvaro")
        self.listen_state(self.christmas_mode_on, "input_boolean.christmas_mode", new="on")
        self.listen_state(self.christmas_mode_off, "input_boolean.christmas_mode", new="off")
        self.listen_state(self.handle_focus_mode, "input_boolean.desk_focus_lights")
        self.listen_state(self.handle_night_mode, "input_boolean.night_mode")
        self.listen_state(self.handle_phone_state_change, "sensor.hampus_zfold_phone_state")
        self.listen_state(self.handle_charger_type_change, "sensor.hampus_zfold_charger_type")

    def presence_trigger(self, entity, attribute, old, new, kwargs):
        if self.get_state("input_boolean.presence_mode") != "on":
            return

        if new == "on":
            self.no_presence_start_time = datetime.now().strftime("%H:%M")
            self.log(f"Presence detected, start time: {self.no_presence_start_time}")
            self.handle_presence_on()
        else:
            self.handle_presence_off()

    def handle_presence_on(self):
        if self.get_state("input_boolean.desk_focus_lights") == "on":
            self.activate_focus_mode()
        elif self.get_state("input_boolean.christmas_mode") == "on":
            self.activate_christmas_mode()
        elif self.get_state("input_boolean.night_mode") == "on":
            self.activate_night_mode()
        else:
            self.activate_default_mode()

    def handle_presence_off(self):
        self.cancel_all_scheduled_callbacks()
        if self.get_state("input_boolean.desk_focus_lights") == "on":
            self.deactivate_focus_mode()
        elif self.get_state("input_boolean.christmas_mode") == "on":
            self.deactivate_christmas_mode()
        elif self.get_state("input_boolean.night_mode") == "on":
            self.deactivate_night_mode()
        else:
            self.deactivate_default_mode()
        self.log("Presence disappeared, handling lights according to mode priorities")

    def activate_focus_mode(self):
        light_settings = self.get_light_settings()
        self.turn_on(self.light_entity, **light_settings)
        self.run_in(self.set_focus_light, 1)

    def deactivate_focus_mode(self):
        self.turn_off(self.light_entity)
        self.turn_off(self.night_light)
        self.turn_off(self.focus_light)

    def activate_christmas_mode(self):
        if not self.christmas_mode_running:
            self.christmas_mode_on(None, None, None, None, None)

    def deactivate_christmas_mode(self):
        self.christmas_mode_off(None, None, None, None, None)

    def activate_night_mode(self):
        self.turn_on_night_lights()

    def deactivate_night_mode(self):
        self.turn_off(self.light_entity)
        self.turn_off(self.focus_light)
        self.turn_off_night_lights()
        if self.should_turn_on_bedroom_night_light():
            self.turn_on(self.night_light, rgb_color=[0, 0, 255], brightness=102)

    def activate_default_mode(self):
        light_settings = self.get_light_settings()
        self.turn_on(self.light_entity, **light_settings)

    def deactivate_default_mode(self):
        self.turn_off(self.light_entity)
        self.turn_off(self.focus_light)
        self.turn_off(self.night_light)

    def handle_focus_mode(self, entity, attribute, old, new, kwargs):
        if new == "on" and self.get_state("binary_sensor.narvarodetektor_narvaro") == "on":
            self.set_focus_light(None)
        elif new == "off":
            light_settings = self.get_light_settings()
            self.turn_on(self.focus_light, **light_settings)

    def set_focus_light(self, kwargs):
        self.turn_on(self.focus_light, color_temp=250, brightness=255)

    def handle_night_mode(self, entity, attribute, old, new, kwargs):
        if new == "on":
            self.turn_off_all_lights(callback=self.turn_on_night_lights)
            if self.should_turn_on_bedroom_night_light():
                self.turn_on(self.night_light, rgb_color=[0, 0, 255], brightness=102)
        elif new == "off":
            self.turn_off(self.night_light)
            self.turn_off_night_lights()
            self.turn_on_default_lights()

    def handle_phone_state_change(self, entity, attribute, old, new, kwargs):
        if self.get_state("input_boolean.night_mode") == "on" and new == "okänd":
            self.turn_on(self.night_light, rgb_color=[0, 0, 255], brightness=102)

    def handle_charger_type_change(self, entity, attribute, old, new, kwargs):
        if self.get_state("input_boolean.night_mode") == "on" and new == "usb":
            self.turn_on(self.night_light, rgb_color=[0, 0, 255], brightness=102)

    def should_turn_on_bedroom_night_light(self):
        phone_state = self.get_state("sensor.hampus_zfold_phone_state")
        charger_type = self.get_state("sensor.hampus_zfold_charger_type")
        return phone_state == "okänd" or charger_type == "usb"

    def christmas_mode_on(self, entity, attribute, old, new, kwargs):
        if self.get_state("binary_sensor.narvarodetektor_narvaro") == "on":
            self.christmas_mode_running = True
            self.custom_alternating_effect({
                "lights1": ["light.christmas1"],
                "lights2": ["light.christmas2"],
                "brightness": 150
            })

    def christmas_mode_off(self, entity, attribute, old, new, kwargs):
        self.cancel_all_scheduled_callbacks()
        self.log("Cancelling all scheduled callbacks")
        self.christmas_mode_running = False
        if self.get_state("binary_sensor.narvarodetektor_narvaro") == "off":
            self.turn_off(self.light_entity)
        else:
            light_settings = self.get_light_settings()
            self.turn_on(self.light_entity, **light_settings)

    def get_light_settings(self):
        current_total_minutes = self.time().hour * 60 + self.time().minute
        early_morning_start_minutes = 5 * 60
        morning_start_minutes = 8 * 60
        afternoon_start_minutes = 12 * 60
        evening_start_minutes = 20 * 60

        if early_morning_start_minutes <= current_total_minutes < morning_start_minutes:
            return {"brightness": 75, "color_temp": 250}
        elif morning_start_minutes <= current_total_minutes < afternoon_start_minutes:
            return {"brightness": 125, "color_temp": 200}
        elif afternoon_start_minutes <= current_total_minutes < evening_start_minutes:
            return {"brightness": 255, "color_temp": 153}
        else:
            return {"brightness": 50, "color_temp": 333}

    def cancel_all_scheduled_callbacks(self):
        for callback in self.callbacks:
            self.cancel_timer(callback)
        self.callbacks = []

    def custom_alternating_effect(self, kwargs):
        if self.get_state("input_boolean.christmas_mode") != "on":
            self.log("Christmas mode is off, cancelling custom effect")
            self.christmas_mode_running = False
            return

        lights1 = kwargs['lights1']
        lights2 = kwargs['lights2']
        brightness = kwargs['brightness']
        self.callbacks = []

        for light in lights1:
            callback = self.run_in(self.set_color, 0, light=light, color='red', brightness=brightness)
            self.callbacks.append(callback)

        for light in lights2:
            callback = self.run_in(self.set_color, 0, light=light, color='green', brightness=brightness)
            self.callbacks.append(callback)

        for light in lights1:
            callback = self.run_in(self.set_color, 5, light=light, color='green', brightness=brightness)
            self.callbacks.append(callback)

        for light in lights2:
            callback = self.run_in(self.set_color, 5, light=light, color='red', brightness=brightness)
            self.callbacks.append(callback)

        callback = self.run_in(self.custom_alternating_effect, 10, lights1=lights1, lights2=lights2, brightness=brightness)
        self.callbacks.append(callback)

    def set_color(self, kwargs):
        light = kwargs['light']
        color = kwargs['color']
        brightness = kwargs['brightness']

        try:
            if color == 'red':
                self.turn_on(light, rgb_color=[255, 0, 0], brightness=brightness, transition=1)
            else:
                self.turn_on(light, rgb_color=[0, 255, 0], brightness=brightness, transition=1)
        except Exception as e:
            self.log(f"Error turning on {light}: {e}", level="ERROR")

    def rgb_to_xy(self, red, green, blue):
        red, green, blue = red / 255, green / 255, blue / 255
        r = (red > 0.04045) * ((red + 0.055) / (1.0 + 0.055)) ** 2.4 + (red <= 0.04045) * (red / 12.92)
        g = (green > 0.04045) * ((green + 0.055) / (1.0 + 0.055)) ** 2.4 + (green <= 0.04045) * (green / 12.92)
        b = (blue > 0.04045) * ((blue + 0.055) / (1.0 + 0.055)) ** 2.4 + (blue <= 0.04045) * (blue / 12.92)

        X = r * 0.649926 + g * 0.103455 + b * 0.197109
        Y = r * 0.234327 + g * 0.743075 + b * 0.022598
        Z = r * 0.000000 + g * 0.053077 + b * 1.035763

        x = X / (X + Y + Z)
        y = Y / (X + Y + Z)

        return [x, y]

    def calculate_no_presence_duration(self, start_time, current_time):
        start_hours, start_minutes = map(int, start_time.split(":"))
        current_hours, current_minutes = map(int, current_time.split(":"))

        start_total_minutes = start_hours * 60 + start_minutes
        current_total_minutes = current_hours * 60 + current_minutes

        if current_total_minutes < start_total_minutes:
            current_total_minutes += 24 * 60

        return current_total_minutes - start_total_minutes

    def turn_on_night_lights(self, kwargs=None):
        for light in self.night_lights_array:
            self.turn_on(light, brightness=64, color_temp=350)

    def turn_off_night_lights(self):
        for light in self.night_lights_array:
            self.turn_off(light)

    def turn_off_all_lights(self, callback=None):
        self.turn_off(self.light_entity)
        self.turn_off(self.focus_light)
        self.turn_off(self.night_light)
        self.turn_off_night_lights()
        if callback:
            self.run_in(callback, 1)

    def turn_on_default_lights(self):
        light_settings = self.get_light_settings()
        self.turn_on(self.light_entity, **light_settings)

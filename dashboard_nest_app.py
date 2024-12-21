class DashboardToNestHubApp(hass.Hass):
    def initialize(self):
        self.listen_state(self.narvarodetektor_changed,
                          "binary_sensor.narvarodetektor_narvaro")
        self.listen_state(self.pc_cpuload_changed, "sensor.pc_cpuload")
        self.cpu_load = None
        self.currentDashboard = None

    def pc_cpuload_changed(self, entity, attribute, old_state, new_state, kwargs):
        self.cpu_load = new_state

    def narvarodetektor_changed(self, entity, attribute, old_state, new_state, kwargs):
        if new_state == "on":
            self.run_in(self.activate_dashboard, 1)  # 1-second delay
        elif new_state == "off":
            self.run_in(self.deactivate_dashboard, 1)  # 1-second delay

    def activate_dashboard(self, kwargs):
        try:
            if self.cpu_load and self.is_float(self.cpu_load):
                if self.currentDashboard != "dashboard":
                    self.call_service("media_player/turn_off",
                                      entity_id="media_player.nesthub0445")

                self.call_service("shell_command/cast_dashboard")
                self.currentDashboard = "dashboard"
            else:
                if self.currentDashboard != "lovelace":
                    self.call_service("shell_command/stop_catt")

                self.call_service("script/cast_lovelace_dashboard_to_nest_hub")
                self.currentDashboard = "lovelace"
        except Exception as e:
            pass

    def deactivate_dashboard(self, kwargs):
        try:
            self.call_service("media_player/turn_off",
                              entity_id="media_player.nesthub0445")
            self.call_service("shell_command.stop_catt")
        except Exception as e:
            pass

    def is_float(self, value):
        try:
            float(value)
            return True
        except ValueError:
            return False

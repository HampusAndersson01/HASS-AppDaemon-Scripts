# Home Assistant AppDaemon Scripts

This repository contains various AppDaemon scripts for Home Assistant. These scripts automate different aspects of my smart home setup, providing functionality like presence-based lighting, time-sensitive modes, and special settings for specific use cases. This repository serves as a personal backup of my configurations.

## Scripts

### Presence Lighting

The `presence_lighting.py` script is an AppDaemon app designed to manage and control lighting based on presence detection, time of day, and specific modes. It utilizes Home Assistant sensors and entities to create a smart and adaptable lighting system.

#### Features

- **Time-based Lighting**: Dynamically adjusts lighting based on the time of day.
- **Presence Detection**: Activates lights when presence is detected.
- **Night Mode**: Provides soothing lighting during nighttime.
- **Focus Mode**: Ensures optimal lighting for focused tasks.
- **Christmas Mode**: Alternates red and green lighting for festive ambiance.
- **Async Operations**: Employs asynchronous functions for efficient state checks and control.
- **Error Handling**: Logs errors and defaults to night settings if issues arise.

---

#### Modes and Criteria

**Presence Mode**

- All lighting modes now respect the presence mode setting
- When presence mode is disabled, lights will operate without presence checks
- When presence mode is enabled, lights will only activate when presence is detected

##### **LightMode.DEFAULT**

- **Early Morning (5:00 AM - 8:00 AM)**:

  - **Criteria**: Time of day is between 5:00 AM and 8:00 AM.
  - **Actions**: Uses settings from `LIGHT_SETTINGS['early_morning']`.

- **Morning (8:00 AM - 12:00 PM)**:

  - **Criteria**: Time of day is between 8:00 AM and 12:00 PM.
  - **Actions**: Uses settings from `LIGHT_SETTINGS['morning']`.

- **Afternoon (12:00 PM - 8:00 PM)**:

  - **Criteria**: Time of day is between 12:00 PM and 8:00 PM.
  - **Actions**: Uses settings from `LIGHT_SETTINGS['afternoon']`.

- **Night (8:00 PM - 5:00 AM)**:
  - **Criteria**: Time of day is between 8:00 PM and 5:00 AM.
  - **Actions**: Uses settings from `LIGHT_SETTINGS['night']`.

---

##### **LightMode.FOCUS**

- **Criteria**:
  - Activated when the system is in focus mode
  - If presence mode is enabled, also requires presence detection
- **Actions**: Keeps a desk light bright white for reading or working, regardless of other lights. Reactivates the focus light if the mode is enabled while a main light state changes.

---

##### **LightMode.CHRISTMAS**

- **Criteria**:
  - Activated when the system is in Christmas mode
  - If presence mode is enabled, also requires presence detection
- **Actions**: Alternates odd and even lights between red and green colors based on two separate entities while presence is detected.

---

##### **LightMode.NIGHT**

Night Mode is activated based on an input boolean (`input_boolean.night_mode`). It consists of two independent systems:

1. **Presence Night Light**:

   - **Criteria**:
     - Night Mode is enabled
     - If presence mode is enabled, requires presence detection
   - **Actions**: Turns on specific lights in a soothing manner for nighttime movement.

2. **Bedroom Night Light**:
   - **Criteria**: Turns on if the phone is charging via USB and is in a call state (`"unknown"` or `"offhook"`).
   - **Actions**: Activates bedroom lights with specific settings, unaffected by presence detection.

These two systems operate independently.

---

#### Usage

To use this script:

1. Place it in the appropriate directory for AppDaemon apps.
2. Configure the necessary sensors, light entities, and input booleans in Home Assistant.
3. Enable or disable Night Mode using the `input_boolean.night_mode`.
4. The script will automatically manage lighting based on the defined criteria and modes.

Enjoy a smarter, more responsive home lighting experience!

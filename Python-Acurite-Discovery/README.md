# Acurite MQTT Discovery Publisher

Publishes Home Assistant MQTT discovery messages for Acurite sensors decoded by [rtl_433](https://github.com/merbanan/rtl_433).

Once run, each sensor automatically appears in Home Assistant as a fully configured device with the correct entities, area assignment, and device class — no manual entity configuration required. Re-run any time you add sensors, replace batteries, rename a sensor, or change its area.

**Supported models:** Acurite-Tower, 06002M, 592TX, Acurite-606TX, Acurite-986

---

## Requirements

- Python 3.10+
- An MQTT broker reachable from this machine
- rtl_433 publishing decoded sensor data to that broker
- Home Assistant with the MQTT integration enabled and discovery turned on

---

## Installation

```bash
# Create and enter your project directory
mkdir ~/homeassistant-rtl && cd ~/homeassistant-rtl

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Configuration

Copy the example config and edit it:

```bash
cp config.example.yaml config.yaml
nano config.yaml
```

### MQTT settings

| Field | Description | Default |
|---|---|---|
| `mqtt.broker` | Broker hostname or IP | `localhost` |
| `mqtt.port` | Broker port | `1883` |
| `mqtt.username` | MQTT username (omit if no auth) | — |
| `mqtt.password` | MQTT password (omit if no auth) | — |
| `discovery_prefix` | Must match HA's discovery prefix | `homeassistant` |
| `base_path` | Root topic where rtl_433 publishes | `rtl_433` |

### Sensor fields

| Field | Required | Description |
|---|---|---|
| `id` | ✅ | **Never change this.** Your stable permanent key for this sensor. Drives all `unique_id` and device identifier values in HA. |
| `device_id` | ✅ | The numeric radio ID rtl_433 reports. Update this after a battery swap. |
| `model` | ✅ | Sensor model — see supported models below. |
| `name` | optional | Friendly label in Home Assistant. Safe to change at any time. |
| `area` | optional | HA area to assign the device to. Created automatically if it doesn't exist. |
| `base_path` | optional | Per-sensor override for the global `base_path`. |

### Finding your device IDs

Watch the rtl_433 MQTT output and note the `id` field for each sensor:

```bash
mosquitto_sub -h <broker> -u <user> -P <pass> -t "rtl_433/#" -v
```

Example output:
```
rtl_433/Acurite-Tower/326 {"time":"...","model":"Acurite-Tower","id":326,"channel":"A","battery_ok":1,"temperature_C":21.3,"humidity":58}
```

---

## Usage

```bash
# Activate venv (if not already active)
source venv/bin/activate

# Publish discovery messages for all sensors in config.yaml
python publish-discovery.py

# Use a different config file
python publish-discovery.py --config other.yaml

# Remove all sensors from Home Assistant
python publish-discovery.py --remove
```

The script connects, publishes all messages with `retain=true`, then exits. Retained messages persist on the broker across HA restarts — you only need to re-run when something changes.

---

## Battery Swap Workflow

When you replace batteries, the sensor gets a new random radio ID. To update it without losing any HA history:

1. Find the new ID by watching rtl_433:
   ```bash
   mosquitto_sub -h <broker> -t "rtl_433/#" -v
   ```
2. In `config.yaml`, update `device_id` for that sensor — leave `id`, `name`, `area`, and `model` untouched
3. Re-run the script:
   ```bash
   python publish-discovery.py
   ```

HA will update the state topic on the existing device. All history, automations, and dashboard cards are preserved because `unique_id` and device identifiers are derived from the stable `id` field, not `device_id`.

---

## Area Assignment

Adding `area` to a sensor entry sets `suggested_area` in the MQTT discovery payload:

```yaml
- id: "kitchen"
  model: "Acurite-Tower"
  device_id: 711
  name: "Kitchen"
  area: "Kitchen"       # ← HA assigns the device here on creation
```

**Behaviour:**
- The area is created automatically in HA if it doesn't already exist
- Area names are case-sensitive and must match exactly
- HA will not override a manually-assigned area on an existing device — delete the device in HA first if you need to force a change, then re-run the script

---

## Entities Created

Each sensor registers as a **Device** in Home Assistant with the following entities:

### Acurite-Tower / 06002M / 592TX
| Entity | Type | Notes |
|---|---|---|
| Temperature | Sensor | °C, expires after 10 min |
| Humidity | Sensor | %, expires after 10 min |
| Battery Low | Binary Sensor | `ON` = battery needs replacement |
| Channel | Sensor | Diagnostic |

### Acurite-606TX
| Entity | Type | Notes |
|---|---|---|
| Temperature | Sensor | °C, expires after 10 min |
| Battery Low | Binary Sensor | `ON` = battery needs replacement |
| Channel | Sensor | Diagnostic |
| Button | Binary Sensor | Diagnostic — sync/reset button press |

### Acurite-986
| Entity | Type | Notes |
|---|---|---|
| Temperature | Sensor | °C, expires after 10 min |
| Battery Low | Binary Sensor | `ON` = battery needs replacement |
| Channel | Sensor | Diagnostic |
| Status | Sensor | Diagnostic |

> **Temperature units:** Always stored in °C. rtl_433 may publish either `temperature_C` or `temperature_F` depending on your configuration — the value template handles both automatically.

---

## Troubleshooting

### Messages publish successfully but nothing appears in Home Assistant

The most common cause is an MQTT broker ACL blocking publishes to `homeassistant/#`. Check your broker config and ensure your MQTT user has write access to that topic prefix.

With Mosquitto, edit `/etc/mosquitto/acl` and add:
```
user mqtt_user
topic readwrite homeassistant/#
topic readwrite rtl_433/#
```

Then restart Mosquitto:
```bash
sudo systemctl restart mosquitto
```

### Verify messages are reaching the broker

Subscribe to the wildcard topic in a separate terminal and re-run the script:

```bash
mosquitto_sub -h <broker> -u <user> -P <pass> -t "homeassistant/#" -v
```

You should see one line per entity as the script runs. If nothing appears, it's a broker/ACL issue rather than a script issue.

### Sensors show as unavailable in Home Assistant

Normal until rtl_433 publishes a reading for that sensor. Entities expire after 10 minutes (`expire_after: 600`) with no incoming message. Verify rtl_433 is running and the sensor is transmitting — most Acurite sensors transmit every 30–90 seconds.

### Error: `id` is required

Every sensor entry must have a unique `id` field. See the example config for the correct format.

### Duplicate id error

Each sensor must have a unique `id`. The script validates this before connecting and will tell you which entry is duplicated.

---

## File Structure

```
homeassistant-rtl/
├── publish-discovery.py    # Main script
├── config.yaml             # Your configuration (edit this)
├── config.example.yaml     # Reference with all options documented
├── requirements.txt        # Python dependencies
└── README.md
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `paho-mqtt` | MQTT client |
| `PyYAML` | Config file parsing |

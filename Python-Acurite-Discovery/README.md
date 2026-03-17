# Acurite MQTT Discovery Publisher

Publishes Home Assistant MQTT discovery messages for Acurite sensors decoded by [rtl_433](https://github.com/merbanan/rtl_433).

Once run, each sensor automatically appears in Home Assistant as a fully configured device — no manual entity configuration required.

**Supported models:** Acurite-Tower, 06002M, 592TX, Acurite-606TX, Acurite-986

---

## Requirements

- Python 3.10+
- An MQTT broker reachable from this machine
- rtl_433 publishing to the same broker
- Home Assistant with the MQTT integration enabled

---

## Installation

```bash
# Clone or copy the project files into a directory
cd ~/homeassistant-rtl

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Configuration

Copy `config.example.yaml` to `config.yaml` and edit it:

```bash
cp config.example.yaml config.yaml
nano config.yaml
```

### Key settings

| Field | Description | Default |
|---|---|---|
| `mqtt.broker` | Broker hostname or IP | `localhost` |
| `mqtt.port` | Broker port | `1883` |
| `mqtt.username` | MQTT username (omit if none) | — |
| `mqtt.password` | MQTT password (omit if none) | — |
| `discovery_prefix` | Must match HA's discovery prefix | `homeassistant` |
| `base_path` | Root topic where rtl_433 publishes | `rtl_433` |

### Finding your device IDs

Watch the rtl_433 MQTT output and note the `id` field for each sensor:

```bash
mosquitto_sub -h <broker> -t "rtl_433/#" -v
```

Example output:
```
rtl_433/Acurite-Tower/326 {"time":"...","model":"Acurite-Tower","id":326,"channel":"A","battery_ok":1,"temperature_C":21.3,"humidity":58}
```

---

## Usage

```bash
# Activate the venv first (if not already active)
source venv/bin/activate

# Publish discovery messages for all sensors in config.yaml
python publish-discovery.py

# Use a different config file
python publish-discovery.py --config other.yaml

# Remove all sensors from Home Assistant
python publish-discovery.py --remove
```

The script connects, publishes all messages with `retain=true`, then exits. You only need to run it once per sensor — retained messages persist on the broker and survive HA restarts.

Re-run it any time you add, rename, or remove sensors.

---

## Entities Created

Each sensor registers as a **Device** in Home Assistant containing the following entities:

### Acurite-Tower / 06002M / 592TX
| Entity | Type | Notes |
|---|---|---|
| Temperature | Sensor | °C, expires after 10 min |
| Humidity | Sensor | %, expires after 10 min |
| Battery Low | Binary Sensor | ON = low battery |
| Channel | Sensor | Diagnostic |

### Acurite-606TX
| Entity | Type | Notes |
|---|---|---|
| Temperature | Sensor | °C, expires after 10 min |
| Battery Low | Binary Sensor | ON = low battery |
| Channel | Sensor | Diagnostic |
| Button | Binary Sensor | Diagnostic — sync/reset button |

### Acurite-986
| Entity | Type | Notes |
|---|---|---|
| Temperature | Sensor | °C, expires after 10 min |
| Battery Low | Binary Sensor | ON = low battery |
| Channel | Sensor | Diagnostic |
| Status | Sensor | Diagnostic |

> **Note:** Temperature is always stored in °C. rtl_433 may publish `temperature_C` or `temperature_F` depending on your configuration — the value template handles both automatically.

---

## Troubleshooting

### Messages publish successfully but nothing appears in Home Assistant

Check that your MQTT user has permission to publish to `homeassistant/#`. Some brokers restrict topics via ACL. With Mosquitto, check `/etc/mosquitto/acl` and ensure your user has write access:

```
user mqtt_user
topic readwrite #
```

Or more specifically:
```
topic readwrite homeassistant/#
topic readwrite rtl_433/#
```

Restart Mosquitto after any ACL changes:
```bash
sudo systemctl restart mosquitto
```

### Verify messages are reaching the broker

In MQTT Explorer (or via CLI), subscribe to the wildcard topic and re-run the script:

```bash
mosquitto_sub -h <broker> -u <user> -P <pass> -t "homeassistant/#" -v
```

You should see one line per entity as the script runs.

### Sensors show unavailable in Home Assistant

This is normal until rtl_433 publishes a reading for that sensor. Entities have a 10-minute expiry (`expire_after: 600`) — they will go unavailable if no message is received within that window. Check that rtl_433 is running and receiving signals.

### DeprecationWarning about callback API

This is harmless but means your paho-mqtt version is newer than 1.x. The script already uses `CallbackAPIVersion.VERSION2` to suppress this. If you still see it, update paho-mqtt:

```bash
pip install --upgrade paho-mqtt
```

---

## File Structure

```
homeassistant-rtl/
├── publish-discovery.py   # Main script
├── config.yaml            # Your configuration (edit this)
├── config.example.yaml    # Reference copy with all options documented
├── requirements.txt       # Python dependencies
└── README.md
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `paho-mqtt` | MQTT client |
| `PyYAML` | Config file parsing |

#!/usr/bin/env python3
"""
Acurite MQTT Discovery Publisher
Publishes or removes Home Assistant MQTT discovery messages for Acurite sensors.

Supports: Acurite-Tower, 06002M, 592TX, Acurite-606TX, Acurite-986

The `id` field in config.yaml is the stable primary key. It is used for all
unique_id and device identifier values in Home Assistant. This means:
  - Changing `device_id` (battery swap)  → HA device keeps its history
  - Changing `name`                      → HA device renames cleanly
  - Changing `area`                      → HA device moves to new area
  - Only `id` must never change

Usage:
    python publish-discovery.py                   # publish all sensors
    python publish-discovery.py --config my.yaml  # use a different config
    python publish-discovery.py --remove          # remove all sensors
"""

import argparse
import json
import sys
import time
import yaml
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

# ---------------------------------------------------------------------------
# Model capabilities
# ---------------------------------------------------------------------------

VALID_MODELS = {"Acurite-Tower", "06002M", "592TX", "Acurite-606TX", "Acurite-986"}

HAS_HUMIDITY = {"Acurite-Tower", "06002M", "592TX"}
HAS_BUTTON   = {"Acurite-606TX"}
HAS_STATUS   = {"Acurite-986"}


# ---------------------------------------------------------------------------
# Discovery payload builders
# ---------------------------------------------------------------------------

def _device_block(stable_id: str, model_name: str, sensor_name: str,
                  area: str | None = None) -> dict:
    """
    Device block uses stable_id so HA device identity never changes.
    If area is provided, suggested_area is included so HA assigns the device
    to that area on first creation. Updating area and re-running the script
    will move the device.
    """
    block = {
        "identifiers":  [f"acurite_{stable_id}"],
        "manufacturer": "Acurite",
        "model":        model_name,
        "name":         sensor_name,
    }
    if area:
        block["suggested_area"] = area
    return block


def build_payloads(stable_id: str, model_name: str, device_id: str,
                   sensor_name: str, base_path: str, discovery_prefix: str,
                   area: str | None = None) -> list[tuple[str, str]]:
    """
    Return a list of (topic, payload_json) tuples for the given sensor.

    stable_id  - permanent key from config `id:` field (never changes)
    device_id  - the rtl_433 radio ID (changes on battery swap)
    area       - optional HA area name (suggested_area in device block)
    """
    uid_prefix = f"acurite_{stable_id}"
    # State topic uses live device_id since that's what rtl_433 publishes to
    base_topic = f"{base_path}/{model_name}/{device_id}"
    device     = _device_block(stable_id, model_name, sensor_name, area)
    msgs       = []

    def pub(component: str, entity: str, payload: dict):
        topic = f"{discovery_prefix}/{component}/{uid_prefix}/{entity}/config"
        msgs.append((topic, json.dumps(payload)))

    common = {
        "state_topic":           base_topic,
        "json_attributes_topic": base_topic,
        "expire_after":          600,
        "device":                device,
    }

    # --- Temperature (all models) ---
    pub("sensor", "temperature", {
        **common,
        "name":                f"{sensor_name} Temperature",
        "unique_id":           f"{uid_prefix}_temp",
        "value_template":      (
            "{% if 'temperature_C' in value_json %}"
            "{{ value_json.temperature_C | float | round(1) }}"
            "{% else %}"
            "{{ ((value_json.temperature_F - 32) * 5/9) | round(1) }}"
            "{% endif %}"
        ),
        "device_class":        "temperature",
        "unit_of_measurement": "°C",
        "state_class":         "measurement",
    })

    # --- Humidity (Tower / 06002M / 592TX) ---
    if model_name in HAS_HUMIDITY:
        pub("sensor", "humidity", {
            **common,
            "name":                f"{sensor_name} Humidity",
            "unique_id":           f"{uid_prefix}_humidity",
            "value_template":      "{{ value_json.humidity | int }}",
            "device_class":        "humidity",
            "unit_of_measurement": "%",
            "state_class":         "measurement",
        })

    # --- Battery (all models) ---
    pub("binary_sensor", "battery", {
        **common,
        "name":           f"{sensor_name} Battery Low",
        "unique_id":      f"{uid_prefix}_battery",
        "value_template": "{{ 'OFF' if value_json.battery_ok == 1 else 'ON' }}",
        "payload_on":     "ON",
        "payload_off":    "OFF",
        "device_class":   "battery",
    })

    # --- Channel (all models) ---
    pub("sensor", "channel", {
        **common,
        "name":            f"{sensor_name} Channel",
        "unique_id":       f"{uid_prefix}_channel",
        "value_template":  "{{ value_json.channel }}",
        "icon":            "mdi:radio-tower",
        "entity_category": "diagnostic",
    })

    # --- Button (606TX only) ---
    if model_name in HAS_BUTTON:
        pub("binary_sensor", "button", {
            **common,
            "name":            f"{sensor_name} Button",
            "unique_id":       f"{uid_prefix}_button",
            "value_template":  "{{ 'ON' if value_json.button == 1 else 'OFF' }}",
            "payload_on":      "ON",
            "payload_off":     "OFF",
            "icon":            "mdi:gesture-tap-button",
            "entity_category": "diagnostic",
        })

    # --- Status (986 only) ---
    if model_name in HAS_STATUS:
        pub("sensor", "status", {
            **common,
            "name":            f"{sensor_name} Status",
            "unique_id":       f"{uid_prefix}_status",
            "value_template":  "{{ value_json.status }}",
            "icon":            "mdi:information-outline",
            "entity_category": "diagnostic",
        })

    return msgs


def removal_topics(stable_id: str, discovery_prefix: str) -> list[tuple[str, str]]:
    """Return (topic, empty_payload) pairs to remove all entities for a sensor."""
    uid_prefix = f"acurite_{stable_id}"
    entities = [
        ("sensor",        "temperature"),
        ("sensor",        "humidity"),
        ("binary_sensor", "battery"),
        ("sensor",        "channel"),
        ("binary_sensor", "button"),
        ("sensor",        "status"),
    ]
    return [
        (f"{discovery_prefix}/{comp}/{uid_prefix}/{entity}/config", "")
        for comp, entity in entities
    ]


# ---------------------------------------------------------------------------
# MQTT helpers
# ---------------------------------------------------------------------------

def connect_mqtt(cfg: dict) -> mqtt.Client:
    broker    = cfg.get("broker", "localhost")
    port      = int(cfg.get("port", 1883))
    username  = cfg.get("username")
    password  = cfg.get("password")
    client_id = cfg.get("client_id", "acurite-discovery")

    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2,
                         client_id=client_id)
    if username:
        client.username_pw_set(username, password)

    if cfg.get("tls", False):
        client.tls_set(
            ca_certs=cfg.get("ca_cert"),
            certfile=cfg.get("certfile"),
            keyfile=cfg.get("keyfile"),
        )

    print(f"Connecting to MQTT broker {broker}:{port} ...", end=" ", flush=True)
    client.connect(broker, port, keepalive=60)
    print("OK")
    return client


def publish_messages(client: mqtt.Client, messages: list[tuple[str, str]],
                     retain: bool = True, delay: float = 0.05):
    for topic, payload in messages:
        result = client.publish(topic, payload, retain=retain, qos=1)
        try:
            result.wait_for_publish(timeout=5.0)
        except RuntimeError:
            pass
        action = "REMOVE" if payload == "" else "PUBLISH"
        print(f"  [{action}] {topic}")
        if delay:
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Config loading & validation
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def validate_sensor(sensor: dict, index: int):
    if not sensor.get("id"):
        raise ValueError(
            f"Sensor #{index} ({sensor.get('name', '?')}): "
            f"'id' is required and must never change."
        )
    model = sensor.get("model")
    if not model:
        raise ValueError(f"Sensor #{index}: 'model' is required.")
    if model not in VALID_MODELS:
        raise ValueError(
            f"Sensor #{index}: unknown model '{model}'. "
            f"Valid models: {sorted(VALID_MODELS)}"
        )
    if not sensor.get("device_id"):
        raise ValueError(f"Sensor #{index}: 'device_id' is required.")


def check_duplicate_ids(sensors: list[dict]):
    seen = {}
    for i, sensor in enumerate(sensors, start=1):
        sid = sensor.get("id")
        if sid in seen:
            raise ValueError(
                f"Duplicate id '{sid}' found at sensor #{i} "
                f"({sensor.get('name', '?')}) and sensor #{seen[sid]}."
            )
        seen[sid] = i


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Publish Acurite MQTT discovery messages")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--remove", action="store_true",
                        help="Remove all sensors instead of creating")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
    except FileNotFoundError:
        print(f"ERROR: Config file '{args.config}' not found.")
        sys.exit(1)

    mqtt_cfg         = cfg.get("mqtt", {})
    global_base_path = cfg.get("base_path", "rtl_433")
    discovery_prefix = cfg.get("discovery_prefix", "homeassistant")
    sensors          = cfg.get("sensors", [])

    if not sensors:
        print("No sensors defined in config. Nothing to do.")
        sys.exit(0)

    for i, sensor in enumerate(sensors, start=1):
        validate_sensor(sensor, i)
    check_duplicate_ids(sensors)

    action = "remove" if args.remove else "create"
    print(f"Action : {action.upper()}")
    print(f"Sensors: {len(sensors)}")
    print()

    client = connect_mqtt(mqtt_cfg)
    client.loop_start()

    try:
        for sensor in sensors:
            stable_id = str(sensor["id"])
            model     = sensor["model"]
            device_id = str(sensor["device_id"])
            name      = sensor.get("name", f"Acurite {stable_id}")
            base_path = sensor.get("base_path", global_base_path)
            area      = sensor.get("area")

            print(f"\n{'─'*60}")
            print(f"  Sensor : {name}  |  Model: {model}")
            print(f"  ID     : {stable_id} (stable)  |  device_id: {device_id} (radio)")
            if area:
                print(f"  Area   : {area}")
            print(f"{'─'*60}")

            if action == "remove":
                msgs = removal_topics(stable_id, discovery_prefix)
            else:
                msgs = build_payloads(stable_id, model, device_id,
                                      name, base_path, discovery_prefix, area)

            publish_messages(client, msgs)

    finally:
        client.loop_stop()
        client.disconnect()

    print(f"\nDone. {len(sensors)} sensor(s) processed.")


if __name__ == "__main__":
    main()

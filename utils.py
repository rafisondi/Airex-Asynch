
import json
import numpy as np

from hat_hum1001.phidget import PhidgetHum1001Sensor
from hat_tmp1000 import PhidgetConfig
from hat_tmp1000.phidget import PhidgetTmp1000Sensor
from hat.sensor import Measurement
from hat_proges import ProgesConfig, ProgesSensorBox, ProgesMeasurement


def get_sensor_list(config_dict):
    sensor_list = []
    for config in config_dict.get("hum1001", []):
        hum = PhidgetHum1001Sensor(
            config=PhidgetConfig(
                sensor_id=config.get("sensor_id"),
                frequency=config.get("frequency"),
                host=config.get("host"),
                hub_port=config.get("hub_port"),
                serial_number=config.get("serial_number"),
                measurement_type=config.get("measurement_type"),
            )
        )
        sensor_list.append(hum)

    for config in config_dict.get("tmp1000", []):
        tmp = PhidgetTmp1000Sensor(
            config=PhidgetConfig(
                sensor_id=config.get("sensor_id"),
                frequency=config.get("frequency"),
                host=config.get("host"),
                hub_port=config.get("hub_port"),
                serial_number=config.get("serial_number"),
                measurement_type=config.get("measurement_type"),
            )
        )
        
    for config in config_dict.get("progres", []):
        tmp = ProgesSensorBox.create_from_config(
            ProgesConfig(
                sensor_id=config.get("sensor_id"),
                frequency=config.get("frequency"),
                host=config.get("host"),
                measurement_type=config.get("measurement_type")
            )
        )
        sensor_list.append(tmp)
    return sensor_list

def get_config_dict():
    config_dict = {}
    with open("./tmp1000_config.json") as config_file:
        config_dict["tmp1000"] = json.load(config_file)

    with open("./pre1000_config.json") as config_file:
        config_dict["pre1000"] = json.load(config_file)

    with open("./hum1001_config.json") as config_file:
        config_dict["hum1001"] = json.load(config_file)
    
    with open("./progres_config.json") as config_file:
        config_dict["progres"] = json.load(config_file)
    return config_dict



def load_sensor_ids_to_dict(json_file_path) -> dict:
    with open(json_file_path, 'r') as file:
        config = json.load(file)
    
    sensor_ids = config.get("sensors", [])
    measurements_dict = {sensor_id: [] for sensor_id in sensor_ids}
    return measurements_dict



def extract_progres_sensor_measurement( measurement_list: list[ProgesMeasurement] ) -> dict[str, list[tuple[str, float]]]:

    measurements_dict: dict[str, list[tuple[str, float]]] = {}
    for measurement in measurement_list:
        sensor_id = measurement.sensor_id
        timestamp = measurement.timestamp
        temperature = measurement.temp
        if sensor_id not in measurements_dict:
            measurements_dict[sensor_id] = []
        measurements_dict[sensor_id].append((timestamp, temperature))

    return measurements_dict

def average_sensor_measurement(measurements : list[Measurement]) -> float:
    vals = []
    for m in measurements:
        vals.append(m.value)
    avg = np.mean(np.array(vals))
    return avg

def average_progres_sensor_measurement(id: str , measurements : list[tuple[str, float]]) -> tuple[str , float]:
    vals = []
    for m in measurements:
        vals.append(m[1])
    avg = np.mean(np.array(vals))
    return id, avg
    
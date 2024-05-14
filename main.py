import asyncio
import datetime
import json
from dataclasses import dataclass

import numpy as np
from hat_hum1001.phidget import PhidgetHum1001Sensor
from hat_tmp1000 import PhidgetConfig
from hat_tmp1000.phidget import PhidgetTmp1000Sensor

MAX_CONSECUTIVE_FAILURES = 3
NB_MEASUREMENTS_PER_SAMPLE = 3


async def sample_sensor(sensor):
    try:
        sensor._connect()
        measurements = []
        for i in range(NB_MEASUREMENTS_PER_SAMPLE):
            try:
                new_measurement = sensor._sample()  # single sample from currently connected sensor
                measurements.append(new_measurement.value)
                await asyncio.sleep(1 / sensor.config.frequency)
            except Exception as e:
                print(f"Error sampling from sensor {sensor.sensor_id}: {e}")
                sensor._disconnect()
                sensor._connect()
        sensor._disconnect()  # Current measurement of single sensor has been finished
        measurement = np.mean(np.array(measurements))  # Averaged measurement

    except Exception as e:
        print(f"Could not connect to sensor {sensor.sensor_id}: {e}")
        measurement = np.NaN
    return measurement


@dataclass
class LoggerConfig:
    sensors_sampling_time: float


class Logger:
    def __init__(self, config: LoggerConfig):
        self.sensors_sampling_time = config.sensors_sampling_time
        self.sensor_list = []
        self.sensor_data = {}
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    def set_sensor_list(self):
        config_dict = get_config_dict()
        self.sensor_list = get_sensor_list(config_dict)

    async def start_logging(self):
        await self.log_sensors_data()

    async def log_sensors_data(self):
        self.latest_sensor_data = {sensor: float for sensor in self.sensor_list}
        self.latest_sensor_data["time"] = None
        self.already_tried_reconnect = {sensor: 0 for sensor in self.sensor_list}

        while True:
            tasks = [sample_sensor(sensor) for sensor in self.sensor_list]
            results = await asyncio.gather(*tasks)

            for sensor, measurement in zip(self.sensor_list, results):
                self.latest_sensor_data[sensor] = measurement

            self.sensor_data["time"] = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            print(self.latest_sensor_data)
            await asyncio.sleep(self.sensors_sampling_time)


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
        sensor_list.append(tmp)
    return sensor_list


def get_config_dict():
    config_dict = {}
    with open("./tmp1000_config.json") as config_file:
        config_dict["tmp1000"] = json.load(config_file)

    with open("./lux1000.json") as config_file:
        config_dict["lux1000"] = json.load(config_file)

    with open("./pre1000_config.json") as config_file:
        config_dict["pre1000"] = json.load(config_file)

    with open("./hum1001_config.json") as config_file:
        config_dict["hum1001"] = json.load(config_file)
    return config_dict


def get_logger_config(config_file_path):
    with open(config_file_path) as config_file:
        config = json.load(config_file)
    print("Logger config loaded successfully.")
    logconfig = LoggerConfig(sensors_sampling_time=config.get("sensors_sampling_time", 0.0))
    return logconfig


if __name__ == "__main__":
    config_file_path = "./logger_config.json"
    print("Loading logger config...")
    config = get_logger_config(config_file_path)

    Log = Logger(config)
    print("Setting sensor list...")
    Log.set_sensor_list()
    asyncio.run(Log.start_logging())

import asyncio
import csv
import datetime
import json
import shutil
import time
from dataclasses import dataclass

import numpy as np
from hat_hum1001.phidget import PhidgetHum1001Sensor
from hat_tmp1000 import PhidgetConfig
from hat_tmp1000.phidget import PhidgetTmp1000Sensor

MAX_CONSECUTIVE_FAILURES = 3
NB_MEASUREMENTS_PER_SAMPLE = 3


@dataclass
class LoggerConfig:
    sensors_sampling_time: float
    sensors_csv_file_period: int

    credentials_file: str
    local_folder_path: str
    drive_folder_id: str
    upload_to_drive_period: float


class Logger:
    def __init__(self, config: LoggerConfig):
        self.sensors_sampling_time = config.sensors_sampling_time
        self.sensors_csv_file_period = config.sensors_csv_file_period

        self.credentials_file = config.credentials_file
        self.local_folder_path = config.local_folder_path
        self.drive_folder_id = config.drive_folder_id
        self.upload_to_drive_period = config.upload_to_drive_period

        self.sensor_list = []
        self.connected_sensors = []
        self.sensor_data = {}

        self.output_sensors_file = None

    def set_sensor_list(self):
        config_dict = get_config_dict()
        self.sensor_list = get_sensor_list(config_dict)

    def establish_sensor_connection(self):
        count = 0
        idx = []
        for sensor in self.sensor_list:
            try:
                sensor._connect()
                idx.append(count)
            except Exception as e:
                print(f"Could not connect to sensor {sensor.sensor_id}: {e}")
            count += 1
        self.connected_sensors = [self.sensor_list[i] for i in idx]
        print(len(self.connected_sensors), "/", len(self.sensor_list), " sensors successfully connected.")
        if len(self.connected_sensors) < len(self.sensor_list):
            print(" Not found sensors are going to return NaN from here on.")

    def disconnect_sensor_connection(self):
        for sensor in self.sensor_list:
            try:
                sensor._disconnect()
            except:
                continue
        print("Sensors disconnected ")

    def sample_sensors(self):
        for sensor in self.connected_sensors:
            try:
                print(sensor._sample(), f" sampled from: {sensor.sensor_id}")
            except Exception as e:
                print(f"Error sampling from sensor {sensor.sensor_id}: {e}")

    async def run_logger(self):
        batch = asyncio.gather(self.new_sensors_data_file(), self.log_sensors_data())
        result_file, result_log_sensors = await batch

    async def sample_sensor(self, sensor):
        if sensor not in self.connected_sensors:
            return np.NaN
        try:
            measurements = []
            for i in range(NB_MEASUREMENTS_PER_SAMPLE):
                measurements.append(sensor._sample().value)
                await asyncio.sleep(1 / sensor.config.frequency)
            sample = np.mean(measurements)
        except Exception as e:
            print(f"Error sampling from sensor {sensor.sensor_id}: {e}")
            print("Trying to reconnect from sensor")
            start_time = time.time()
            try:
                sensor._connect()
            except Exception as e:
                print(f"Could not connect to sensor {sensor.sensor_id}: {e}")
            end_time = time.time()
            diff_time = end_time - start_time
            print(f"Reconnection attempt took {diff_time}")
            sample = np.NaN
        return sample

    async def new_sensors_data_file(self):
        while True:
            if self.output_sensors_file != None:
                shutil.copy(self.output_sensors_file, self.local_folder_path)
            try:
                print("Trying to upload data...")
            except:
                print("Could not upload files to Google Drive, no Internet Connection.")

            current_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.output_sensors_file = f"./csv/sensor_data_{current_datetime}.csv"
            self.create_sensors_data_csv()
            print(f" Creating new CSV Placeholder  at {current_datetime}")
            await asyncio.sleep(self.sensors_csv_file_period)  # 3600 for one hour

    async def log_sensors_data(self):
        self.latest_sensor_data = {sensor: float for sensor in self.sensor_list}
        self.latest_sensor_data["time"] = None
        self.already_tried_reconnect = {sensor: 0 for sensor in self.sensor_list}

        while True:
            # Wait for sampling of all sensors
            tasks = [self.sample_sensor(sensor) for sensor in self.sensor_list]
            results = await asyncio.gather(*tasks)

            # Gather all results in a single dict {sensor: val}
            for sensor, measurement in zip(self.sensor_list, results):
                self.latest_sensor_data[sensor] = measurement

            self.sensor_data["time"] = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.save_new_sensors_data()
            print(self.latest_sensor_data)
            await asyncio.sleep(self.sensors_sampling_time)

    def save_new_sensors_data(self):
        if self.output_sensors_file is not None:
            with open(self.output_sensors_file, "a", newline="") as csv_file:
                csv_writer = csv.writer(csv_file)
                row_data = [self.sensor_data["time"]] + [self.latest_sensor_data[sensor] for sensor in self.sensor_list]
                csv_writer.writerow(row_data)
                print("New measurements saved at " + self.sensor_data["time"])

    def create_sensors_data_csv(self):
        with open(self.output_sensors_file, "w", newline="") as csv_file:
            csv_writer = csv.writer(csv_file)
            # Create a list of column headers based on sensor_id
            header = ["Timestamp"] + [
                f"{sensor.config.measurement_type} from {sensor.config.sensor_id}" for sensor in self.sensor_list
            ]
            csv_writer.writerow(header)
            # csv_file.close()


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

    with open("./pre1000_config.json") as config_file:
        config_dict["pre1000"] = json.load(config_file)

    with open("./hum1001_config.json") as config_file:
        config_dict["hum1001"] = json.load(config_file)
    return config_dict


def get_logger_config(config_file_path):
    with open(config_file_path) as config_file:
        config = json.load(config_file)
    print("Logger config loaded successfully.")
    logconfig = LoggerConfig(
        sensors_sampling_time=config["sensors_sampling_time"],
        sensors_csv_file_period=config["sensors_csv_file_period"],
        credentials_file=config["credentials_file"],
        local_folder_path=config["local_folder_path"],
        drive_folder_id=config["drive_folder_id"],
        upload_to_drive_period=config["upload_to_drive_period"],
    )
    return logconfig


if __name__ == "__main__":
    config_file_path = "./logger_config.json"
    print("Loading logger config...")
    config = get_logger_config(config_file_path)

    Log = Logger(config)
    print("Setting sensor list...")
    Log.set_sensor_list()

    print("Establish sensor connections...")
    Log.establish_sensor_connection()

    print(" Single test measurement from each connected sensor: ")
    Log.sample_sensors()

    print("---------- Start Logging ----------")
    asyncio.run(Log.run_logger())

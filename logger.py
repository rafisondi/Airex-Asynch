import shutil
import time
import csv
import datetime
import asyncio
from dataclasses import dataclass
import numpy as np
from utils import get_sensor_list , get_config_dict , extract_progres_sensor_measurement
from hat_proges import ProgesConfig, ProgesSensorBox


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
                sensor.connect()
                print( f" Sensor {sensor} connected" )
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
                #print(sensor.sample(), f" sampled from: {sensor.sensor_id}")
                sensor.measure_for_count(1)
                m = sensor.list_measurements()    
                print(f'{m = }')
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
            
            if isinstance(sensor.config, ProgesConfig):
                # TODO: Replace '2' value with config variable
                sensor.measure_for_count(NB_MEASUREMENTS_PER_SAMPLE * 2) # Two channels in Box used
                progres_list = sensor.list_measurements()      
                measurements_dict = extract_progres_sensor_measurement(progres_list)
            else:
                sensor.measure_for_count(NB_MEASUREMENTS_PER_SAMPLE)
                m = sensor.list_measurements()   
                measurements.append(m[0].value)
            sensor.stop_measuring()
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
            header = ["Timestamp"]
            for sensor in self.sensor_list: 
                if not isinstance(sensor.config, ProgesConfig):
                    header + [
                        f"{sensor.config.measurement_type} from {sensor.config.sensor_id}" 
                    ]
                else: # Workaround to missing .config.measurement_type of progres
                    header + [
                        f"Alu-Profile Temperature measurement from {sensor.config.sensor_id}" 
                    ]
            csv_writer.writerow(header)
            # csv_file.close()
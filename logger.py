import shutil
import time
import csv
import datetime
import asyncio
from dataclasses import dataclass
import numpy as np
import utils

from hat.sensor import SensorConfig, Measurement
from hat_proges import ProgesConfig, ProgesMeasurement


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
        self.sensor_id_list = []
        self.connected_sensors = []
        self.sensor_data = {}

        self.output_sensors_file = None

    def set_sensor_list(self):
        config_dict =  utils.get_config_dict()
        self.sensor_list =  utils.get_sensor_list(config_dict)
        self.sensor_id_list = [sensor.sensor_id for sensor in self.sensor_list]
        

    def establish_sensor_connection(self):
        count = 0
        idx = []
        for sensor in self.sensor_list:
            try:
                sensor._connect()
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
                sensor.disconnect()
            except:
                continue
        print("Sensors disconnected ")

    def single_sample_all_sensors(self):
        for sensor in self.connected_sensors:
            try:
                
                if (sensor.sensor_id == 'progres_box'):
                    sensor.measure_for_count(2) # 2 channels in Box used
                    # TODO Fix the following hack
                    # Include the progres sensor ID's attached to the box
                    sensor_measurements_list = sensor.list_measurements()  
                    progres_id_1 = sensor_measurements_list[0].sensor_id
                    progres_id_2 = sensor_measurements_list[1].sensor_id
                    progres_box_idx = self.sensor_id_list.index('progres_box')
                    self.sensor_id_list[progres_box_idx:progres_box_idx+1] = progres_id_1, progres_id_2
                else:
                    print(sensor._sample(), f" sampled from: {sensor.sensor_id}")

            except Exception as e:
                print(f"Error sampling from sensor {sensor.sensor_id}: {e}")

    async def run_logger(self):
        batch = asyncio.gather(self.new_sensors_data_file(), self.log_sensors_data())
        result_file, result_log_sensors = await batch

    async def sample_sensor(self, sensor:SensorConfig) -> list[Measurement] :
        if sensor not in self.connected_sensors:
            return np.NaN
        
        try:
            if isinstance(sensor.config, ProgesConfig):
                # TODO: Replace '2' value with config variable
                sensor.measure_for_count(NB_MEASUREMENTS_PER_SAMPLE * 2) # Two channels in Box used
                sensor_measurements_list = sensor.list_measurements()  
            else:
                sensor_measurements_list = [sensor._sample() for i in range(NB_MEASUREMENTS_PER_SAMPLE)]
            sensor.stop_measuring()
            
            
        except Exception as e:
            print(f"[ERROR] {sensor.sensor_id}: {e}")
            print("Trying to reconnect to sensor")
            start_time = time.time()
            try:
                sensor._connect()
            except Exception as e:
                print(f"Could not connect to sensor {sensor.sensor_id}: {e}")
            end_time = time.time()
            diff_time = end_time - start_time
            print(f"Reconnection attempt took {diff_time}")
            sensor_measurements_list = [sensor.sensor_id]
            
        return sensor_measurements_list

    async def log_sensors_data(self):
        self.latest_sensor_data = {} # {sensor: float for sensor in self.sensor_list}
        self.latest_sensor_data["time"] = None
        self.already_tried_reconnect = {sensor: 0 for sensor in self.sensor_list}

        while True:
            # Wait for sampling of all sensors
            tasks = [self.sample_sensor(sensor) for sensor in self.sensor_list]
            results = await asyncio.gather(*tasks)
            
            # Preprocess 
            for hat_measurement_list in results:
                if isinstance(hat_measurement_list[0], str):
                    self.latest_sensor_data[hat_measurement_list[0]] = np.NaN
                
                elif isinstance(hat_measurement_list[0], ProgesMeasurement):
                    progres_sensor_dict = utils.extract_progres_sensor_measurement(hat_measurement_list)                    
                    for sensor_id , measurement_tuple_list in progres_sensor_dict.items():
                        id, averaged_measurement = utils.average_progres_sensor_measurement(sensor_id, measurement_tuple_list)
                        self.latest_sensor_data[id] = averaged_measurement
                else:
                    averaged_measurement =  utils.average_sensor_measurement(hat_measurement_list)
                    self.latest_sensor_data[hat_measurement_list[0].sensor_id] = averaged_measurement

            self.latest_sensor_data["time"] = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.save_new_sensors_data()

            await asyncio.sleep(self.sensors_sampling_time)

    def save_new_sensors_data(self):
        if self.output_sensors_file is not None:
            with open(self.output_sensors_file, "a", newline="") as csv_file:
                csv_writer = csv.writer(csv_file)
                row_data = [self.latest_sensor_data["time"]] + [self.latest_sensor_data[id] for id in self.sensor_id_list]
                csv_writer.writerow(row_data)
                
    async def new_sensors_data_file(self):
        while True:
            if self.output_sensors_file != None:
                shutil.copy(self.output_sensors_file, self.local_folder_path)
            try:
                print("Uploading CSV to Drive, new local file will be created.")
            except:
                print("Could not upload files to Google Drive, no Internet Connection.")
            current_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.output_sensors_file = f"./csv/sensor_data_{current_datetime}.csv"
            self.create_sensors_data_csv()
            await asyncio.sleep(self.sensors_csv_file_period)  # 3600 for one hour

    def create_sensors_data_csv(self):
        print("------- Preparing CSV Filesave --------")
        with open(self.output_sensors_file, "w", newline="") as csv_file:
            csv_writer = csv.writer(csv_file)
            # Create a list of column headers based on sensor_id
            header = ["Timestamp"]
            for sensor in self.sensor_list: 
                if sensor.sensor_id != 'progres_box':
                    header = header + [
                        f"{sensor.config.measurement_type} from {sensor.config.sensor_id}" 
                    ]
                else: 
                    # TODO: Fix this hardcoded mess
                    # Workaround to missing .config.measurement_type of progres_hat
                    # Idx remains set after initialization of sensor_id_list
                    header = header + [
                        f"Alu Temperature: ID:DB00000E81526628" 
                    ]
                    header = header + [
                        f"Alu Temperature: ID:9300000E80967E28" 
                    ]
            csv_writer.writerow(header)

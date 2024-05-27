import asyncio
import json
from logger import Logger , LoggerConfig

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
    print( "---------- Setting sensor list... ----------")
    Log.set_sensor_list()

    print("---------- Establish sensor connections... ----------")
    Log.establish_sensor_connection()

    print(" ---------- Single test measurement from each connected sensor: ---------- ")
    Log.single_sample_all_sensors()

    print("---------- Start Logging ----------")
    asyncio.run(Log.run_logger())

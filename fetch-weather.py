import argparse
from datetime import datetime
from enum import StrEnum
from pathlib import Path
import pickle
# Above is Standard Library
# Below is custom/third-party
from pendulum import now, parse
import requests
import requests_cache
from retry_requests import retry

class C(StrEnum):
	APPARENT_TEMPERATURE = "apparent_temperature"
	CLOUD_COVER = "cloud_cover"
	DATE_FORMAT = "%Y-%m-%dT%H:%M"
	DEW_POINT = "dew_point"
	ELEVATION = "elevation"
	END_DATE = "end_date"
	END_HOUR = "end_hour"
	FAHRENHEIT = "fahrenheit"
	FORECAST_HOURS = "forecast_hours"
	HOURLY = "hourly"
	LATITUDE = "latitude"
	LONGITUDE = "longitude"
	MPH = "mph"
	OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
	PRECIPITATION = "precipitation"
	START_DATE = "start_date"
	START_HOUR = "start_hour"
	TEMPERATURE = "temperature_2m"
	TEMPERATURE_UNIT = "temperature_unit"
	TIME = "time"
	# TIME_ZONE_PREFIX = "America/"
	WIND_GUSTS_10M = "wind_gusts_10m"
	WIND_SPEED_10M = "wind_speed_10m"
	WIND_SPEED_UNIT = "wind_speed_unit"

CACHE_FILE = Path.home() / "weather.pickle"
LOCAL_TIME_ZONE = now().timezone
DEFAULT_START_TIME = now().add(hours=1).set(minute=0, second=0, microsecond=0)
METER_TO_FEET_RATIO = 3.28084

parser = argparse.ArgumentParser(description='Provide weather data.')
parser.add_argument('--latitude', metavar="DEGREES OF LATITUDE", type=int, help="North of equator is positive.", default=39.9)
parser.add_argument('--longitude', metavar="DEGREES OF LONGITUDE", type=int, help="West of Prime Meridian is negative.", default=-105)
parser.add_argument('--start-time', metavar="YYYY-MM-DD", help=f"Ignore forecast before this time. Default is {DEFAULT_START_TIME.format("YYYY-MM-DD HH:00 zz")}.", default=DEFAULT_START_TIME)
logging_group = parser.add_mutually_exclusive_group()
logging_group.add_argument('--verbose', action='store_true')
logging_group.add_argument('--terse', action='store_true')
error_list = list()
args = parser.parse_args()
latitude = args.latitude
longitude = args.longitude
if abs(latitude) >= 90:
	error_list.append("Latitude must be between -90 and 90")
if abs(longitude) >= 180:
	error_list.append("Longitude must be between -180 and 180")
start_time = args.start_time
try:
	if not(isinstance(args.start_time, datetime)):
		start_time = parse(args.start_time)
except ValueError:
	error_list.append(f"Invalid start time '{args.start_time}'")
if error_list:
	raise argparse.ArgumentTypeError(", ".join(error_list))

# cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
# retry_session = retry(cache_session, retries=5, backoff_factor = 0.2)

# Make sure all required weather variables are listed here
# The order of variables in hourly or daily is important to assign them correctly below
requested_metric_list = (
	C.TEMPERATURE,
	C.DEW_POINT,
	C.PRECIPITATION,
	C.WIND_SPEED_10M,
	C.WIND_GUSTS_10M,
	C.CLOUD_COVER,
)
params = {
	C.LATITUDE: latitude,
	C.LONGITUDE: longitude,
	C.HOURLY: requested_metric_list,
	C.TEMPERATURE_UNIT: C.FAHRENHEIT,
	C.WIND_SPEED_UNIT: C.MPH,
}

if CACHE_FILE.exists():
	data_dict = pickle.load(open(CACHE_FILE, "rb"))
else:
	response = requests.get(C.OPEN_METEO_URL, params=params)
	data_dict = response.json()
	with open(CACHE_FILE, "wb") as f:
		pickle.dump(data_dict, f)

elevation_in_feet = 100 * round(data_dict[C.ELEVATION] * METER_TO_FEET_RATIO / 100)
print(f"Elevation: {elevation_in_feet:,} feet")

# Based on requested/default start time determine which of the first N elements of each return list to throw away
for i, stamp in enumerate(data_dict[C.HOURLY][C.TIME]):
	# print(i, parse(stamp))
	if parse(stamp).set(tz=LOCAL_TIME_ZONE) >= start_time:
		break

received_time_series = list()
for stamp_str in data_dict[C.HOURLY][C.TIME][i:]:
	local_stamp = parse(stamp_str).set(tz=LOCAL_TIME_ZONE)
	received_time_series.append(local_stamp.format("ddd hh A"))

for key, received_metric in data_dict[C.HOURLY].items():
	if key == C.TIME:
		continue
	print(key)
	# print(received_metric[i:])
	# print(len(received_metric[i:]))
	time_metric_pair_list = zip(received_time_series, received_metric[i:])
	for item in time_metric_pair_list:
		print(item)


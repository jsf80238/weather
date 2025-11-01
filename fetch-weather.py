import argparse
import enum
# Above is Standard Library
# Below is custom/third-party
import pendulum
import requests
import requests_cache
from retry_requests import retry

class C(enum.Enum):
	NEW_YORK = "New_York"
	CHICAGO = "Chicago"
	DENVER = "Denver"
	LOS_ANGELES = "Los_Angeles"
	OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
	LATITUDE = "latitude"
	LONGITUDE = "longitude"
	TEMPERATURE = "temperature_2m"
	HOURLY = "hourly"
	ELEVATION = "elevation"
	DATE_FORMAT = "%Y-%m-%dT%H:%M"

parser = argparse.ArgumentParser(description='Provide weather data.')
parser.add_argument('--latitude', metavar="DEGREES OF LATITUDE", help="North of equator is positive.", default=39.9)
parser.add_argument('--longitude', metavar="DEGREES OF LONGITUDE", help="West of Prime Meridian is negative.", default=-105)
parser.add_argument('--start-time', metavar="YYYY-MM-DD HH[:00:00]", help="Default is the next hour in the timezone specified by --start-time-city.")
parser.add_argument('--start-time-city', metavar="NAME", help="Time zone for results and optional --start-time.", choices=(C.NEW_YORK.value, C.CHICAGO.value, C.DENVER.value, C.LOS_ANGELES.value), default=C.DENVER.value)
logging_group = parser.add_mutually_exclusive_group()
logging_group.add_argument('--verbose', action='store_true')
logging_group.add_argument('--terse', action='store_true')
args = parser.parse_args()
latitude = args.latitude
longitude = args.longitude

cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries=5, backoff_factor = 0.2)

# Make sure all required weather variables are listed here
# The order of variables in hourly or daily is important to assign them correctly below
url = "https://api.open-meteo.com/v1/forecast"
params = {
	C.LATITUDE.value: latitude,
	C.LONGITUDE.value: longitude,
	C.HOURLY.value: C.TEMPERATURE.value,
}

response = requests.get(C.OPEN_METEO_URL.value, params=params)
data_dict = response.json()

print(f"Elevation: {data_dict["elevation"]} meters")

for key, value in data_dict[C.HOURLY.value].items():
	print(type(key))
	print(key)
	print(type(value))
	print(value)
	print()


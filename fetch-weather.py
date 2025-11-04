import argparse
from datetime import datetime
from enum import StrEnum
from itertools import accumulate
from pathlib import Path
import pickle
from subprocess import run
from tempfile import NamedTemporaryFile
# Above is Standard Library
# Below is custom/third-party
import matplotlib.pyplot as plt
import numpy as np
from pendulum import now, parse
import requests
import requests_cache
from retry_requests import retry

class C(StrEnum):
	ACCUMULATED_PRECIPITATION = "accumulated_precipitation"  # not fetched from the API
	APPARENT_TEMPERATURE = "apparent_temperature"
	CLOUD_COVER = "cloud_cover"
	DATE_FORMAT = "%Y-%m-%dT%H:%M"
	DEW_POINT = "dew_point_2m"
	ELEVATION = "elevation"
	FAHRENHEIT = "fahrenheit"
	FORECAST_HOURS = "forecast_hours"
	HOURLY = "hourly"
	IMAGE_VIEW_EXECUTABLE = "/usr/bin/okular"
	LATITUDE = "latitude"
	LONGITUDE = "longitude"
	MPH = "mph"
	OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
	PRECIPITATION = "precipitation"
	TEMPERATURE = "temperature_2m"
	TEMPERATURE_UNIT = "temperature_unit"
	TIME = "time"
	TITLE = "title"
	UNIT_OF_MEASUREMENT = "unit_of_measurement"
	WIND_GUSTS_10M = "wind_gusts_10m"
	WIND_SPEED_10M = "wind_speed_10m"
	WIND_SPEED_UNIT = "wind_speed_unit"
	X_VALUES = "x_values"
	Y_VALUES = "y_values"

CACHE_FILE = Path.home() / "weather.pickle"
LOCAL_TIME_ZONE = now().timezone
DEFAULT_START_TIME = now().add(hours=1).set(minute=0, second=0, microsecond=0)
METER_TO_FEET_RATIO = 3.28084
REQUESTED_METRIC_LIST = (
	C.TEMPERATURE,
	C.DEW_POINT,
	C.PRECIPITATION,
	C.WIND_SPEED_10M,
	C.WIND_GUSTS_10M,
	C.CLOUD_COVER,
)
REPORT_ORDER_LIST = (
	C.TEMPERATURE,
	C.DEW_POINT,
	C.PRECIPITATION,
	C.ACCUMULATED_PRECIPITATION,
	C.CLOUD_COVER,
	C.WIND_SPEED_10M,
	C.WIND_GUSTS_10M,
)


def create_multi_line_charts(
		main_title: str,
		datasets: list,
) -> plt.Figure:
	"""
    Generates a single PNG image containing multiple line graphs, one for each
    dictionary in the input list. The graphs are stacked vertically.

    Each dictionary must contain:
    - 'x_values': list of string labels.
    - 'y_values': list of numeric measurements.
    - 'title': string title for the subplot.
    - 'unit_of_measurement': string

    Args:
    	main_title (str): printed at top
        datasets (list[dict]): A list where each dictionary defines a dataset and its title.

    Returns:
    	plt.Figure: A figure containing the PNG image.
    """
	if not datasets:
		raise ValueError("No datasets provided.")
	num_datasets = len(datasets)

	# 1. Create the figure and a set of subplots (stacked vertically)
	# The figure height scales with the number of datasets to ensure readability.
	fig, axes = plt.subplots(
		num_datasets, 1,
		figsize=(10, 4 * num_datasets),
		sharex=False  # Do not share x-axis labels across plots by default
	)

	# Ensure axes is iterable even if only one subplot exists
	if num_datasets == 1:
		axes = [axes]

	# 2. Iterate through the datasets and plot each one
	for i, data in enumerate(datasets):
		ax = axes[i]

		try:
			x_labels = data[C.X_VALUES]
			y_measurements = data[C.Y_VALUES]
			title = data[C.TITLE]
			unit_of_measurement = data[C.UNIT_OF_MEASUREMENT]
		except KeyError as e:
			print(f"Error: Dataset {i + 1} is missing a required key: {e}")
			continue

		if len(x_labels) != len(y_measurements):
			print(f"Warning: Data lengths mismatch for '{title}'. Skipping this plot.")
			continue

		# Line plots typically use numeric axes. We plot against the index (0, 1, 2...)
		# and then set the tick labels to the strings.
		x_indices = np.arange(len(x_labels))

		# Plot the line graph
		ax.plot(x_indices, y_measurements, marker='o', linestyle='-', color='indigo', linewidth=2)

		# Apply title and labels
		improved_title = " ".join([x.capitalize() for x in title.lower().split("_")])
		ax.set_title(improved_title, fontsize=14)
		ax.set_ylabel(unit_of_measurement, fontsize=10)

		# Set the string labels on the x-axis
		CAN_COMFORTABLY_FIT = 36
		step_size = max(1, int(len(x_indices) / CAN_COMFORTABLY_FIT))
		ax.set_xticks(x_indices[::step_size])
		ax.set_xticklabels(x_labels[::step_size], rotation=45, ha='right', fontsize=9)

		ax.grid(axis='y', linestyle=':', alpha=0.6)

	# 3. Add a main title to the overall figure
	fig.suptitle(main_title, fontsize=18, fontweight='bold')

	# 4. Final layout adjustments
	plt.tight_layout(rect=[0, 0, 1, 0.95])  # Adjust space for suptitle
	fig.subplots_adjust(top=0.92)

	return plt


def get_units_of_measurement(measurement_name: str) -> str:
	match measurement_name:
		case C.TEMPERATURE | C.DEW_POINT:
			return "°F"
		case C.WIND_GUSTS_10M | C.WIND_SPEED_10M:
			return "mph"
		case C.PRECIPITATION | C.ACCUMULATED_PRECIPITATION:
			return "mm"
		case C.CLOUD_COVER:
			return "%"
		case _:
			return "Unknown"


parser = argparse.ArgumentParser(description='Provide weather data.')
parser.add_argument('coordinates', metavar="LATITUDE,LONGITUDE", type=str, help="North of equator is positive, west of Prime Meridian is negative.")
parser.add_argument('--start-time', metavar="YYYY-MM-DD", help=f"Ignore forecast before this time. Default is {DEFAULT_START_TIME.format("YYYY-MM-DD HH:00 zz")}.", default=DEFAULT_START_TIME)
parser.add_argument('--hours-limit', metavar="NUMBER", type=int, help="Don't go beyond this number of hours in the future.")
logging_group = parser.add_mutually_exclusive_group()
logging_group.add_argument('--verbose', action='store_true')
logging_group.add_argument('--terse', action='store_true')
error_list = list()
args = parser.parse_args()
coordinates = args.coordinates
try:
	# Northwest Alaska: 69, -163
	# East Maine: 44, -67
	# Hawaii: 19, -155
	latitude, longitude = coordinates.replace(" ", "").split(",")
	latitude = float(latitude)
	longitude = float(longitude)
	if latitude > 69 or latitude < 19:
		error_list.append("Latitude must be between 19 and 69")
	if longitude < -163 or longitude > -67:
		error_list.append("Longitude must be between -67 and -163")
except ValueError:
	error_list.append(f"Invalid coordinates: {coordinates}")
start_time = args.start_time
hours_limit = args.hours_limit
try:
	if not(isinstance(args.start_time, datetime)):
		start_time = parse(args.start_time)
except ValueError:
	error_list.append(f"Invalid start time '{args.start_time}'")
if error_list:
	raise argparse.ArgumentTypeError(", ".join(error_list))

# cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
# retry_session = retry(cache_session, retries=5, backoff_factor = 0.2)
api_params = {
	C.LATITUDE: latitude,
	C.LONGITUDE: longitude,
	C.HOURLY: REQUESTED_METRIC_LIST,
	C.TEMPERATURE_UNIT: C.FAHRENHEIT,
	C.WIND_SPEED_UNIT: C.MPH,
}

if False and CACHE_FILE.exists():
	data_dict = pickle.load(open(CACHE_FILE, "rb"))
else:
	response = requests.get(C.OPEN_METEO_URL, params=api_params)
	data_dict = response.json()
	with open(CACHE_FILE, "wb") as f:
		pickle.dump(data_dict, f)

elevation_in_feet = 100 * round(data_dict[C.ELEVATION] * METER_TO_FEET_RATIO / 100)

# Based on requested/default start time determine which of the first N elements of each return list to throw away
i = 0
for i, stamp in enumerate(data_dict[C.HOURLY][C.TIME]):
	# print(i, parse(stamp))
	if parse(stamp).set(tz=LOCAL_TIME_ZONE) >= start_time:
		break

received_time_series = list()
if hours_limit:
	last = min(i + hours_limit, len(data_dict[C.HOURLY][C.TIME]))
else:
	last = len(data_dict[C.HOURLY][C.TIME])
for stamp_str in data_dict[C.HOURLY][C.TIME][i:last]:
	local_stamp = parse(stamp_str).set(tz=LOCAL_TIME_ZONE)
	received_time_series.append(local_stamp.format("ddd hh A"))

# Special: accumulated precipitation
y_values = list(accumulate(data_dict[C.HOURLY][C.PRECIPITATION][i:last]))
data_dict[C.HOURLY][C.ACCUMULATED_PRECIPITATION] = y_values

data_for_plots = list()
for key in REPORT_ORDER_LIST:
	received_metric = data_dict[C.HOURLY][key]
	single_plot_dict = {
		C.X_VALUES: received_time_series,
		C.Y_VALUES: received_metric[i:last],
		C.TITLE: key,
		C.UNIT_OF_MEASUREMENT: get_units_of_measurement(key)
	}
	data_for_plots.append(single_plot_dict.copy())

title = f"Weather for {latitude}, {longitude} ({elevation_in_feet} feet)"
plot = create_multi_line_charts(title, data_for_plots)
with NamedTemporaryFile(suffix='.png') as tmp:
	temp_filepath = tmp.name
	plot.savefig(temp_filepath)
	viewer_command = [C.IMAGE_VIEW_EXECUTABLE, temp_filepath]
	run(viewer_command, check=True)

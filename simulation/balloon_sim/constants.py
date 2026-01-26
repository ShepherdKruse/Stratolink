"""
Physical constants and configuration values for balloon simulation.
"""

# Earth geometry
EARTH_RADIUS_KM = 6371.0

# Conversion factors
KM_PER_DEGREE_LAT = 111.111  # km per degree of latitude
MS_TO_KMH = 3.6  # meters per second to kilometers per hour

# Default simulation parameters
DEFAULT_COVERAGE_RADIUS_KM = 370.0  # Horizon distance at ~35,000 ft
DEFAULT_PRESSURE_LEVEL = 300  # hPa, approximately 9,000m altitude

# Wind data time resolution
WIND_UPDATE_HOURS = 6  # NCEP Reanalysis data updates every 6 hours

# Grid dimensions for NCEP Reanalysis 2 data
NCEP_GRID_HEIGHT = 73  # Latitude points (2.5 degree resolution)
NCEP_GRID_WIDTH = 144  # Longitude points (2.5 degree resolution)

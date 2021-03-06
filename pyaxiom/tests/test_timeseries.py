#!python
# coding=utf-8

import os
import shutil
import unittest
from copy import copy
from datetime import timedelta, datetime

import numpy as np
import pandas as pd
import netCDF4

from pyaxiom.netcdf import EnhancedDataset
from pyaxiom.netcdf.sensors import TimeSeries, get_dataframe_from_variable

import logging
from pyaxiom import logger
from pyaxiom.utils import urnify
logger.level = logging.INFO
logger.handlers = [logging.StreamHandler()]


class TestTimeSeries(unittest.TestCase):

    def setUp(self):
        self.output_directory = os.path.join(os.path.dirname(__file__), "output")
        self.latitude = 34
        self.longitude = -72
        self.station_name = "PytoolsTestStation"
        self.global_attributes = dict(id='this.is.the.id', naming_authority='my.authority')
        self.fillvalue = -9999.9

    def test_timeseries(self):
        filename = 'test_timeseries.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = None
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        # Basic metadata on all timeseries
        self.assertEqual(nc.cdm_data_type, 'Station')
        self.assertEqual(nc.geospatial_lat_units, 'degrees_north')
        self.assertEqual(nc.geospatial_lon_units, 'degrees_east')
        self.assertEqual(nc.geospatial_vertical_units, 'meters')
        self.assertEqual(nc.geospatial_vertical_positive, 'down')
        self.assertEqual(nc.featureType, 'timeSeries')
        self.assertEqual(nc.geospatial_vertical_resolution, '0')

        # No verticals, so these were not set
        with self.assertRaises(AttributeError):
            nc.geospatial_vertical_min
        with self.assertRaises(AttributeError):
            nc.geospatial_vertical_max

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times)
        assert (nc.variables.get('temperature')[:] == np.asarray(values)).all()

    def test_timeseries_from_dataframe(self):
        filename = 'test_timeseries_from_dataframe.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = 0
        values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature', units='degree_Celsius')

        # From dataframe
        df = pd.DataFrame({
            'depth': verticals,
            'time': [ datetime.utcfromtimestamp(x) for x in times ],
            'value': values
        })
        ts = TimeSeries.from_dataframe(
            df,
            output_directory=self.output_directory,
            output_filename=filename,
            latitude=self.latitude,
            longitude=self.longitude,
            station_name=self.station_name,
            global_attributes=self.global_attributes,
            variable_name='temperature',
            variable_attributes=attrs,
            attempts=4
        )
        ts.add_instrument_variable('temperature')

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        # Basic metadata on all timeseries
        self.assertEqual(nc.cdm_data_type, 'Station')
        self.assertEqual(nc.geospatial_lat_units, 'degrees_north')
        self.assertEqual(nc.geospatial_lon_units, 'degrees_east')
        self.assertEqual(nc.geospatial_vertical_units, 'meters')
        self.assertEqual(nc.geospatial_vertical_positive, 'down')
        self.assertEqual(nc.featureType, 'timeSeries')
        self.assertEqual(nc.geospatial_vertical_resolution, '0')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 0)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times)
        assert nc.variables.get('temperature').long_name == 'Sea Water Temperature (degree_Celsius)'
        assert (nc.variables.get('temperature')[:] == np.asarray(values)).all()

    def test_timeseries_extra_values(self):
        """
        This will map directly to the time variable and ignore any time indexes
        that are not found.  The 'times' parameter to add_variable should be
        the same length as the values parameter.
        """
        filename = 'test_timeseries_extra_values.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = None
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [20, 21, 22, 23, 24, 25, 26, 27, 28]
        value_times = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs, times=value_times)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '0')

        # No verticals, so these were not set
        with self.assertRaises(AttributeError):
            nc.geospatial_vertical_min
        with self.assertRaises(AttributeError):
            nc.geospatial_vertical_max

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times)
        assert (nc.variables.get('temperature')[:] == np.asarray(values[0:6])).all()
        assert nc.variables.get('temperature').long_name == 'Sea Water Temperature'

    def test_timeseries_profile(self):
        filename = 'test_timeseries_profile.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0, 1, 2]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = np.repeat([20, 21, 22, 23, 24, 25], len(verticals))
        attrs = dict(standard_name='sea_water_temperature', vertical_datum='NAVD88')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        # Basic metadata on all timeseries
        self.assertEqual(nc.cdm_data_type, 'Station')
        self.assertEqual(nc.geospatial_lat_units, 'degrees_north')
        self.assertEqual(nc.geospatial_lon_units, 'degrees_east')
        self.assertEqual(nc.geospatial_vertical_units, 'meters')
        self.assertEqual(nc.geospatial_vertical_positive, 'down')
        self.assertEqual(nc.geospatial_bounds_vertical_crs, 'NAVD88')
        self.assertEqual(nc.featureType, 'timeSeriesProfile')
        self.assertEqual(nc.geospatial_vertical_resolution, '1 1')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 2)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z').positive == 'down'
        assert nc.variables.get('z')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times) * len(verticals)
        assert (nc.variables.get('temperature')[:] == values.reshape((len(times), len(verticals)))).all()

    def test_timeseries_profile_from_dataframe(self):
        filename = 'test_timeseries_profile_from_dataframe.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0, 1, 2]
        values = [20, 21, 22]
        attrs = dict(standard_name='sea_water_temperature')

        # From dataframe
        df = pd.DataFrame({
            'depth': np.tile(verticals, 6),
            'time': np.repeat([ datetime.utcfromtimestamp(x) for x in times ], 3),
            'value': np.tile(values, 6)
        })
        ts = TimeSeries.from_dataframe(
            df,
            output_directory=self.output_directory,
            output_filename=filename,
            latitude=self.latitude,
            longitude=self.longitude,
            station_name=self.station_name,
            global_attributes=self.global_attributes,
            variable_name='temperature',
            variable_attributes=attrs,
            attempts=4
        )
        ts.add_instrument_variable('temperature')

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        # Basic metadata on all timeseries
        self.assertEqual(nc.cdm_data_type, 'Station')
        self.assertEqual(nc.geospatial_lat_units, 'degrees_north')
        self.assertEqual(nc.geospatial_lon_units, 'degrees_east')
        self.assertEqual(nc.geospatial_vertical_units, 'meters')
        self.assertEqual(nc.geospatial_vertical_positive, 'down')
        self.assertEqual(nc.featureType, 'timeSeriesProfile')
        self.assertEqual(nc.geospatial_vertical_resolution, '1 1')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 2)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z').positive == 'down'
        assert nc.variables.get('z')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times) * len(verticals)
        assert (nc.variables.get('temperature')[:] == np.tile(values, 6).reshape(6, 3)).all()

    def test_timeseries_profile_different_z_name(self):
        filename = 'test_timeseries_profile_different_z_name.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0, 1, 2]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals,
                        vertical_positive='up',
                        vertical_axis_name='height'
                        )

        values = np.repeat([20, 21, 22, 23, 24, 25], len(verticals))
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '1 1')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 2)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('height').size == len(verticals)
        assert nc.variables.get('height').positive == 'up'
        assert nc.variables.get('height')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times) * len(verticals)
        assert (nc.variables.get('temperature')[:] == values.reshape((len(times), len(verticals)))).all()

    def test_timeseries_profile_extra_values(self):
        """
        This will map directly to the time variable and ignore any time indexes
        that are not found.  The 'times' parameter to add_variable should be
        the same length as the values parameter.
        """
        filename = 'test_timeseries_profile_extra_values.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0, 1, 2]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = np.repeat([20, 21, 22, 23, 24, 25, 26, 27, 28], len(verticals))
        new_times = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]
        values_times = np.repeat(new_times, len(verticals))
        values_verticals = np.repeat(verticals, len(new_times))
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs, times=values_times, verticals=values_verticals)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '1 1')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 2)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('temperature').size == len(times) * len(verticals)
        assert (nc.variables.get('temperature')[:] == np.repeat([20, 21, 22, 23, 24, 25], len(verticals)).reshape((len(times), len(verticals)))).all()

    def test_timeseries_profile_duplicate_heights(self):
        filename = 'test_timeseries_profile_duplicate_heights.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0, 0, 0, 1, 1, 1]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = np.repeat([20, 21, 22, 23, 24, 25], 2)
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '1')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 1)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(list(set(verticals)))
        assert nc.variables.get('z')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times) * len(list(set(verticals)))

        assert (nc.variables.get('temperature')[:] == values.reshape((len(times), 2))).all()

    def test_timeseries_profile_with_shape(self):
        filename = 'test_timeseries_profile_with_shape.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0, 1, 2]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = np.repeat([20, 21, 22, 23, 24, 25], len(verticals)).reshape((len(times), len(verticals)))
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '1 1')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 2)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('temperature').size == len(times) * len(verticals)
        assert (nc.variables.get('temperature')[:] == values.reshape((len(times), len(verticals)))).all()

    def test_timeseries_profile_fill_value_in_z(self):
        filename = 'test_timeseries_profile_fill_value_in_z.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        # Vertical fills MUST be at the BEGINNING of the array!!!!
        verticals = [self.fillvalue, 0]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [self.fillvalue, 20, self.fillvalue, 21, self.fillvalue, 22, self.fillvalue, 23, self.fillvalue, 24, self.fillvalue, 25]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs, fillvalue=self.fillvalue)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '0')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 0)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z')[:].dtype == np.float64
        assert nc.variables.get('temperature').size == len(times) * len(verticals)

        assert nc.variables.get('temperature')[:][0][1] == 20
        assert nc.variables.get('temperature')[:].mask[0][0] == True  # noqa

        assert nc.variables.get('temperature')[:][1][1] == 21
        assert nc.variables.get('temperature')[:].mask[1][0] == True  # noqa

        assert nc.variables.get('temperature')[:][2][1] == 22
        assert nc.variables.get('temperature')[:].mask[2][0] == True  # noqa

        assert nc.variables.get('temperature')[:][3][1] == 23
        assert nc.variables.get('temperature')[:].mask[3][0] == True  # noqa

        assert nc.variables.get('temperature')[:][4][1] == 24
        assert nc.variables.get('temperature')[:].mask[4][0] == True  # noqa

        assert nc.variables.get('temperature')[:][5][1] == 25
        assert nc.variables.get('temperature')[:].mask[5][0] == True  # noqa

        assert (nc.variables.get('temperature')[:] == np.asarray(values).reshape((len(times), len(verticals)))).all()

    def test_timeseries_profile_unsorted_time_and_z(self):
        filename = 'test_timeseries_profile_unsorted_time_and_z.nc'
        times = [5000, 1000, 2000, 3000, 4000, 0]
        verticals = [0, 50]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = np.repeat([20, 21, 22, 23, 24, 25], len(verticals))
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs, fillvalue=self.fillvalue)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '50')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 50)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times) * len(verticals)

        assert nc.variables.get('temperature')[:][0][0] == 25
        assert nc.variables.get('temperature')[:][0][1] == 25
        assert nc.variables.get('temperature')[:][1][0] == 21
        assert nc.variables.get('temperature')[:][1][1] == 21
        assert nc.variables.get('temperature')[:][2][0] == 22
        assert nc.variables.get('temperature')[:][2][1] == 22
        assert nc.variables.get('temperature')[:][3][0] == 23
        assert nc.variables.get('temperature')[:][3][1] == 23
        assert nc.variables.get('temperature')[:][4][0] == 24
        assert nc.variables.get('temperature')[:][4][1] == 24
        assert nc.variables.get('temperature')[:][5][0] == 20
        assert nc.variables.get('temperature')[:][5][1] == 20

    def test_timeseries_profile_with_bottom_temperature(self):
        filename = 'test_timeseries_profile_with_bottom_temperature.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0, 1, 2]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = np.repeat([20, 21, 22, 23, 24, 25], len(verticals))
        bottom_values = [30, 31, 32, 33, 34, 35]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)
        ts.add_variable('bottom_temperature', values=bottom_values, verticals=[60], unlink_from_profile=True, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '1 1')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 2)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times) * len(verticals)
        assert nc.variables.get('sensor_depth') is not None
        assert nc.variables.get('bottom_temperature').size == len(times)

        assert (nc.variables.get('temperature')[:] == values.reshape((len(times), len(verticals)))).all()
        assert (nc.variables.get('bottom_temperature')[:] == np.asarray(bottom_values)).all()

    def test_timeseries_many_variables(self):
        filename = 'test_timeseries_many_variables.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0, 1, 2]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = np.repeat([20, 21, 22, 23, 24, 25], len(verticals))
        bottom_values = [30, 31, 32, 33, 34, 35]
        full_masked = values.view(np.ma.MaskedArray)
        full_masked.mask = True
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature',        values=values, attributes=attrs)
        ts.add_variable('salinity',           values=values.reshape((len(times), len(verticals))))
        ts.add_variable('dissolved_oxygen',   values=full_masked, fillvalue=full_masked.fill_value)
        ts.add_variable('bottom_temperature', values=bottom_values, verticals=[60], unlink_from_profile=True, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        self.assertEqual(nc.geospatial_vertical_resolution, '1 1')
        self.assertEqual(nc.geospatial_vertical_min, 0)
        self.assertEqual(nc.geospatial_vertical_max, 2)

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z')[:].dtype == np.int32
        assert nc.variables.get('temperature').size == len(times) * len(verticals)
        assert (nc.variables.get('temperature')[:] == values.reshape((len(times), len(verticals)))).all()
        assert (nc.variables.get('salinity')[:] == values.reshape((len(times), len(verticals)))).all()
        assert nc.variables.get('dissolved_oxygen')[:].mask.all()

    def test_extracting_dataframe_all_masked_heights(self):
        filename = 'test_extracting_dataframe_all_masked_heights.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [-9999.9]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals,
                        vertical_fill=-9999.9)

        values = np.repeat([20, 21, 22, 23, 24, 25], len(verticals))
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z')[:].dtype == np.float64
        assert nc.variables.get('z')[:].size == 1
        assert nc.variables.get('z')[:].mask == True  # noqa
        assert nc.variables.get('temperature').size == len(times) * len(verticals)

        df = get_dataframe_from_variable(nc, nc.variables.get('temperature'))
        assert df['depth'].dropna().empty

    def test_extracting_dataframe_some_masked_heights(self):
        filename = 'test_extracting_dataframe_some_masked_heights.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [-9999.9, 7.8, 7.9]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals,
                        vertical_fill=-9999.9)

        values = np.repeat([20, 21, 22, 23, 24, 25], len(verticals))
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z')[:].dtype == np.float64
        assert np.allclose(nc.variables.get('z')[:], np.ma.array([np.nan, 7.8, 7.9], mask=[1, 0, 0]))
        assert nc.variables.get('temperature').size == len(times) * len(verticals)

        df = get_dataframe_from_variable(nc, nc.variables.get('temperature'))
        assert not df['depth'].dropna().empty

    def test_extracting_dataframe_ordered_masked_heights(self):
        filename = 'test_extracting_dataframe_ordered_masked_heights.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [np.nan, 7.8]
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals,
                        vertical_fill=np.nan)

        values = np.asarray([[20, 21], [22, 23], [24, 25], [30, 31], [32, 33], [34, 35]])
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        assert nc.variables.get('time').size == len(times)
        assert nc.variables.get('time')[:].dtype == np.int32
        assert nc.variables.get('z').size == len(verticals)
        assert nc.variables.get('z')[:].dtype == np.float64

        # The height order is sorted!
        assert np.allclose(nc.variables.get('z')[:], np.ma.array([7.8, np.nan], mask=[0, 1]))
        assert nc.variables.get('temperature').size == len(times) * len(verticals)

        # Be sure the values are re-arranged because the height order is sorted!
        assert np.isclose(nc.variables.get('temperature')[:][0][0], 21)
        assert np.isclose(nc.variables.get('temperature')[:][1][0], 23)
        assert np.isclose(nc.variables.get('temperature')[:][2][0], 25)
        assert np.isclose(nc.variables.get('temperature')[:][3][0], 31)
        assert np.isclose(nc.variables.get('temperature')[:][4][0], 33)
        assert np.isclose(nc.variables.get('temperature')[:][5][0], 35)

        df = get_dataframe_from_variable(nc, nc.variables.get('temperature'))
        assert not df['depth'].dropna().empty

    def test_instrumnet_metadata_variable(self):
        filename = 'test_timeseries.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = None

        gats = copy(self.global_attributes)
        gats['naming_authority'] = 'pyaxiom'
        gats['geospatial_bounds_vertical_crs'] = 'NAVD88'

        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=gats,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs, create_instrument_variable=True, sensor_vertical_datum='bar')

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None
        assert nc.geospatial_bounds_vertical_crs == 'NAVD88'  # First one set

        datavar = nc.variables.get('temperature')
        instrument_var_name = datavar.instrument
        instvar = nc.variables[instrument_var_name]
        assert instvar.short_name == 'sea_water_temperature'
        assert instvar.ioos_code == urnify(gats['naming_authority'], gats['id'], attrs)

    def test_history_empty(self):
        filename = 'test_history_append.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = None

        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=self.global_attributes,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        history = nc.history.split('\n')
        assert len(history) == 1
        assert 'File created using pyaxiom' in history[0]
        assert '\n' not in history[0]

    def test_history_append_to_string(self):
        filename = 'test_history_append.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = None

        gats = copy(self.global_attributes)
        gats['history'] = 'this is some history'

        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=gats,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        history = nc.history.split('\n')
        assert len(history) == 2
        assert history[0] == 'this is some history'
        assert 'File created using pyaxiom' in history[1]

    def test_history_append_to_list(self):
        filename = 'test_history_append.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = None
        gats = copy(self.global_attributes)

        gats['history'] = 'this is some history\nsome other history\nsome more'
        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=self.station_name,
                        global_attributes=gats,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None

        history = nc.history.split('\n')
        assert len(history) == 4
        assert history[0] == 'this is some history'
        assert history[1] == 'some other history'
        assert history[2] == 'some more'
        assert 'File created using pyaxiom' in history[3]

    def test_station_name_as_urn(self):
        filename = 'test_station_name_as_urn.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = None
        gats = copy(self.global_attributes)

        urn = 'urn:ioos:station:myauthority:mylabel'

        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=urn,
                        global_attributes=gats,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None
        assert nc.variables['platform'].ioos_code == urn
        assert nc.variables['platform'].short_name == 'mylabel'
        assert nc.variables['platform'].long_name == 'Station mylabel'

    def test_station_name_as_urn_override_with_globals(self):
        filename = 'test_station_name_as_urn_override_with_globals.nc'
        times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = None
        gats = copy(self.global_attributes)
        gats['title'] = "My Title Override"
        gats['summary'] = "My Summary Override"

        urn = 'urn:ioos:station:myauthority:mylabel'

        ts = TimeSeries(output_directory=self.output_directory,
                        latitude=self.latitude,
                        longitude=self.longitude,
                        station_name=urn,
                        global_attributes=gats,
                        output_filename=filename,
                        times=times,
                        verticals=verticals)

        values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature')
        ts.add_variable('temperature', values=values, attributes=attrs)

        nc = netCDF4.Dataset(os.path.join(self.output_directory, filename))
        assert nc is not None
        assert nc.variables['platform'].ioos_code == urn
        assert nc.variables['platform'].short_name == gats['title']
        assert nc.variables['platform'].long_name == gats['summary']


class TestTimeseriesTimeBounds(unittest.TestCase):

    def setUp(self):
        self.output_directory = os.path.join(os.path.dirname(__file__), "output")
        self.latitude = 34
        self.longitude = -72
        self.station_name = "PytoolsTestStation"
        self.global_attributes = dict(id='this.is.the.id')

        self.filename = 'test_timeseries_bounds.nc'
        self.times = [0, 1000, 2000, 3000, 4000, 5000]
        verticals = [0]
        self.ts = TimeSeries(output_directory=self.output_directory,
                             latitude=self.latitude,
                             longitude=self.longitude,
                             station_name=self.station_name,
                             global_attributes=self.global_attributes,
                             output_filename=self.filename,
                             times=self.times,
                             verticals=verticals)

        self.values = [20, 21, 22, 23, 24, 25]
        attrs = dict(standard_name='sea_water_temperature')
        self.ts.add_variable('temperature', values=self.values, attributes=attrs)

    def tearDown(self):
        os.remove(os.path.join(self.output_directory, self.filename))

    def test_time_bounds_start(self):
        delta = timedelta(seconds=1000)
        self.ts.add_time_bounds(delta=delta, position='start')

        nc = netCDF4.Dataset(os.path.join(self.output_directory, self.filename))
        assert nc.variables.get('time_bounds').shape == (len(self.times), 2,)
        assert (nc.variables.get('time_bounds')[:] == np.asarray([
                                                                    [0,    1000],
                                                                    [1000, 2000],
                                                                    [2000, 3000],
                                                                    [3000, 4000],
                                                                    [4000, 5000],
                                                                    [5000, 6000]
                                                                ])).all()
        nc.close()

    def test_time_bounds_middle(self):
        delta = timedelta(seconds=1000)
        self.ts.add_time_bounds(delta=delta, position='middle')

        nc = netCDF4.Dataset(os.path.join(self.output_directory, self.filename))
        assert nc.variables.get('time_bounds').shape == (len(self.times), 2,)
        assert (nc.variables.get('time_bounds')[:] == np.asarray([
                                                                    [ -500,  500],
                                                                    [  500, 1500],
                                                                    [ 1500, 2500],
                                                                    [ 2500, 3500],
                                                                    [ 3500, 4500],
                                                                    [ 4500, 5500]
                                                                ])).all()
        nc.close()

    def test_time_bounds_end(self):
        delta = timedelta(seconds=1000)
        self.ts.add_time_bounds(delta=delta, position='end')

        nc = netCDF4.Dataset(os.path.join(self.output_directory, self.filename))
        assert nc.variables.get('time_bounds').shape == (len(self.times), 2,)
        assert (nc.variables.get('time_bounds')[:] == np.asarray([
                                                                    [-1000,    0],
                                                                    [    0, 1000],
                                                                    [ 1000, 2000],
                                                                    [ 2000, 3000],
                                                                    [ 3000, 4000],
                                                                    [ 4000, 5000]
                                                                ])).all()
        nc.close()


class TestDataFrameFromVariable(unittest.TestCase):
    def test_sensor_with_depths(self):
        ncfile1 = os.path.join(os.path.dirname(__file__), 'resources', 'sensor_with_depths_1.nc')
        ncd1 = EnhancedDataset(ncfile1)
        ncvar1 = ncd1.variables['soil_moisture_percent']
        df1 = get_dataframe_from_variable(ncd1, ncvar1)
        ncd1.close()

        ncfile2 = os.path.join(os.path.dirname(__file__), 'resources', 'sensor_with_depths_2.nc')
        ncd2 = EnhancedDataset(ncfile2)
        ncvar2 = ncd2.variables['soil_moisture_percent']
        df2 = get_dataframe_from_variable(ncd2, ncvar2)
        ncd2.close()

        df = df2.combine_first(df1)

        assert not df.empty

    def test_flip_depths(self):
        ncfile1 = os.path.join(os.path.dirname(__file__), 'resources', 'sensor_with_depths_3.nc')
        ncd1 = EnhancedDataset(ncfile1)
        ncvar1 = ncd1.variables['soil_moisture_percent']
        df1 = get_dataframe_from_variable(ncd1, ncvar1)

        assert np.allclose(df1.depth.unique(), np.asarray([-0.0508, -0.2032, -0.508]))


class TestFromDataframeAttempts(unittest.TestCase):

    def setUp(self):
        self.output_directory = os.path.join(os.path.dirname(__file__), "output", 'attempts')
        self.latitude = 34
        self.longitude = -72
        self.station_name = "PytoolsTestStation"
        self.global_attributes = dict(id='this.is.the.id')
        self.fillvalue = -9999.9
        self.vatts = dict(standard_name='sea_water_temperature')
        self.vname = 'temperature'
        times = [0, 1000, 2000, 3000, 4000, 5000, 6000, 2000]
        verticals = [None, 1, 2, 3, None, 4, 5, 6]
        values = [20, 21, 22, 23, 24, 25, 0, 9]
        self.df = pd.DataFrame({
            'depth': verticals,
            'time': [ datetime.utcfromtimestamp(x) for x in times ],
            'value': values
        })

    def tearDown(self):
        try:
            shutil.rmtree(self.output_directory)
        except FileNotFoundError:
            pass

    def test_attempts_1(self):
        filename = 'test_attempts_1.nc'

        # From dataframe
        with self.assertRaises(ValueError):
            TimeSeries.from_dataframe(
                self.df,
                output_directory=self.output_directory,
                output_filename=filename,
                latitude=self.latitude,
                longitude=self.longitude,
                station_name=self.station_name,
                global_attributes=self.global_attributes,
                variable_name=self.vname,
                variable_attributes=self.vatts,
                attempts=1
            )

    def test_attempts_2(self):
        filename = 'test_attempts_2.nc'

        # From dataframe
        with self.assertRaises(ValueError):
            TimeSeries.from_dataframe(
                self.df,
                output_directory=self.output_directory,
                output_filename=filename,
                latitude=self.latitude,
                longitude=self.longitude,
                station_name=self.station_name,
                global_attributes=self.global_attributes,
                variable_name=self.vname,
                variable_attributes=self.vatts,
                attempts=2
            )

    def test_attempts_3(self):
        filename = 'test_attempts_3.nc'

        # From dataframe
        with self.assertRaises(ValueError):
            TimeSeries.from_dataframe(
                self.df,
                output_directory=self.output_directory,
                output_filename=filename,
                latitude=self.latitude,
                longitude=self.longitude,
                station_name=self.station_name,
                global_attributes=self.global_attributes,
                variable_name=self.vname,
                variable_attributes=self.vatts,
                attempts=3
            )

    def test_attempts_4(self):
        filename = 'test_attempts_4.nc'

        # From dataframe
        with self.assertRaises(ValueError):
            TimeSeries.from_dataframe(
                self.df,
                output_directory=self.output_directory,
                output_filename=filename,
                latitude=self.latitude,
                longitude=self.longitude,
                station_name=self.station_name,
                global_attributes=self.global_attributes,
                variable_name=self.vname,
                variable_attributes=self.vatts,
                attempts=4
            )

    def test_attempts_5(self):
        filename = 'test_attempts_5.nc'

        # From dataframe
        TimeSeries.from_dataframe(
            self.df,
            output_directory=self.output_directory,
            output_filename=filename,
            latitude=self.latitude,
            longitude=self.longitude,
            station_name=self.station_name,
            global_attributes=self.global_attributes,
            variable_name=self.vname,
            variable_attributes=self.vatts,
            attempts=5
        )

    def test_attempts_empty(self):
        filename = 'test_attempts_empty.nc'

        # From dataframe
        TimeSeries.from_dataframe(
            self.df,
            output_directory=self.output_directory,
            output_filename=filename,
            latitude=self.latitude,
            longitude=self.longitude,
            station_name=self.station_name,
            global_attributes=self.global_attributes,
            variable_name=self.vname,
            variable_attributes=self.vatts
        )

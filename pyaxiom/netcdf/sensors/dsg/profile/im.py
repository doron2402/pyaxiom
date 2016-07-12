# -*- coding: utf-8 -*-
from datetime import datetime
from collections import namedtuple

import numpy as np
import pandas as pd
import netCDF4 as nc4
from pygc import great_distance
from shapely.geometry import Point, LineString

from pyaxiom.utils import unique_justseen
from pyaxiom.netcdf import CFDataset
from pyaxiom import logger


class IncompleteMultidimensionalProfile(CFDataset):
    """
    If there are the same number of levels in each profile, but they do not
    have the same set of vertical coordinates, one can use the incomplete
    multidimensional array representation, which the vertical coordinate
    variable is two-dimensional e.g. replacing z(z) in Example H.8,
    "Atmospheric sounding profiles for a common set of vertical coordinates
    stored in the orthogonal multidimensional array representation." with
    alt(profile,z).  This representation also allows one to have a variable
    number of elements in different profiles, at the cost of some wasted space.
    In that case, any unused elements of the data and auxiliary coordinate
    variables must contain missing data values (section 9.6).
    """

    @classmethod
    def is_mine(cls, dsg):
        try:
            pvars = dsg.get_variables_by_attributes(cf_role='profile_id')
            assert len(pvars) == 1
            assert dsg.featureType.lower() == 'profile'
            assert len(dsg.t_axes()) == 1
            assert len(dsg.x_axes()) == 1
            assert len(dsg.y_axes()) == 1
            assert len(dsg.z_axes()) == 1

            # Allow for string variables
            pvar = pvars[0]
            # This diferentiates between this and an OrthogonalMultidimensionalProfile
            # Incomplete files need to have a profile dimension (at least 1 dim).
            minimum_dimensions = 1
            maximum_dimensions = 2
            if np.issubdtype(pvar.dtype, 'S'):
                minimum_dimensions += 1
                maximum_dimensions += 1
            assert minimum_dimensions <= len(pvar.dimensions) <= maximum_dimensions

            t = dsg.t_axes()[0]
            x = dsg.x_axes()[0]
            y = dsg.y_axes()[0]
            z = dsg.z_axes()[0]
            assert t.size == pvar.size
            assert x.size == pvar.size
            assert y.size == pvar.size
            p_dim = dsg.dimensions[pvar.dimensions[0]]
            z_dim = dsg.dimensions[[ d for d in z.dimensions if d != p_dim.name ][0]]
            for dv in dsg.datavars() + [z]:
                assert len(dv.dimensions) == 2
                assert z_dim.name in dv.dimensions
                assert p_dim.name in dv.dimensions
                assert dv.size == z_dim.size * p_dim.size

        except BaseException:
            return False

        return True

    def from_dataframe(self, df, variable_attributes=None, global_attributes=None):
        variable_attributes = variable_attributes or {}
        global_attributes = global_attributes or {}

        raise NotImplementedError

    def calculated_metadata(self, geometries=True, clean_cols=True, clean_rows=True):
        df = self.to_dataframe(clean_cols=clean_cols, clean_rows=clean_rows)

        profiles = {}
        for pid, pgroup in df.groupby('profile'):
            pgroup = pgroup.sort_values('t')
            first_row = pgroup.iloc[0]
            profile = namedtuple('Profile', ['min_z', 'max_z', 't', 'x', 'y', 'loc'])
            profiles[pid] = profile(
                min_z=pgroup.z.min(),
                max_z=pgroup.z.max(),
                t=first_row.t,
                x=first_row.x,
                y=first_row.y,
                loc=Point(first_row.x, first_row.y)
            )

        geometry = None
        first_loc = None
        if geometries:
            first_row = df.iloc[0]
            first_loc = Point(first_row.x, first_row.y)
            coords = list(unique_justseen(zip(df.x, df.y)))
            if len(coords) > 1:
                geometry = LineString(coords)  # noqa
            elif len(coords) == 1:
                geometry = first_loc  # noqa

        meta = namedtuple('Metadata', ['min_t', 'max_t', 'profiles', 'first_loc', 'geometry'])
        return meta(
            min_t=df.t.min(),
            max_t=df.t.max(),
            profiles=profiles,
            first_loc=first_loc,
            geometry=geometry
        )

    def to_dataframe(self, clean_cols=True, clean_rows=True):
        pvar = self.get_variables_by_attributes(cf_role='profile_id')[0]
        # Multiple profiles in the file
        p_dim = self.dimensions[pvar.dimensions[0]]
        ps = p_dim.size
        logger.debug(['# profiles: ', ps])

        zvar = self.z_axes()[0]

        z_dim = self.dimensions[[ d for d in zvar.dimensions if d != p_dim.name ][0]]
        zs = z_dim.size

        # Profiles
        try:
            p = np.ma.fix_invalid(np.ma.MaskedArray(pvar[:]).astype(int))
        except ValueError:
            p = np.asarray(list(range(len(pvar))), dtype=np.integer)
        p = p.repeat(zs).astype(np.integer)
        logger.debug(['profile data size: ', p.size])

        # Z
        z = np.ma.fix_invalid(np.ma.MaskedArray(zvar[:].astype(np.float64)))
        z = z.flatten().round(5)
        logger.debug(['z data size: ', z.size])

        # T
        tvar = self.t_axes()[0]
        t = nc4.num2date(tvar[:], tvar.units, getattr(tvar, 'calendar', 'standard'))
        if isinstance(t, datetime):
            # Size one
            t = np.array([t.isoformat()], dtype='datetime64')
        t = t.repeat(zs)
        logger.debug(['time data size: ', t.size])

        # X
        xvar = self.x_axes()[0]
        x = np.ma.fix_invalid(np.ma.MaskedArray(xvar[:].astype(np.float64)))
        x = x.repeat(zs).round(5)
        logger.debug(['x data size: ', x.size])

        # Y
        yvar = self.y_axes()[0]
        y = np.ma.fix_invalid(np.ma.MaskedArray(yvar[:].astype(np.float64)))
        y = y.repeat(zs).round(5)
        logger.debug(['y data size: ', y.size])

        # Distance
        d = np.append([0], great_distance(start_latitude=y[0:-1], end_latitude=y[1:], start_longitude=x[0:-1], end_longitude=x[1:])['distance'])
        d = np.ma.fix_invalid(np.ma.MaskedArray(np.cumsum(d)).astype(np.float64).round(2))
        logger.debug(['distance data size: ', d.size])

        df_data = {
            't': t,
            'x': x,
            'y': y,
            'z': z,
            'profile': p,
            'distance': d
        }

        building_index_to_drop = np.ones(t.size, dtype=bool)
        for i, x in enumerate(self.datavars()):
            vdata = np.ma.fix_invalid(np.ma.MaskedArray(x[:].astype(np.float64).round(3).flatten()))
            building_index_to_drop = (building_index_to_drop == True) & (vdata.mask == True)  # noqa
            df_data[x.name] = vdata

        df = pd.DataFrame(df_data)

        # Drop all data columns with no data
        if clean_cols:
            df = df.dropna(axis=1, how='all')

        # Drop all data rows with no data variable data
        if clean_rows:
            df = df.iloc[~building_index_to_drop]

        return df
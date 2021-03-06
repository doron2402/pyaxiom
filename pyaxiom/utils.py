#!python
# coding=utf-8
import base64
import random
import string
import operator
import itertools
import simplejson as json

import numpy as np
import netCDF4 as nc4

from pyaxiom.urn import IoosUrn
from pyaxiom import logger


class DotDict(object):
    def __init__(self, *args, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        import pprint
        return pprint.pformat(vars(self), indent=2)


def all_subclasses(cls):
    """ Recursively generate of all the subclasses of class cls. """
    for subclass in cls.__subclasses__():
        yield subclass
        for subc in all_subclasses(subclass):
            yield subc


def unique_justseen(iterable, key=None):
    "List unique elements, preserving order. Remember only the element just seen."
    # unique_justseen('AAAABBBCCDAABBB') --> A B C D A B
    # unique_justseen('ABBCcAD', str.lower) --> A B C A D
    try:
        # PY2 support
        from itertools import imap as map
    except ImportError:
        from builtins import map

    return map(next, map(operator.itemgetter(1), itertools.groupby(iterable, key)))


def normalize_array(var):
    """
    Returns a normalized data array from a NetCDF4 variable. This is mostly
    used to normalize string types between py2 and py3. It has no effect on types
    other than chars/strings
    """
    if np.issubdtype(var.dtype, 'S1'):
        if var.dtype == str:
            # Python 2 on netCDF4 'string' variables needs this.
            # Python 3 returns false for np.issubdtype(var.dtype, 'S1')
            return var[:]

        def decoder(x):
            return str(x.decode('utf-8'))
        vfunc = np.vectorize(decoder)
        return vfunc(nc4.chartostring(var[:]))
    else:
        return var[:]


def safe_attribute_typing(zdtype, value):
    try:
        return zdtype.type(value)
    except ValueError:
        logger.warning("Could not convert {} to type {}".format(value, zdtype))
        return None


def generic_masked(arr, attrs=None, minv=None, maxv=None, mask_nan=True):
    """
    Returns a masked array with anything outside of values masked.
    The minv and maxv parameters take precendence over any dict values.
    The valid_range attribute takes precendence over the valid_min and
    valid_max attributes.
    """
    attrs = attrs or {}

    if 'valid_min' in attrs:
        minv = safe_attribute_typing(arr.dtype, attrs['valid_min'])
    if 'valid_max' in attrs:
        maxv = safe_attribute_typing(arr.dtype, attrs['valid_max'])
    if 'valid_range' in attrs:
        vr = attrs['valid_range']
        minv = safe_attribute_typing(arr.dtype, vr[0])
        maxv = safe_attribute_typing(arr.dtype, vr[1])

    # Get the min/max of values that the hardware supports
    try:
        info = np.iinfo(arr.dtype)
    except ValueError:
        info = np.finfo(arr.dtype)

    minv = minv if minv is not None else info.min
    maxv = maxv if maxv is not None else info.max

    if mask_nan is True:
        arr = np.ma.fix_invalid(arr)

    return np.ma.masked_outside(
        arr,
        minv,
        maxv
    )


def pyscalar(val):
    return np.asscalar(val)


def get_fill_value(var):
    if hasattr(var, 'missing_value'):
        return var.missing_value
    elif hasattr(var, '_FillValue'):
        return var._FillValue
    return None


def fix_int_dtypes(obj):
    # DAP does not support int64 until DAP4 and NetCDF Java doesn't
    # seem to support int64 either. Try to convert to int32 and
    # fall back to a double if we can't do the converstion.
    if np.issubdtype(obj.dtype, np.int64) or np.issubdtype(obj.dtype, np.uint64):
        ii = np.iinfo(np.int32)
        if np.any(obj > ii.max) or np.any(obj < ii.min):
            # Data can't fit in an int32
            return np.float64
        else:
            return np.int32
    else:
        return obj.dtype


def get_dtype(obj):
    if isinstance(obj, (tuple, list)):
        obj = obj[0]

    if hasattr(obj, 'dtype'):
        if obj.dtype == object:
            return str
        elif np.issubdtype(obj.dtype, int):
            return fix_int_dtypes(obj)
        else:
            return obj.dtype
    else:
        return type(obj)


def dict_update(d, u):
    # http://stackoverflow.com/a/3233356
    import collections
    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            r = dict_update(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


def dictify_urn(urn, combine_interval=True):
    """
        By default, this will put the `interval` as part of the `cell_methods`
        attribute (NetCDF CF style). To return `interval` as its own key, use
        the `combine_interval=False` parameter.
    """
    ioos_urn = IoosUrn.from_string(urn)

    if ioos_urn.valid() is False:
        return dict()

    if ioos_urn.asset_type != 'sensor':
        logger.error("This function only works on 'sensor' URNs.")
        return dict()

    if '#' in ioos_urn.component:
        standard_name, extras = ioos_urn.component.split('#')
    else:
        standard_name = ioos_urn.component
        extras = ''

    d = dict(standard_name=standard_name)

    # Discriminant
    if '-' in ioos_urn.component:
        d['discriminant'] = standard_name.split('-')[-1]
        d['standard_name'] = standard_name.split('-')[0]

    intervals = []
    cell_methods = []
    if extras:
        for section in extras.split(';'):
            key, values = section.split('=')
            if key == 'interval':
                # special case, intervals should be appended to the cell_methods
                for v in values.split(','):
                    intervals.append(v)
            else:
                if key == 'cell_methods':
                    value = [ x.replace('_', ' ').replace(':', ': ') for x in values.split(',') ]
                    cell_methods = value
                else:
                    value = ' '.join([x.replace('_', ' ').replace(':', ': ') for x in values.split(',')])
                    d[key] = value

    if combine_interval is True:
        if cell_methods and intervals:
            if len(cell_methods) == len(intervals):
                d['cell_methods'] = ' '.join([ '{} (interval: {})'.format(x[0], x[1].upper()) for x in zip(cell_methods, intervals) ])
            else:
                d['cell_methods'] = ' '.join(cell_methods)
                for i in intervals:
                    d['cell_methods'] += ' (interval: {})'.format(i.upper())
        elif cell_methods:
            d['cell_methods'] = ' '.join(cell_methods)
            for i in intervals:
                d['cell_methods'] += ' (interval: {})'.format(i.upper())
        elif intervals:
            raise ValueError("An interval without a cell_method is not allowed!  Not possible!")
    else:
        d['cell_methods'] = ' '.join(cell_methods)
        d['interval'] = ','.join(intervals).upper()

    if 'vertical_datum' in d:
        d['vertical_datum'] = d['vertical_datum'].upper()

    return d


def urnify(naming_authority, station_identifier, data):

    if isinstance(data, dict):
        return urnify_from_dict(naming_authority, station_identifier, data)
    else:
        d = dict(standard_name=getattr(data, 'standard_name', None),
                 bounds=getattr(data, 'bounds', None),
                 cell_methods=getattr(data, 'cell_methods', None),
                 vertical_datum=getattr(data, 'vertical_datum', None),
                 name=getattr(data, 'name', None),
                 discriminant=getattr(data, 'discriminant', None),
                 interval=getattr(data, 'interval', None))
        return urnify_from_dict(naming_authority, station_identifier, d)


def urnify_from_dict(naming_authority, station_identifier, data_dict):

    def clean_value(v):
        return v.replace('(', '').replace(')', '').strip().replace(' ', '_')
    extras = []
    intervals = []  # Because it can be part of cell_methods and its own dict key

    if 'cell_methods' in data_dict and data_dict['cell_methods']:
        cm = data_dict['cell_methods']
        keys = []
        values = []
        sofar = ''
        for i, c in enumerate(cm):
            if c == ":":
                if len(keys) == len(values):
                    keys.append(clean_value(sofar))
                else:
                    for j in reversed(range(0, i)):
                        if cm[j] == " ":
                            key = clean_value(cm[j+1:i])
                            values.append(clean_value(sofar.replace(key, '')))
                            keys.append(key)
                            break
                sofar = ''
            else:
                sofar += c
        # The last value needs appending
        values.append(clean_value(sofar))

        pairs = zip(keys, values)

        mems = []
        cell_intervals = []
        pairs = sorted(pairs)
        for group, members in itertools.groupby(pairs, lambda x: x[0]):
            if group == 'interval':
                cell_intervals = [m[1] for m in members]
            elif group in ['time', 'area']:  # Ignore 'comments'. May need to add more things here...
                member_strings = []
                for m in members:
                    member_strings.append('{}:{}'.format(group, m[1]))
                mems.append(','.join(member_strings))
        if mems:
            extras.append('cell_methods={}'.format(','.join(mems)))
        if cell_intervals:
            intervals += cell_intervals

    if 'bounds' in data_dict and data_dict['bounds']:
        extras.append('bounds={0}'.format(data_dict['bounds']))

    if 'vertical_datum' in data_dict and data_dict['vertical_datum']:
        extras.append('vertical_datum={0}'.format(data_dict['vertical_datum']))

    if 'interval' in data_dict and data_dict['interval']:
        if isinstance(data_dict['interval'], (list, tuple,)):
            intervals += data_dict['interval']
        elif isinstance(data_dict['interval'], str):
            intervals += [data_dict['interval']]

    if 'standard_name' in data_dict and data_dict['standard_name']:
        variable_name = data_dict['standard_name']
    elif 'name' in data_dict and data_dict['name']:
        variable_name = data_dict['name']
    else:
        variable_name = ''.join(random.choice(string.ascii_uppercase) for _ in range(8)).lower()
        logger.warning("Had to randomly generate a variable name: {0}".format(variable_name))

    if 'discriminant' in data_dict and data_dict['discriminant']:
        variable_name = '{}-{}'.format(variable_name, data_dict['discriminant'])

    if intervals:
        intervals = list(set(intervals))  # Unique them
        extras.append('interval={}'.format(','.join(intervals)))

    if extras:
        variable_name = '{0}#{1}'.format(variable_name, ';'.join(extras))

    u = IoosUrn(asset_type='sensor',
                authority=naming_authority,
                label=station_identifier,
                component=variable_name,
                version=None)

    return u.urn


class BasicNumpyEncoder(json.JSONEncoder):

    def default(self, obj):
        """If input object is an ndarray it will be converted into a list
        """
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.generic):
            return np.asscalar(obj)
        # Let the base class default method raise the TypeError
        return json.JSONEncoder(self, obj)


class NumpyEncoder(json.JSONEncoder):

    def default(self, obj):
        """If input object is an ndarray it will be converted into a dict
        holding dtype, shape and the data, base64 encoded.
        """
        if isinstance(obj, np.ndarray):
            if obj.flags['C_CONTIGUOUS']:
                obj_data = obj.data
            else:
                cont_obj = np.ascontiguousarray(obj)
                assert(cont_obj.flags['C_CONTIGUOUS'])
                obj_data = cont_obj.data
            data_b64 = base64.b64encode(obj_data)
            return dict(__ndarray__=data_b64,
                        dtype=str(obj.dtype),
                        shape=obj.shape)
        elif isinstance(obj, np.generic):
            return np.asscalar(obj)
        # Let the base class default method raise the TypeError
        return json.JSONEncoder(self, obj)

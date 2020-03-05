import base64
import hashlib
import importlib
import json
import logging
import os
import shlex
import sys
from collections import namedtuple
from contextlib import contextmanager
from enum import Enum, EnumMeta
from pathlib import Path

import requests

from lpipe.exceptions import InvalidInputError, InvalidPathError


def hash(encoded_data):
    return hashlib.sha1(encoded_data.encode("utf-8")).hexdigest()


def batch(iterable, n=1):
    """Batch iterator.

    https://stackoverflow.com/a/8290508

    """
    iter_len = len(iterable)
    for ndx in range(0, iter_len, n):
        yield iterable[ndx : min(ndx + n, iter_len)]


def get_nested(d, keys):
    """Given a dictionary, fetch a key nested several levels deep."""

    def _get(head, k):
        if isinstance(head, dict):
            return head.get(k, {})
        else:
            return getattr(head, k, {})

    head = d
    for k in keys:
        head = _get(head, k)
        if not head:
            return head
    return head


def set_nested(d, keys, value):
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _set_env(env):
    state = {}
    for k, v in env.items():
        state[k] = os.environ[k] if k in os.environ else None
        os.environ[k] = str(v)
        logging.getLogger().debug(f"os.environ[{k}] = {v}")
    return state


def _reset_env(env, state):
    for k, v in env.items():
        if k in state and state[k]:
            os.environ[k] = str(state[k])
        elif k in os.environ:
            del os.environ[k]


@contextmanager
def set_env(env):
    state = {}
    try:
        state = _set_env(env)
        yield
    finally:
        _reset_env(env, state)


class AutoEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            if isinstance(obj, Enum):
                return str(obj)
            return obj._json()
        except AttributeError:
            return json.JSONEncoder.default(self, obj)


def check_status(response, code=2, keys=["ResponseMetadata", "HTTPStatusCode"]):
    """Check status of an AWS API response."""
    status = get_nested(response, keys)
    assert status // 100 == code
    return status


def call(_callable, *args, **kwargs):
    """Call boto3 function and check the AWS API response status code.

    Args:
        _callable (function): boto3 function to call
        *args: arguments to pass to _callable
        **kwargs: keyword args to pass to _callable

    Raises:
        AssertionError: if the _callable response status code is not in the 200 range
    """
    resp = _callable(*args, **kwargs)
    check_status(resp)
    return resp


def get_enum_value(e: EnumMeta, k):
    """Get the value of an enum key.

    Args:
        e (EnumMeta): A reference to an enumerated values
        k: The name of an enumerated value

    Raises:
        InvalidPathError: if key `k` is not in Enum `e`
    """
    try:
        return e[str(k).split(".")[-1]]
    except KeyError as err:
        raise InvalidPathError(err)


def _repr(o, attrs):
    desc = ", ".join([f"{a}: {getattr(o, a)}" for a in attrs])
    return f"{o.__class__.__name__}<{desc}>"


def describe_client_error(e):
    return e.response.get("Error", {}).get("Code")

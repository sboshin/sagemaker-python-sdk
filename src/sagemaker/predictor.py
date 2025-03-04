# Copyright 2017-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
"""Placeholder docstring"""
from __future__ import print_function, absolute_import

import codecs
import csv
import json
import six
from six import StringIO, BytesIO
import numpy as np

from sagemaker.content_types import CONTENT_TYPE_JSON, CONTENT_TYPE_CSV, CONTENT_TYPE_NPY
from sagemaker.model_monitor import DataCaptureConfig
from sagemaker.session import Session
from sagemaker.utils import name_from_base

from sagemaker.model_monitor.model_monitoring import (
    _DEFAULT_MONITOR_IMAGE_URI_WITH_PLACEHOLDERS,
    ModelMonitor,
    DefaultModelMonitor,
)


class RealTimePredictor(object):
    """Make prediction requests to an Amazon SageMaker endpoint."""

    def __init__(
        self,
        endpoint,
        sagemaker_session=None,
        serializer=None,
        deserializer=None,
        content_type=None,
        accept=None,
    ):
        """Initialize a ``RealTimePredictor``.

        Behavior for serialization of input data and deserialization of
        result data can be configured through initializer arguments. If not
        specified, a sequence of bytes is expected and the API sends it in the
        request body without modifications. In response, the API returns the
        sequence of bytes from the prediction result without any modifications.

        Args:
            endpoint (str): Name of the Amazon SageMaker endpoint to which
                requests are sent.
            sagemaker_session (sagemaker.session.Session): A SageMaker Session
                object, used for SageMaker interactions (default: None). If not
                specified, one is created using the default AWS configuration
                chain.
            serializer (callable): Accepts a single argument, the input data,
                and returns a sequence of bytes. It may provide a
                ``content_type`` attribute that defines the endpoint request
                content type. If not specified, a sequence of bytes is expected
                for the data.
            deserializer (callable): Accepts two arguments, the result data and
                the response content type, and returns a sequence of bytes. It
                may provide a ``content_type`` attribute that defines the
                endpoint response's "Accept" content type. If not specified, a
                sequence of bytes is expected for the data.
            content_type (str): The invocation's "ContentType", overriding any
                ``content_type`` from the serializer (default: None).
            accept (str): The invocation's "Accept", overriding any accept from
                the deserializer (default: None).
        """
        self.endpoint = endpoint
        self.sagemaker_session = sagemaker_session or Session()
        self.serializer = serializer
        self.deserializer = deserializer
        self.content_type = content_type or getattr(serializer, "content_type", None)
        self.accept = accept or getattr(deserializer, "accept", None)
        self._endpoint_config_name = self._get_endpoint_config_name()
        self._model_names = self._get_model_names()

    def predict(self, data, initial_args=None):
        """Return the inference from the specified endpoint.

        Args:
            data (object): Input data for which you want the model to provide
                inference. If a serializer was specified when creating the
                RealTimePredictor, the result of the serializer is sent as input
                data. Otherwise the data must be sequence of bytes, and the
                predict method then sends the bytes in the request body as is.
            initial_args (dict[str,str]): Optional. Default arguments for boto3
                ``invoke_endpoint`` call. Default is None (no default
                arguments).

        Returns:
            object: Inference for the given input. If a deserializer was specified when creating
                the RealTimePredictor, the result of the deserializer is
                returned. Otherwise the response returns the sequence of bytes
                as is.
        """

        request_args = self._create_request_args(data, initial_args)
        response = self.sagemaker_session.sagemaker_runtime_client.invoke_endpoint(**request_args)
        return self._handle_response(response)

    def _handle_response(self, response):
        """
        Args:
            response:
        """
        response_body = response["Body"]
        if self.deserializer is not None:
            # It's the deserializer's responsibility to close the stream
            return self.deserializer(response_body, response["ContentType"])
        data = response_body.read()
        response_body.close()
        return data

    def _create_request_args(self, data, initial_args=None):
        """
        Args:
            data:
            initial_args:
        """
        args = dict(initial_args) if initial_args else {}

        if "EndpointName" not in args:
            args["EndpointName"] = self.endpoint

        if self.content_type and "ContentType" not in args:
            args["ContentType"] = self.content_type

        if self.accept and "Accept" not in args:
            args["Accept"] = self.accept

        if self.serializer is not None:
            data = self.serializer(data)

        args["Body"] = data
        return args

    def _delete_endpoint_config(self):
        """Delete the Amazon SageMaker endpoint configuration"""
        self.sagemaker_session.delete_endpoint_config(self._endpoint_config_name)

    def delete_endpoint(self, delete_endpoint_config=True):
        """Delete the Amazon SageMaker endpoint backing this predictor. Also
        delete the endpoint configuration attached to it if
        delete_endpoint_config is True.

        Args:
            delete_endpoint_config (bool, optional): Flag to indicate whether to
                delete endpoint configuration together with endpoint. Defaults
                to True. If True, both endpoint and endpoint configuration will
                be deleted. If False, only endpoint will be deleted.
        """
        if delete_endpoint_config:
            self._delete_endpoint_config()

        self.sagemaker_session.delete_endpoint(self.endpoint)

    def delete_model(self):
        """Deletes the Amazon SageMaker models backing this predictor."""
        request_failed = False
        failed_models = []
        for model_name in self._model_names:
            try:
                self.sagemaker_session.delete_model(model_name)
            except Exception:  # pylint: disable=broad-except
                request_failed = True
                failed_models.append(model_name)

        if request_failed:
            raise Exception(
                "One or more models cannot be deleted, please retry. \n"
                "Failed models: {}".format(", ".join(failed_models))
            )

    def enable_data_capture(self):
        """Updates the DataCaptureConfig for the Predictor's associated Amazon SageMaker Endpoint
        to enable data capture. For a more customized experience, refer to
        update_data_capture_config, instead.
        """
        self.update_data_capture_config(data_capture_config=DataCaptureConfig(enable_capture=True))

    def disable_data_capture(self):
        """Updates the DataCaptureConfig for the Predictor's associated Amazon SageMaker Endpoint
        to disable data capture. For a more customized experience, refer to
        update_data_capture_config, instead.
        """
        self.update_data_capture_config(data_capture_config=DataCaptureConfig(enable_capture=False))

    def update_data_capture_config(self, data_capture_config):
        """Updates the DataCaptureConfig for the Predictor's associated Amazon SageMaker Endpoint
        with the provided DataCaptureConfig.

        Args:
            data_capture_config (sagemaker.model_monitor.DataCaptureConfig): The
                DataCaptureConfig to update the predictor's endpoint to use.
        """
        endpoint_desc = self.sagemaker_session.sagemaker_client.describe_endpoint(
            EndpointName=self.endpoint
        )

        new_config_name = name_from_base(base=self.endpoint)

        data_capture_config_dict = None
        if data_capture_config is not None:
            data_capture_config_dict = data_capture_config._to_request_dict()

        self.sagemaker_session.create_endpoint_config_from_existing(
            existing_config_name=endpoint_desc["EndpointConfigName"],
            new_config_name=new_config_name,
            new_data_capture_config_dict=data_capture_config_dict,
        )

        self.sagemaker_session.update_endpoint(
            endpoint_name=self.endpoint, endpoint_config_name=new_config_name
        )

    def list_monitors(self):
        """Generates ModelMonitor objects (or DefaultModelMonitors) based on the schedule(s)
        associated with the endpoint that this predictor refers to.

        Returns:
            [ModelMonitor]: A list of ModelMonitor (or DefaultModelMonitor) objects.

        """
        monitoring_schedules_dict = self.sagemaker_session.list_monitoring_schedules(
            endpoint_name=self.endpoint
        )
        if len(monitoring_schedules_dict["MonitoringScheduleSummaries"]) == 0:
            print("No monitors found for endpoint. endpoint: {}".format(self.endpoint))
            return []

        monitors = []
        for schedule_dict in monitoring_schedules_dict["MonitoringScheduleSummaries"]:
            schedule_name = schedule_dict["MonitoringScheduleName"]
            schedule = self.sagemaker_session.describe_monitoring_schedule(
                monitoring_schedule_name=schedule_name
            )
            image_uri = schedule["MonitoringScheduleConfig"]["MonitoringJobDefinition"][
                "MonitoringAppSpecification"
            ]["ImageUri"]
            index_after_placeholders = _DEFAULT_MONITOR_IMAGE_URI_WITH_PLACEHOLDERS.rfind("{}")
            if image_uri.endswith(
                _DEFAULT_MONITOR_IMAGE_URI_WITH_PLACEHOLDERS[index_after_placeholders + len("{}") :]
            ):
                monitors.append(
                    DefaultModelMonitor.attach(
                        monitor_schedule_name=schedule_name,
                        sagemaker_session=self.sagemaker_session,
                    )
                )
            else:
                monitors.append(
                    ModelMonitor.attach(
                        monitor_schedule_name=schedule_name,
                        sagemaker_session=self.sagemaker_session,
                    )
                )

        return monitors

    def _get_endpoint_config_name(self):
        """Placeholder docstring"""
        endpoint_desc = self.sagemaker_session.sagemaker_client.describe_endpoint(
            EndpointName=self.endpoint
        )
        endpoint_config_name = endpoint_desc["EndpointConfigName"]
        return endpoint_config_name

    def _get_model_names(self):
        """Placeholder docstring"""
        endpoint_config = self.sagemaker_session.sagemaker_client.describe_endpoint_config(
            EndpointConfigName=self._endpoint_config_name
        )
        production_variants = endpoint_config["ProductionVariants"]
        return map(lambda d: d["ModelName"], production_variants)


class _CsvSerializer(object):
    """Placeholder docstring"""

    def __init__(self):
        """Placeholder docstring"""
        self.content_type = CONTENT_TYPE_CSV

    def __call__(self, data):
        """Take data of various data formats and serialize them into CSV.

        Args:
            data (object): Data to be serialized.

        Returns:
            object: Sequence of bytes to be used for the request body.
        """
        # For inputs which represent multiple "rows", the result should be newline-separated CSV
        # rows
        if _is_mutable_sequence_like(data) and len(data) > 0 and _is_sequence_like(data[0]):
            return "\n".join([_CsvSerializer._serialize_row(row) for row in data])
        return _CsvSerializer._serialize_row(data)

    @staticmethod
    def _serialize_row(data):
        # Don't attempt to re-serialize a string
        """
        Args:
            data:
        """
        if isinstance(data, str):
            return data
        if isinstance(data, np.ndarray):
            data = np.ndarray.flatten(data)
        if hasattr(data, "__len__"):
            if len(data) == 0:
                raise ValueError("Cannot serialize empty array")
            return _csv_serialize_python_array(data)

        # files and buffers
        if hasattr(data, "read"):
            return _csv_serialize_from_buffer(data)

        raise ValueError("Unable to handle input format: ", type(data))


def _csv_serialize_python_array(data):
    """
    Args:
        data:
    """
    return _csv_serialize_object(data)


def _csv_serialize_from_buffer(buff):
    """
    Args:
        buff:
    """
    return buff.read()


def _csv_serialize_object(data):
    """
    Args:
        data:
    """
    csv_buffer = StringIO()

    csv_writer = csv.writer(csv_buffer, delimiter=",")
    csv_writer.writerow(data)
    return csv_buffer.getvalue().rstrip("\r\n")


csv_serializer = _CsvSerializer()


def _is_mutable_sequence_like(obj):
    """
    Args:
        obj:
    """
    return _is_sequence_like(obj) and hasattr(obj, "__setitem__")


def _is_sequence_like(obj):
    """
    Args:
        obj:
    """
    # Need to explicitly check on str since str lacks the iterable magic methods in Python 2
    return (  # pylint: disable=consider-using-ternary
        hasattr(obj, "__iter__") and hasattr(obj, "__getitem__")
    ) or isinstance(obj, str)


def _row_to_csv(obj):
    """
    Args:
        obj:
    """
    if isinstance(obj, str):
        return obj
    return ",".join(obj)


class _CsvDeserializer(object):
    """Placeholder docstring"""

    def __init__(self, encoding="utf-8"):
        """
        Args:
            encoding:
        """
        self.accept = CONTENT_TYPE_CSV
        self.encoding = encoding

    def __call__(self, stream, content_type):
        """
        Args:
            stream:
            content_type:
        """
        try:
            return list(csv.reader(stream.read().decode(self.encoding).splitlines()))
        finally:
            stream.close()


csv_deserializer = _CsvDeserializer()


class BytesDeserializer(object):
    """Return the response as an undecoded array of bytes.

    Args:
        accept (str): The Accept header to send to the server (optional).
    """

    def __init__(self, accept=None):
        """
        Args:
            accept:
        """
        self.accept = accept

    def __call__(self, stream, content_type):
        """
        Args:
            stream:
            content_type:
        """
        try:
            return stream.read()
        finally:
            stream.close()


class StringDeserializer(object):
    """Return the response as a decoded string.

    Args:
        encoding (str): The string encoding to use (default=utf-8).
        accept (str): The Accept header to send to the server (optional).
    """

    def __init__(self, encoding="utf-8", accept=None):
        """
        Args:
            encoding:
            accept:
        """
        self.encoding = encoding
        self.accept = accept

    def __call__(self, stream, content_type):
        """
        Args:
            stream:
            content_type:
        """
        try:
            return stream.read().decode(self.encoding)
        finally:
            stream.close()


class StreamDeserializer(object):
    """Returns the tuple of the response stream and the content-type of the response.
       It is the receivers responsibility to close the stream when they're done
       reading the stream.

    Args:
        accept (str): The Accept header to send to the server (optional).
    """

    def __init__(self, accept=None):
        """
        Args:
            accept:
        """
        self.accept = accept

    def __call__(self, stream, content_type):
        """
        Args:
            stream:
            content_type:
        """
        return (stream, content_type)


class _JsonSerializer(object):
    """Placeholder docstring"""

    def __init__(self):
        """Placeholder docstring"""
        self.content_type = CONTENT_TYPE_JSON

    def __call__(self, data):
        """Take data of various formats and serialize them into the expected
        request body. This uses information about supported input formats for
        the deployed model.

        Args:
            data (object): Data to be serialized.

        Returns:
            object: Serialized data used for the request.
        """
        if isinstance(data, dict):
            # convert each value in dict from a numpy array to a list if necessary, so they can be
            # json serialized
            return json.dumps({k: _ndarray_to_list(v) for k, v in six.iteritems(data)})

        # files and buffers
        if hasattr(data, "read"):
            return _json_serialize_from_buffer(data)

        return json.dumps(_ndarray_to_list(data))


json_serializer = _JsonSerializer()


def _ndarray_to_list(data):
    """
    Args:
        data:
    """
    return data.tolist() if isinstance(data, np.ndarray) else data


def _json_serialize_from_buffer(buff):
    """
    Args:
        buff:
    """
    return buff.read()


class _JsonDeserializer(object):
    """Placeholder docstring"""

    def __init__(self):
        """Placeholder docstring"""
        self.accept = CONTENT_TYPE_JSON

    def __call__(self, stream, content_type):
        """Decode a JSON object into the corresponding Python object.

        Args:
            stream (stream): The response stream to be deserialized.
            content_type (str): The content type of the response.

        Returns:
            object: Body of the response deserialized into a JSON object.
        """
        try:
            return json.load(codecs.getreader("utf-8")(stream))
        finally:
            stream.close()


json_deserializer = _JsonDeserializer()


class _NumpyDeserializer(object):
    """Placeholder docstring"""

    def __init__(self, accept=CONTENT_TYPE_NPY, dtype=None):
        """
        Args:
            accept:
            dtype:
        """
        self.accept = accept
        self.dtype = dtype

    def __call__(self, stream, content_type=CONTENT_TYPE_NPY):
        """Decode from serialized data into a Numpy array.

        Args:
            stream (stream): The response stream to be deserialized.
            content_type (str): The content type of the response. Can accept
                CSV, JSON, or NPY data.

        Returns:
            object: Body of the response deserialized into a Numpy array.
        """
        try:
            if content_type == CONTENT_TYPE_CSV:
                return np.genfromtxt(
                    codecs.getreader("utf-8")(stream), delimiter=",", dtype=self.dtype
                )
            if content_type == CONTENT_TYPE_JSON:
                return np.array(json.load(codecs.getreader("utf-8")(stream)), dtype=self.dtype)
            if content_type == CONTENT_TYPE_NPY:
                return np.load(BytesIO(stream.read()))
        finally:
            stream.close()
        raise ValueError(
            "content_type must be one of the following: CSV, JSON, NPY. content_type: {}".format(
                content_type
            )
        )


numpy_deserializer = _NumpyDeserializer()


class _NPYSerializer(object):
    """Placeholder docstring"""

    def __init__(self):
        """Placeholder docstring"""
        self.content_type = CONTENT_TYPE_NPY

    def __call__(self, data, dtype=None):
        """Serialize data into the request body in NPY format.

        Args:
            data (object): Data to be serialized. Can be a numpy array, list,
                file, or buffer.
            dtype:

        Returns:
            object: NPY serialized data used for the request.
        """
        if isinstance(data, np.ndarray):
            if not data.size > 0:
                raise ValueError("empty array can't be serialized")
            return _npy_serialize(data)

        if isinstance(data, list):
            if not len(data) > 0:
                raise ValueError("empty array can't be serialized")
            return _npy_serialize(np.array(data, dtype))

        # files and buffers. Assumed to hold npy-formatted data.
        if hasattr(data, "read"):
            return data.read()

        return _npy_serialize(np.array(data))


def _npy_serialize(data):
    """
    Args:
        data:
    """
    buffer = BytesIO()
    np.save(buffer, data)
    return buffer.getvalue()


npy_serializer = _NPYSerializer()

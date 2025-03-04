# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
from __future__ import absolute_import

import logging
import os

import pytest
from sagemaker.fw_registry import default_framework_uri

from sagemaker.processing import ProcessingInput, ProcessingOutput, ScriptProcessor, Processor
from sagemaker.sklearn.processing import SKLearnProcessor
from tests.integ import DATA_DIR
from tests.integ.kms_utils import get_or_create_kms_key

ROLE = "arn:aws:iam::142577830533:role/SageMakerRole"


@pytest.fixture(scope="module")
def image_uri(sagemaker_session):
    image_tag = "{}-{}-{}".format("0.20.0", "cpu", "py3")
    return default_framework_uri(
        "scikit-learn", sagemaker_session.boto_session.region_name, image_tag
    )


@pytest.fixture(scope="module")
def volume_kms_key(sagemaker_session):
    return get_or_create_kms_key(
        sagemaker_session=sagemaker_session,
        role_arn=ROLE,
        alias="integ-test-processing-volume-kms-key-{}".format(
            sagemaker_session.boto_session.region_name
        ),
    )


@pytest.fixture(scope="module")
def output_kms_key(sagemaker_session):
    return get_or_create_kms_key(
        sagemaker_session=sagemaker_session,
        role_arn=ROLE,
        alias="integ-test-processing-output-kms-key-{}".format(
            sagemaker_session.boto_session.region_name
        ),
    )


def test_sklearn(sagemaker_session, sklearn_full_version, cpu_instance_type):
    logging.getLogger().setLevel(logging.DEBUG)  # TODO-reinvent-2019: REMOVE

    script_path = os.path.join(DATA_DIR, "dummy_script.py")
    input_file_path = os.path.join(DATA_DIR, "dummy_input.txt")

    sklearn_processor = SKLearnProcessor(
        framework_version=sklearn_full_version,
        role=ROLE,
        instance_type=cpu_instance_type,
        instance_count=1,
        command=["python3"],
        sagemaker_session=sagemaker_session,
        max_runtime_in_seconds=3600,  # TODO-reinvent-2019: REMOVE
        base_job_name="test-sklearn",
    )

    sklearn_processor.run(
        code=script_path,
        inputs=[ProcessingInput(source=input_file_path, destination="/opt/ml/processing/inputs/")],
        wait=False,
        logs=False,
    )

    job_description = sklearn_processor.latest_job.describe()

    assert len(job_description["ProcessingInputs"]) == 2
    assert job_description["ProcessingResources"] == {
        "ClusterConfig": {"InstanceCount": 1, "InstanceType": "ml.m4.xlarge", "VolumeSizeInGB": 30}
    }
    assert job_description["StoppingCondition"] == {"MaxRuntimeInSeconds": 3600}
    assert job_description["AppSpecification"]["ContainerEntrypoint"] == [
        "python3",
        "/opt/ml/processing/input/code/dummy_script.py",
    ]
    assert job_description["RoleArn"] == ROLE


def test_sklearn_with_customizations(
    sagemaker_session, image_uri, sklearn_full_version, cpu_instance_type, output_kms_key
):
    input_file_path = os.path.join(DATA_DIR, "dummy_input.txt")

    sklearn_processor = SKLearnProcessor(
        framework_version=sklearn_full_version,
        role=ROLE,
        command=["python3"],
        instance_type=cpu_instance_type,
        instance_count=1,
        volume_size_in_gb=100,
        volume_kms_key=None,
        output_kms_key=output_kms_key,
        max_runtime_in_seconds=3600,
        base_job_name="test-sklearn-with-customizations",
        env={"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"},
        tags=[{"Key": "dummy-tag", "Value": "dummy-tag-value"}],
        sagemaker_session=sagemaker_session,
    )

    sklearn_processor.run(
        code=os.path.join(DATA_DIR, "dummy_script.py"),
        inputs=[
            ProcessingInput(
                source=input_file_path,
                destination="/opt/ml/processing/input/container/path/",
                input_name="dummy_input",
                s3_data_type="S3Prefix",
                s3_input_mode="File",
                s3_data_distribution_type="FullyReplicated",
                s3_compression_type="None",
            )
        ],
        outputs=[
            ProcessingOutput(
                source="/opt/ml/processing/output/container/path/",
                output_name="dummy_output",
                s3_upload_mode="EndOfJob",
            )
        ],
        arguments=["-v"],
        wait=True,
        logs=True,
    )

    job_description = sklearn_processor.latest_job.describe()

    assert job_description["ProcessingInputs"][0]["InputName"] == "dummy_input"

    assert job_description["ProcessingInputs"][1]["InputName"] == "code"

    assert job_description["ProcessingJobName"].startswith("test-sklearn-with-customizations")

    assert job_description["ProcessingJobStatus"] == "Completed"

    assert job_description["ProcessingOutputConfig"]["KmsKeyId"] == output_kms_key
    assert job_description["ProcessingOutputConfig"]["Outputs"][0]["OutputName"] == "dummy_output"

    assert job_description["ProcessingResources"] == {
        "ClusterConfig": {"InstanceCount": 1, "InstanceType": "ml.m4.xlarge", "VolumeSizeInGB": 100}
    }

    assert job_description["AppSpecification"]["ContainerArguments"] == ["-v"]
    assert job_description["AppSpecification"]["ContainerEntrypoint"] == [
        "python3",
        "/opt/ml/processing/input/code/dummy_script.py",
    ]
    assert job_description["AppSpecification"]["ImageUri"] == image_uri

    assert job_description["Environment"] == {"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"}

    assert job_description["RoleArn"] == ROLE

    assert job_description["StoppingCondition"] == {"MaxRuntimeInSeconds": 3600}


def test_sklearn_with_no_inputs_or_outputs(
    sagemaker_session, image_uri, sklearn_full_version, cpu_instance_type
):
    sklearn_processor = SKLearnProcessor(
        framework_version=sklearn_full_version,
        role=ROLE,
        command=["python3"],
        instance_type=cpu_instance_type,
        instance_count=1,
        volume_size_in_gb=100,
        volume_kms_key=None,
        max_runtime_in_seconds=3600,
        base_job_name="test-sklearn-with-no-inputs-or-outputs",
        env={"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"},
        tags=[{"Key": "dummy-tag", "Value": "dummy-tag-value"}],
        sagemaker_session=sagemaker_session,
    )

    sklearn_processor.run(
        code=os.path.join(DATA_DIR, "dummy_script.py"), arguments=["-v"], wait=True, logs=True
    )

    job_description = sklearn_processor.latest_job.describe()

    assert job_description["ProcessingInputs"][0]["InputName"] == "code"

    assert job_description["ProcessingJobName"].startswith("test-sklearn-with-no-inputs")

    assert job_description["ProcessingJobStatus"] == "Completed"

    assert job_description["ProcessingResources"] == {
        "ClusterConfig": {"InstanceCount": 1, "InstanceType": "ml.m4.xlarge", "VolumeSizeInGB": 100}
    }

    assert job_description["AppSpecification"]["ContainerArguments"] == ["-v"]
    assert job_description["AppSpecification"]["ContainerEntrypoint"] == [
        "python3",
        "/opt/ml/processing/input/code/dummy_script.py",
    ]
    assert job_description["AppSpecification"]["ImageUri"] == image_uri

    assert job_description["Environment"] == {"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"}

    assert job_description["RoleArn"] == ROLE

    assert job_description["StoppingCondition"] == {"MaxRuntimeInSeconds": 3600}


def test_script_processor(sagemaker_session, image_uri, cpu_instance_type, output_kms_key):
    input_file_path = os.path.join(DATA_DIR, "dummy_input.txt")

    script_processor = ScriptProcessor(
        role=ROLE,
        image_uri=image_uri,
        command=["python3"],
        instance_count=1,
        instance_type=cpu_instance_type,
        volume_size_in_gb=100,
        volume_kms_key=None,
        output_kms_key=output_kms_key,
        max_runtime_in_seconds=3600,
        base_job_name="test-script-processor",
        env={"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"},
        tags=[{"Key": "dummy-tag", "Value": "dummy-tag-value"}],
        sagemaker_session=sagemaker_session,
    )

    script_processor.run(
        code=os.path.join(DATA_DIR, "dummy_script.py"),
        inputs=[
            ProcessingInput(
                source=input_file_path,
                destination="/opt/ml/processing/input/container/path/",
                input_name="dummy_input",
                s3_data_type="S3Prefix",
                s3_input_mode="File",
                s3_data_distribution_type="FullyReplicated",
                s3_compression_type="None",
            )
        ],
        outputs=[
            ProcessingOutput(
                source="/opt/ml/processing/output/container/path/",
                output_name="dummy_output",
                s3_upload_mode="EndOfJob",
            )
        ],
        arguments=["-v"],
        wait=True,
        logs=True,
    )

    job_description = script_processor.latest_job.describe()

    assert job_description["ProcessingInputs"][0]["InputName"] == "dummy_input"

    assert job_description["ProcessingInputs"][1]["InputName"] == "code"

    assert job_description["ProcessingJobName"].startswith("test-script-processor")

    assert job_description["ProcessingJobStatus"] == "Completed"

    assert job_description["ProcessingOutputConfig"]["KmsKeyId"] == output_kms_key
    assert job_description["ProcessingOutputConfig"]["Outputs"][0]["OutputName"] == "dummy_output"

    assert job_description["ProcessingResources"] == {
        "ClusterConfig": {"InstanceCount": 1, "InstanceType": "ml.m4.xlarge", "VolumeSizeInGB": 100}
    }

    assert job_description["AppSpecification"]["ContainerArguments"] == ["-v"]
    assert job_description["AppSpecification"]["ContainerEntrypoint"] == [
        "python3",
        "/opt/ml/processing/input/code/dummy_script.py",
    ]
    assert job_description["AppSpecification"]["ImageUri"] == image_uri

    assert job_description["Environment"] == {"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"}

    assert job_description["RoleArn"] == ROLE

    assert job_description["StoppingCondition"] == {"MaxRuntimeInSeconds": 3600}


def test_script_processor_with_no_inputs_or_outputs(
    sagemaker_session, image_uri, cpu_instance_type
):
    script_processor = ScriptProcessor(
        role=ROLE,
        image_uri=image_uri,
        command=["python3"],
        instance_count=1,
        instance_type=cpu_instance_type,
        volume_size_in_gb=100,
        volume_kms_key=None,
        max_runtime_in_seconds=3600,
        base_job_name="test-script-processor-with-no-inputs-or-outputs",
        env={"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"},
        tags=[{"Key": "dummy-tag", "Value": "dummy-tag-value"}],
        sagemaker_session=sagemaker_session,
    )

    script_processor.run(
        code=os.path.join(DATA_DIR, "dummy_script.py"), arguments=["-v"], wait=True, logs=True
    )

    job_description = script_processor.latest_job.describe()

    assert job_description["ProcessingInputs"][0]["InputName"] == "code"

    assert job_description["ProcessingJobName"].startswith("test-script-processor-with-no-inputs")

    assert job_description["ProcessingJobStatus"] == "Completed"

    assert job_description["ProcessingResources"] == {
        "ClusterConfig": {"InstanceCount": 1, "InstanceType": "ml.m4.xlarge", "VolumeSizeInGB": 100}
    }

    assert job_description["AppSpecification"]["ContainerArguments"] == ["-v"]
    assert job_description["AppSpecification"]["ContainerEntrypoint"] == [
        "python3",
        "/opt/ml/processing/input/code/dummy_script.py",
    ]
    assert job_description["AppSpecification"]["ImageUri"] == image_uri

    assert job_description["Environment"] == {"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"}

    assert job_description["RoleArn"] == ROLE

    assert job_description["StoppingCondition"] == {"MaxRuntimeInSeconds": 3600}


def test_processor(sagemaker_session, image_uri, cpu_instance_type, output_kms_key):
    script_path = os.path.join(DATA_DIR, "dummy_script.py")

    processor = Processor(
        role=ROLE,
        image_uri=image_uri,
        instance_count=1,
        instance_type=cpu_instance_type,
        entrypoint=["python3", "/opt/ml/processing/input/code/dummy_script.py"],
        volume_size_in_gb=100,
        volume_kms_key=None,
        output_kms_key=output_kms_key,
        max_runtime_in_seconds=3600,
        base_job_name="test-processor",
        env={"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"},
        tags=[{"Key": "dummy-tag", "Value": "dummy-tag-value"}],
        sagemaker_session=sagemaker_session,
    )

    processor.run(
        inputs=[
            ProcessingInput(
                source=script_path, destination="/opt/ml/processing/input/code/", input_name="code"
            )
        ],
        outputs=[
            ProcessingOutput(
                source="/opt/ml/processing/output/container/path/",
                output_name="dummy_output",
                s3_upload_mode="EndOfJob",
            )
        ],
        arguments=["-v"],
        wait=True,
        logs=True,
    )

    job_description = processor.latest_job.describe()

    assert job_description["ProcessingInputs"][0]["InputName"] == "code"

    assert job_description["ProcessingJobName"].startswith("test-processor")

    assert job_description["ProcessingJobStatus"] == "Completed"

    assert job_description["ProcessingOutputConfig"]["KmsKeyId"] == output_kms_key
    assert job_description["ProcessingOutputConfig"]["Outputs"][0]["OutputName"] == "dummy_output"

    assert job_description["ProcessingResources"] == {
        "ClusterConfig": {"InstanceCount": 1, "InstanceType": "ml.m4.xlarge", "VolumeSizeInGB": 100}
    }

    assert job_description["AppSpecification"]["ContainerArguments"] == ["-v"]
    assert job_description["AppSpecification"]["ContainerEntrypoint"] == [
        "python3",
        "/opt/ml/processing/input/code/dummy_script.py",
    ]
    assert job_description["AppSpecification"]["ImageUri"] == image_uri

    assert job_description["Environment"] == {"DUMMY_ENVIRONMENT_VARIABLE": "dummy-value"}

    assert job_description["RoleArn"] == ROLE

    assert job_description["StoppingCondition"] == {"MaxRuntimeInSeconds": 3600}

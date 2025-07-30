# kube-custom-resource

This package provides utilities for working with
[Kubernetes custom resources](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/)
in [Python](https://www.python.org/), e.g. when implementing the
[operator pattern](https://kubernetes.io/docs/concepts/extend-kubernetes/operator/).

In particular, it provides a set of types that build on
[Pydantic](https://docs.pydantic.dev/latest/) and generate schemas that are compatible with the
[Kubernetes OpenAPI implementation](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#validation).

It also includes utilities to discover your custom resource models and produce the
`CustomResourceDefinition`s required to enrol them with the Kubernetes API server.

This documentation assumes you are familiar with Kubernetes custom resource definitions.

## Defining custom resources

To define your custom resources, simply build your models by extending the `CustomResource`
base class and define attributes as you would with any other Pydantic model, using the special
types from the `schema` module where required. Please consult the Pydantic documentation for
different ways of defining model attributes.

The version can be specified at class creation time, however if it is not given the model
will attempt to derive it from the module name. For example, if your model is in a module
called `myproject.models.v1alpha1.resource` then `CustomResource` would pick `v1alpha1` for the
version unless specified otherwise. This is useful if you have several models that should
use the same version.

In the following Python code, we will implement a `CustomResource` for objects like this:

```yaml
apiVersion: cron.example.com/v1alpha1
kind: CronJob
metadata:
  name: example-cronjob
  namespace: my-namespace
spec:
  schedule: "0 12 * * *"
  jobTemplate:
    image: busybox
    command:
      - /bin/sh
      - -c
      - date; echo Hello from the cronjob
  # This field is optional with a default value of false
  paused: true
  # This field is optional with a default value of 3
  successfulJobsHistoryLimit: 3
status:
  lastScheduleTime: "2025-07-25T12:00:00Z"
  activeJobs:
    - name: cronjob-abcde
      startTime: "2025-07-25T12:00:01Z"
```

```python
import datetime as dt
import typing

import annotated_types as at
from pydantic import Field

from kube_custom_resource import CustomResource, Scope, schema


Command = typing.Annotated[
    typing.List[schema.constr(min_length=1)],
    at.Len(min_length = 1)
]


class JobTemplate(schema.BaseModel):
    """
    The job template for a cronjob.
    """
    image: schema.constr(min_length=1) = Field(
        ..., # Required
        description="The image to use for jobs."
    )
    command: Command = Field(
        ...,
        description="The command to execute for jobs."
    )


class CronJobSpec(schema.BaseModel):
    """
    The spec for a cronjob.
    """
    # Could use pattern="<regex>" to do a tighter validation
    schedule: schema.constr(min_length=1) = Field(
        ...,
        description="The schedule the cronjob should run with."
    )
    job_template: JobTemplate = Field(
        ...,
        description="The template for jobs produced by the cronjob."
    )
    paused: bool = Field(
        False, # Default value
        description="Indicates whether the cronjob is paused."
    )
    successful_jobs_history_limit: schema.conint(gt=0) = Field(
        3,
        description="The number of successful jobs to keep."
    )


class ActiveJob(schema.BaseModel):
    """
    Represents an active job for a cronjob.
    """
    name: schema.constr(min_length=1) = Field(
        ...,
        description="The name of the job."
    )
    start_time: dt.datetime = Field(
        ...,
        description="The start time of the job."
    )


class CronJobStatus(schema.BaseModel):
    """
    The status for a cronjob.
    """
    last_schedule_time: schema.Optional[dt.datetime] = Field(
        None,
        description="The last time that a job was scheduled."
    )
    active_jobs: typing.List[ActiveJob] = Field(
        default_factory=list,
        description="The list of active jobs for the cronjob."
    )


class CronJob(
    CustomResource,
    # Define a subresource for the status
    # This can also be used to add a scale subresource if you want to support that
    subresources={"status": {}},
    # Define printer columns for the resource, used when doing "kubectl get <resource>"
    printer_columns=[
        {
            "name": "Schedule",
            "type": "string",
            "jsonPath": ".spec.schedule",
        },
        {
            "name": "Paused",
            "type": "boolean",
            "jsonPath": ".spec.paused",
        },
        {
            "name": "Last Schedule Time",
            "type": "string",
            "jsonPath": ".status.lastScheduleTime",
        },
    ],
    # The scope of the custom resource, either NAMESPACED or CLUSTER
    # Defaults to NAMESPACED if not given
    scope=Scope.NAMESPACED,
    # Names for the resource
    # By default, these are derived from the class name
    kind="CronJob",           # Defaults to the class name
    singular_name="cronjob",  # Defaults to the lower-cased kind
    plural_name="cronjobs"    # Defaults to the singular name + "s"
):
    """
    Custom resource representing a cronjob.
    """
    spec: CronJobSpec
    status: CronJobStatus = Field(default_factory=CronJobStatus)
```

## Producing definitions for Kubernetes

Once our models are defined, we need to produce `CustomResourceDefinition`s to register the
resources with the Kubernetes API.

This is done using a registry and the Kubernetes client of your choice:

```python
import kube_custom_resource as kcr

from . import models


registry = kcr.CustomResourceRegistry("myoperator.example.org", ["myoperator"])
registry.discover_models(models)
for crd in registry:
    # Create a Python dict containing the CustomResourceDefinition
    obj = crd.kubernetes_resource()
    # apply obj to cluster using your favourite Kubernetes client
    # ...
```

Alternatively, `kube-custom-resource` provides a command that can be used to generate YAML files:

```sh
kcr_generate <models module> <api group> <output directory>
```

e.g.:

```sh
kcr_generate myoperator.models myoperator.example.org ./crds
```

This can be done as part of a build step and then the CRDs can be baked into a Helm chart or
uploaded as a release artifact.

## Custom types

The `schema` module defines several custom types for use in custom resource models. Some are
special types for use with Kubernetes specifically (e.g. `IntOrString`) and some are
customisations of types from `typing` that have been modified to produce Kubernetes-compliant
OpenAPI schemas.

### `BaseModel`

Subclass of Pydantic's `BaseModel` that should be used by all models that are part of a custom
resource. Ensures that Kubernetes-compatible schemas are generated.

### `Any`

Annotated version of `typing.Any` that ensures the generated schema includes
`x-kubernetes-preserve-unknown-fields: true`.

### `Dict`

Annotated version of `dict` / `typing.Dict` that ensures the generated schema includes
`x-kubernetes-preserve-unknown-fields: true`.

### `Enum`

Subclass of [enum.Enum](https://docs.python.org/3/library/enum.html#enum.Enum) that ensures
the generated schema is Kubernetes-compatible.

### `Optional`

Annotated version of `typing.Optional` that produces Kubernetes-compatible schemas by rewriting
schemas to use `nullable` instead of the `anyOf` based schemas generated by Pydantic.

### `confloat`

Constructor that produces constrained `float` types.

The following parameters are supported:

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `strict` | `bool \| None` | Whether to use strict mode when validating. | `None` |
| `gt` | `float \| None` | The value must be greater than this. | `None` |
| `ge` | `float \| None` | The value must be greater than or equal to this. | `None` |
| `lt` | `float \| None` | The value must be less than this. | `None` |
| `le` | `float \| None` | The value must be less than or equal to this. | `None` |
| `multiple_of` | `float \| None` | The value must be a multiple of this. | `None` |
| `allow_inf_nan` | `bool \| None` | Whether to allow `-inf`, `inf` and `nan`. | `None` |

###  `conint`

Constructor that produces constrained `int` types.

The following parameters are supported:

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `strict` | `bool \| None` | Whether to use strict mode when validating. | `None` |
| `gt` | `int \| None` | The value must be greater than this. | `None` |
| `ge` | `int \| None` | The value must be greater than or equal to this. | `None` |
| `lt` | `int \| None` | The value must be less than this. | `None` |
| `le` | `int \| None` | The value must be less than or equal to this. | `None` |
| `multiple_of` | `int \| None` | The value must be a multiple of this. | `None` |

### `constr`

Constructor that produces constrained `str` types.

The following parameters are supported:

| Name | Type | Description | Default |
|------|------|-------------|---------|
| `strip_whitespace` | `bool \| None` | Whether to remove leading and trailing whitespace. | `None` |
| `to_upper` | `bool \| None` | Whether to convert the string to uppercase. | `None` |
| `to_lower` | `bool \| None` | Whether to convert the string to lowercase. | `None` |
| `strict` | `bool \| None` | Whether to validate the string in strict mode. | `None` |
| `min_length` | `int \| None` | The minimum length of the string. | `None` |
| `max_length` | `int \| None` | The maximum length of the string. | `None` |
| `pattern` | `str \| regex \| None` | A regex pattern that the string must match. | `None` |

### `AnyHttpUrl`

Type that validates a string as a HTTP URL.

### `AnyUrl`

Type that validates a string as a URL of any type.

### `IntOrString`

Annotated version of `str` that ensures the generated schema includes
`x-kubernetes-int-or-string: true`, allowing either an integer or a string to be specified
when a resource is created.

During validation, the value is always coerced to a string even if an integer is given.

### `StructuralUnion`

Annotation type for defining "structural unions", that allow the representation of objects
like this:

```yaml
apiVersion: example.com/v1alpha1
kind: ConfigurableObject
metadata:
  name: configurable-obj
spec:
  configSources:
    - configMap:
        name: configmap-1
        key: key-1
    - secret:
        name: secret-1
        key: key-2
    - inline: |
        some
        inline
        config
```

using code like this:

```python
# Define different models for the different ways config sources can be specified
class ConfigSourceNameKey(schema.BaseModel):
    name: schema.constr(pattern=r"^[a-z0-9-]+$")
    key: schema.constr(min_length=1)

class ConfigMapConfigSource(schema.BaseModel):
    config_map: ConfigSourceNameKey

class SecretConfigSource(schema.BaseModel):
    secret: ConfigSourceNameKey

class InlineConfigSource(schema.BaseModel):
    inline: schema.constr(min_length=1)


# Define a union of the types and annotate it as a structural union so that the
# schema is generated correctly for Kubernetes
ConfigSource = t.Annotated[
    ConfigMapConfigSource | SecretConfigSource | InlineConfigSource,
    schema.StructuralUnion,
]


# Use the union to define the list of config sources
class ConfigurableObjectSpec(schema.BaseModel):
    config_sources: list[ConfigSource] = Field(default_factory=list)

class ConfigurableObject(CustomResource):
    spec: ConfigurableObjectSpec
```

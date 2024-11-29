import dataclasses
import datetime
import re
import typing

from pydantic_core import CoreSchema

from pydantic import Field, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue

from .schema import BaseModel, Enum


#: Regex used for extracting versions from module names
VERSION_REGEX = re.compile(r"^v\d+((alpha|beta)\d+)?$")


class Scope(str, Enum):
    """
    Enum representing the possible scopes for a custom resource.
    """
    CLUSTER    = "Cluster"
    NAMESPACED = "Namespaced"


@dataclasses.dataclass
class CustomResourceMeta:
    """
    Dataclass to hold metadata for the custom resource.
    """
    # The API subgroup for the custom resource
    api_subgroup: typing.Optional[str]
    # The version of the custom resource
    version: str
    # The scope of the custom resource
    scope: Scope
    # The kind of the resource
    kind: str
    # The singular name of the resource
    singular_name: str
    # The plural name of the resource
    plural_name: str
    # A list of short names for the resource
    short_names: typing.List[str]
    # The subresources for the CRD
    subresources: typing.Dict[str, typing.Any]
    # A list of printer column definitions for the version
    printer_columns: typing.List[typing.Dict[str, typing.Any]]
    # Indicates if this is the storage version
    storage_version: bool


class CustomResourceMetaclass(type(BaseModel)):
    """
    Metaclass for the custom resource class.
    """
    def __new__(
        cls,
        name,
        bases,
        attrs,
        /,
        # Indicates that the resource is abstract and is not actually a CRD
        abstract: bool = False,
        # The API subgroup for the custom resource
        # If not given, the resource is placed in the root api group
        api_subgroup: typing.Optional[str] = None,
        # The version of the custom resource
        # If not given, it is inferred from the module if possible
        version: typing.Optional[str] = None,
        # The scope of the resource, either 'Namespaced' or 'Cluster'
        # If not given, Namespaced is used by default
        scope: Scope = Scope.NAMESPACED,
        # The kind of the resource
        # If not given, the model class name is used
        kind: typing.Optional[str] = None,
        # The singular name of the resource
        # If not given, the lower-cased kind is used
        singular_name: typing.Optional[str] = None,
        # The plural name of the resource
        # If not given, the singular name with 's' appended is used
        plural_name: typing.Optional[str] = None,
        # A list of short names for the resource
        # If not given, no short names are used
        short_names: typing.Optional[typing.List[str]] = None,
        # The subresources for the CRD
        # If not given, no subresources are defined
        subresources: typing.Optional[typing.Dict[str, typing.Any]] = None,
        # A list of printer column definitions for the version
        # An "age" column is always appended to the given list
        printer_columns: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None,
        # Indicates if this is the storage version
        storage_version: bool = True,
        # Other kwargs, passed to Pydantic
        **kwargs
    ):
        if not abstract:
            # If no version is given, find the first module component that looks like a version
            if not version:
                version = next(
                    part
                    for part in reversed(attrs["__module__"].split("."))
                    if VERSION_REGEX.match(part)
                )
            # Derive any names that were't given from the ones that were
            kind = kind or name
            singular_name = singular_name or kind.lower()
            plural_name = plural_name or f"{singular_name}s"
            # Add the metadata to the attrs
            # We also add an annotation so that Pydantic leaves it alone
            attrs.setdefault("__annotations__", {})["_meta"] = typing.ClassVar[CustomResourceMeta]
            attrs["_meta"] = CustomResourceMeta(
                api_subgroup,
                version,
                scope,
                kind,
                singular_name,
                plural_name,
                short_names or [],
                subresources or {},
                (printer_columns or []) + [
                    {
                        "name": "Age",
                        "type": "date",
                        "jsonPath": ".metadata.creationTimestamp",
                    },
                ],
                storage_version
            )
        return super().__new__(cls, name, bases, attrs, **kwargs)


class OwnerReference(BaseModel):
    """
    Model for an owner reference.
    """
    api_version: str = Field(
        ...,
        description = "The API version of the owner."
    )
    kind: str = Field(
        ...,
        description = "The kind of the owner."
    )
    name: str = Field(
        ...,
        description = "The name of the owner."
    )
    uid: str = Field(
        ...,
        description = "The UID of the owner."
    )
    block_owner_deletion: bool = Field(
        False,
        description = "If true, the owner cannot be removed until this resource is removed."
    )
    controller: bool = Field(
        False,
        description = "Indicates if this resource points to the managing controller."
    )


class Metadata(BaseModel):
    """
    Model for the metadata associated with a resource instance.
    """
    name: str = Field(
        ...,
        description = "The name of the resource."
    )
    namespace: typing.Optional[str] = Field(
        None,
        description = "The namespace for the resource."
    )
    labels: typing.Dict[str, str] = Field(
        default_factory = dict,
        description = "The labels for the resource. Can be used to match selectors."
    )
    annotations: typing.Dict[str, str] = Field(
        default_factory = dict,
        description = "Annotations for the resource. Can be used to store arbitrary metadata."
    )
    owner_references: typing.List[OwnerReference] = Field(
        default_factory = list,
        description = "List of resources that this resource depends on."
    )
    finalizers: typing.List[str] = Field(
        default_factory = list,
        description = "List of identifiers blocking removal of the resource."
    )
    uid: typing.Optional[str] = Field(
        None,
        description = "The UID for the resource."
    )
    creation_timestamp: typing.Optional[datetime.datetime] = Field(
        None,
        description = "The timestamp at which the resource was created."
    )
    deletion_timestamp: typing.Optional[datetime.datetime] = Field(
        None,
        description = "The timestamp at which the resource was deleted."
    )
    resource_version: typing.Optional[str] = Field(
        None,
        description = (
            "The internal version of the resource. "
            "Used to implement optimistic concurrency and resumable watches."
        )
    )

    def add_owner_reference(self, owner, /, block_owner_deletion = False, controller = False):
        """
        Adds the given owner as a reference if it doesn't already exist.

        Returns True if a new reference was added, False otherwise.
        """
        if any(ref.uid == owner.metadata.uid for ref in self.owner_references):
            # Reference already exists - nothing to do
            return False
        else:
            self.owner_references.append(
                OwnerReference(
                    api_version = owner["apiVersion"],
                    kind = owner["kind"],
                    name = owner["metadata"]["name"],
                    uid = owner["metadata"]["uid"],
                    block_owner_deletion = block_owner_deletion,
                    controller = controller
                )
            )
            return True


class CustomResource(
    BaseModel,
    metaclass = CustomResourceMetaclass,
    abstract = True
):
    """
    Base class for defining custom resources.
    """
    api_version: str = Field(
        ...,
        description = "The API version of the resource."
    )
    kind: str = Field(
        ...,
        description = "The kind of the resource."
    )
    metadata: Metadata = Field(
        ...,
        description = "The metadata for the resource."
    )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        # Remove the API version, kind and metadata from the schema as they are
        # not required for a valid CRD
        for key in ["apiVersion", "kind", "metadata"]:
            json_schema["properties"].pop(key)
            json_schema["required"].remove(key)
        return json_schema

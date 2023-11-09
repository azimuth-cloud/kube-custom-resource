import enum
import typing as t

import annotated_types

from pydantic_core import CoreSchema, core_schema

from pydantic import (
    BaseModel as PydanticModel,
    TypeAdapter,
    AnyUrl as PydanticAnyUrl,
    AnyHttpUrl as PydanticAnyHttpUrl,
    TypeAdapter,
    StringConstraints,
    AllowInfNan,
    Strict,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler
)
from pydantic.json_schema import JsonSchemaValue


def schema_apply(schema, func, pre = False):
    """
    Return a new schema that is the result of recursively applying the given function
    to the given schema and all subschemas.

    The function itself can be applied to the given schema either before or after
    it is applied to the subschemas.
    """
    schema_new = schema.copy()
    # Check if we need to apply the function before recursing
    if pre:
        schema_new = func(schema_new)
    # For object schemas, we need to apply the function to each of the property schemas
    if schema_new.get("type") == "object":
        if "properties" in schema_new:
            schema_new["properties"] = {
                prop_name: schema_apply(prop_schema, func, pre)
                for prop_name, prop_schema in schema_new["properties"].items()
            }
        # Additional properties can be the boolean "true"
        # If it is a dict, then it is the schema for the additional properties
        additional_properties = schema_new.get("additionalProperties")
        if isinstance(additional_properties, dict):
            schema_new["additionalProperties"] = schema_apply(additional_properties, func, pre)
    # For array schemas, we need to apply the function to the schema for items
    elif schema_new.get("type") == "array":
        if "items" in schema_new:
            schema_new["items"] = schema_apply(schema_new["items"], func, pre)
    # For anyOf, allOf and oneOf, we need to apply the function to each schema
    elif "anyOf" in schema_new:
        schema_new["anyOf"] = [schema_apply(s, func, pre) for s in schema_new["anyOf"]]
    elif "allOf" in schema_new:
        schema_new["allOf"] = [schema_apply(s, func, pre) for s in schema_new["allOf"]]
    elif "oneOf" in schema_new:
        schema_new["oneOf"] = [schema_apply(s, func, pre) for s in schema_new["oneOf"]]
    # not is a single schema
    elif "not" in schema_new:
        schema_new["not"] = schema_apply(schema_new["not"], func, pre)
    # Finally, apply the function to the schema itself if required
    return schema_new if pre else func(schema_new)


def resolve_refs(schema):
    """
    Recursively resolve $refs in the given schema.
    """
    schema_new = schema.copy()
    definitions = schema_new.pop("$defs", {})

    def func(schema):
        schema_new = schema.copy()
        # If the schema has an allOf with a single item, collapse it
        if "allOf" in schema_new and len(schema_new["allOf"]) == 1:
            schema_new.update(schema_new.pop("allOf")[0])
        # If the schema has a ref, resolve it
        if "$ref" in schema_new:
            # If the schema is a ref schema, resolve the ref
            ref = schema_new.pop("$ref").removeprefix("#/$defs/")
            schema_new.update(definitions[ref])
        return schema_new

    # Apply the function to each schema _before_ recursing
    # This ensures that refs are recursed into correctly
    return schema_apply(schema_new, func, pre = True)


def remove_fields(schema, *fields):
    """
    Recursively remove the specified fields from all the types in the schema.
    """
    return schema_apply(schema, lambda s: { k: v for k, v in s.items() if k not in fields })


def snake_to_pascal(name):
    """
    Converts a snake case name to pascalCase.
    """
    first, *rest = name.split("_")
    return "".join([first] + [part.capitalize() for part in rest])


class Enum(enum.Enum):
    """
    Enum that does not include a title in the JSON-Schema.
    """
    def __str__(self):
        return str(self.value)

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.pop("title", None)
        return json_schema


class XKubernetesPreserveUnknownFields:
    """
    Type annotation that adds the x-kubernetes-preserve-unknown-fields property
    to the generated schema.
    """
    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["x-kubernetes-preserve-unknown-fields"] = True
        return json_schema


Any = t.Annotated[t.Any, XKubernetesPreserveUnknownFields]


KeyT = t.TypeVar("KeyT")
ValueT = t.TypeVar("ValueT")
Dict = t.Annotated[t.Dict[KeyT, ValueT], XKubernetesPreserveUnknownFields]


class XKubernetesIntOrString:
    """
    Type annotation that adds the x-kubernetes-int-or-string property to the generated schema.
    """
    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: t.Any,
        handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        # Validate the value as a union of int and str, but convert to a string after
        return core_schema.no_info_after_validator_function(
            str,
            handler.generate_schema(t.Union[str, int])
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        # Replace the anyOf generated by the union with the special Kubernetes property
        json_schema.pop("anyOf", None)
        json_schema["x-kubernetes-int-or-string"] = True
        return json_schema


IntOrString = t.Annotated[str, XKubernetesIntOrString]


def constr(**kwargs):
    return t.Annotated[str, StringConstraints(**kwargs)]


class ValidateStrAs:
    """
    Type annotation that allows a str to be annotated with validation from another type.
    """
    def __init__(self, validation_type):
        self.validation_type = validation_type
        self.type_adapter = TypeAdapter(self.validation_type)

    def __get_pydantic_core_schema__(
        self,
        source_type: t.Any,
        handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        # Validate the value as the given validation type, but convert back to a string after
        json_schema = core_schema.no_info_after_validator_function(
            str,
            handler.generate_schema(self.validation_type)
        )
        return core_schema.json_or_python_schema(
            json_schema = json_schema,
            python_schema = json_schema,
            # When serializing, just use the string
            serialization = core_schema.plain_serializer_function_ser_schema(lambda x: x)
        )


AnyUrl = t.Annotated[str, ValidateStrAs(PydanticAnyUrl)]
AnyHttpUrl = t.Annotated[str, ValidateStrAs(PydanticAnyHttpUrl)]


class _ConvertExclusiveMinMax:
    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        exclusive_min = json_schema.pop("exclusiveMinimum", None)
        if exclusive_min is not None:
            json_schema.update({
                "minimum": exclusive_min,
                "exclusiveMinimum": True,
            })
        exclusive_max = json_schema.pop("exclusiveMaximum", None)
        if exclusive_max is not None:
            json_schema.update({
                "maximum": exclusive_max,
                "exclusiveMaximum": True,
            })
        return json_schema


def conint(
    *,
    strict: t.Optional[bool] = None,
    gt: t.Optional[int] = None,
    ge: t.Optional[int] = None,
    lt: t.Optional[int] = None,
    le: t.Optional[int] = None,
    multiple_of: t.Optional[int] = None
) -> t.Type[int]:
    return t.Annotated[
        int,
        Strict(strict) if strict is not None else None,
        annotated_types.Interval(gt = gt, ge = ge, lt = lt, le = le),
        annotated_types.MultipleOf(multiple_of) if multiple_of is not None else None,
        _ConvertExclusiveMinMax,
    ]


def confloat(
    *,
    strict: t.Optional[bool] = None,
    gt: t.Optional[float] = None,
    ge: t.Optional[float] = None,
    lt: t.Optional[float] = None,
    le: t.Optional[float] = None,
    multiple_of: t.Optional[float] = None,
    allow_inf_nan: t.Optional[bool] = None,
) -> t.Type[float]:
    return t.Annotated[
        float,
        Strict(strict) if strict is not None else None,
        annotated_types.Interval(gt = gt, ge = ge, lt = lt, le = le),
        annotated_types.MultipleOf(multiple_of) if multiple_of is not None else None,
        AllowInfNan(allow_inf_nan) if allow_inf_nan is not None else None,
        _ConvertExclusiveMinMax,
    ]


class Nullable:
    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # We don't want to produce the anyOf schema that Optional would normally produce,
        # as it is not valid OpenAPI
        # Instead, we want to produce the schema for the wrapped type with nullable set
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        any_of = json_schema.pop("anyOf")
        non_null_schema = next(s for s in any_of if s.get("type") != "null")
        json_schema.update(non_null_schema)
        json_schema["nullable"] = True
        return json_schema


OptionalT = t.TypeVar("OptionalT")
Optional = t.Annotated[t.Optional[OptionalT], Nullable]


class StructuralUnion:
    """
    Type annotation for a structural union, i.e. a union with a structural schema.

    See https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#specifying-a-structural-schema.
    """
    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # We only support structural union schemas for unions (obvs!)
        assert core_schema["type"] == "union"
        # Build the anyOf using the fully-resolved schemas of the individual types
        any_of = []
        properties = {}
        for choice_schema in core_schema.get("choices", []):
            if choice_schema["type"] == "model":
                # For models, we need the fully resolved schema to do the rest of the ops
                # The handler only gives us a ref schema
                adapter = TypeAdapter(choice_schema["cls"])
                choice_json_schema = resolve_refs(adapter.json_schema())
            else:
                choice_json_schema = handler.resolve_ref_schema(handler(choice_schema))
            # In order to qualify as a structural schema, the schema of the union itself
            # must include all the possible properties
            properties.update(choice_json_schema.get("properties", {}))
            # Schemas in anyOf are not permitted to contain particular keys
            choice_json_schema = remove_fields(
                choice_json_schema,
                "type",
                "title",
                "description",
                "default",
                "additionalProperties",
                "nullable",
                "x-kubernetes-preserve-unknown-fields",
            )
            any_of.append(choice_json_schema)
        return {
            "type": "object",
            "properties": properties,
            "anyOf": any_of,
        }


class BaseModel(
    PydanticModel,
    alias_generator = snake_to_pascal,
    populate_by_name = True,
    # Validate any mutations to the model
    frozen = False,
    validate_assignment = True
):
    """
    Base model for use within CRD definitions.
    """
    def model_dump(self, **kwargs):
        # Unless otherwise specified, we want by_alias = True
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        # Unless otherwise specified, we want by_alias = True
        kwargs.setdefault("by_alias", True)
        return super().model_dump_json(**kwargs)

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = super().__get_pydantic_json_schema__(core_schema, handler)
        #####
        # Post-process the generated schema to make it compatible with a Kubernetes CRD
        #####
        # When extra fields are allowed, stop Kubernetes pruning them
        if cls.model_config.get("extra") == "allow":
            json_schema["x-kubernetes-preserve-unknown-fields"] = True
        return json_schema

    @classmethod
    def model_json_schema(cls, *args, include_defaults = False, **kwargs):
        json_schema = super().model_json_schema(*args, **kwargs)
        # Resolve all the refs
        json_schema = resolve_refs(json_schema)
        # Remove the titles
        fields_to_remove = ["title"]
        # Unless explicitly included, we remove defaults from the schema as they cause
        # Kubernetes to rewrite objects
        # In most cases, it is better that defaults are applied at model instantiation time
        # as rewriting the Kubernetes objects themselves can have unintended side-effects
        # However in some cases it is more appropriate for the defaults to be "locked in" at
        # creation time
        if not include_defaults:
            fields_to_remove.append("default")
        return remove_fields(json_schema, *fields_to_remove)

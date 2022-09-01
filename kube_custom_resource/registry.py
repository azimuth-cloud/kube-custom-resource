import dataclasses
import importlib
import inspect
import pkgutil
import types
import typing

from .custom_resource import CustomResource, Scope
from .schema import BaseModel


@dataclasses.dataclass
class CustomResourceDefinitionVersion:
    """
    Storage object for CRD version information.
    """
    # The name of the version
    name: str
    # The model that defines the schema for the version
    model: BaseModel
    # The subresources for the version
    subresources: typing.Dict[str, typing.Any]
    # A list of printer column definitions for the version
    printer_columns: typing.List[typing.Dict[str, typing.Any]]
    # Indicates if this is the storage version
    storage: bool


@dataclasses.dataclass
class CustomResourceDefinition:
    """
    Storage object for CRD information.
    """
    # The API group for the resource
    api_group: str
    # The kind of the resource
    kind: str
    # The singular name of the resource
    singular_name: str
    # The plural name of the resource
    plural_name: str
    # The scope of the resource
    scope: Scope
    # A list of short names for the resource
    short_names: typing.List[str]
    # A list of categories for the resource
    categories: typing.List[str]
    # The versions for the resource, indexed by name
    versions: typing.Dict[str, CustomResourceDefinitionVersion]

    def kubernetes_resource(self) -> typing.Dict[str, typing.Any]:
        return {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {
                "name": f"{self.plural_name}.{self.api_group}",
            },
            "spec": {
                "group": self.api_group,
                "scope": self.scope,
                "names": {
                    "kind": self.kind,
                    "singular": self.singular_name,
                    "plural": self.plural_name,
                    "shortNames": self.short_names,
                    "categories": self.categories,
                },
                "versions": [
                    {
                        "name": version.name,
                        "served": True,
                        "storage": version.storage,
                        "schema": {
                            "openAPIV3Schema": version.model.schema(),
                        },
                        "subresources": version.subresources,
                        "additionalPrinterColumns": version.printer_columns,
                    }
                    for version in self.versions.values()
                ]
            }
        }


def iscustomresourcemodel(obj):
    """
    Utility function to check if a given object is a custom resource model.
    """
    return (
        inspect.isclass(obj) and
        issubclass(obj, CustomResource) and
        # Only consider concrete custom resource models
        hasattr(obj, "_meta")
    )


class CustomResourceRegistry:
    """
    Class for indexing and querying available custom resources.
    """
    def __init__(
        self,
        api_group: str,
        categories: typing.Optional[typing.List[str]] = None
    ):
        self._api_group = api_group
        self._categories = categories or []
        # The indexed CRDs indexed by a tuple of (API group, kind)
        self._crds: typing.Dict[typing.Tuple[str, str], CustomResourceDefinition] = {}

    def register_model(self, model: CustomResource):
        """
        Registers the given model as providing a version of a CRD.
        """
        # Combine the root API group with any subgroup for the resource
        api_group = (
            f"{model._meta.api_subgroup}.{self._api_group}"
            if model._meta.api_subgroup
            else self._api_group
        )
        key = (api_group, model._meta.kind)
        # If the CRD exists, we want to extend the short names and the versions
        existing_crd = self._crds.get(key)
        self._crds[key] = CustomResourceDefinition(
            # Last writer wins for resource-level stuff
            api_group,
            model._meta.kind,
            model._meta.singular_name,
            model._meta.plural_name,
            model._meta.scope,
            # Merge but dedupe the short names given by each version
            list(set(getattr(existing_crd, "short_names", []) + model._meta.short_names)),
            self._categories,
            # Add the new version
            dict(
                getattr(existing_crd, "versions", {}),
                **{
                    model._meta.version: CustomResourceDefinitionVersion(
                        model._meta.version,
                        model,
                        model._meta.subresources,
                        model._meta.printer_columns,
                        model._meta.storage_version
                    )
                }
            )
        )
        return model

    def discover_models(self, module: types.ModuleType):
        """
        Discovers and registers all the custom resource models in the given module.
        """
        # Register all the models in this module
        for _, model in inspect.getmembers(module, lambda obj: iscustomresourcemodel(obj)):
            self.register_model(model)
        # Register all the models in the submodules of the given module
        # Only modules with submodules have a __path__, it seems
        if hasattr(module, "__path__"):
            for _, name, _ in pkgutil.iter_modules(module.__path__):
                self.discover_models(importlib.import_module(f".{name}", module.__name__))

    def get_model_instance(self, resource) -> CustomResource:
        """
        Given a Kubernetes resource, return an instance of the model associated with the
        API version and kind.
        """
        api_group, version = resource["apiVersion"].split("/")
        model = self._crds[(api_group, resource["kind"])].versions[version].model
        return model.parse_obj(resource)

    def __iter__(self):
        # Produce the CRDs when iterated
        yield from self._crds.values()

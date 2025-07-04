import importlib
import importlib.util
import pathlib

import click
import yaml

from .registry import CustomResourceRegistry


@click.command()
@click.option(
    "--category",
    "categories",
    multiple=True,
    help="Category to place CRDs in. Can be specified multiple times.",
)
@click.argument("models_mod")
@click.argument("api_group")
@click.argument("output_dir", type=click.Path())
def main(models_mod, api_group, output_dir, categories=None):
    """
    Generate CRDs from the models in the given module with the given API group.

    The generated CRDs are written into the specified directory.
    """
    # Load the specified module
    models_module = importlib.import_module(models_mod)
    # Create a registry and discover the models in the module
    registry = CustomResourceRegistry(api_group, categories)
    registry.discover_models(models_module)
    # Produce the CRDs in the output directory
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for crd in registry:
        output_path = output_dir / f"{crd.plural_name}.{crd.api_group}.yaml"
        with output_path.open("w") as fh:
            yaml.safe_dump(crd.kubernetes_resource(), fh)

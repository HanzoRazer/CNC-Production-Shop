"""CAM Assist CLI entry point."""

import click

import cam_assist


@click.group()
@click.version_option()
def main() -> None:
    """CAM Assist — Human-guided manufacturing intelligence."""
    pass


@main.command()
def status() -> None:
    """Show CAM Assist status."""
    click.echo(f"CAM Assist v{cam_assist.__version__} — Ready")


if __name__ == "__main__":
    main()

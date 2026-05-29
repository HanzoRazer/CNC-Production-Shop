"""CAM Assist CLI entry point."""

import click


@click.group()
@click.version_option()
def main() -> None:
    """CAM Assist — Human-guided manufacturing intelligence."""
    pass


@main.command()
def status() -> None:
    """Show CAM Assist status."""
    click.echo("CAM Assist v0.1.0 — Ready")


if __name__ == "__main__":
    main()

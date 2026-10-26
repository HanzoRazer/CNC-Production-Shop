"""Source-checkout command for one draft job quote packet.

Dev Order: CNC-JOB-QUOTE-WORKFLOW-001

The command writes files. It does not send, approve, publish externally, or
start manufacturing.
"""

from __future__ import annotations

import click

from business.workflows.models import JobQuoteFailureError, JobQuoteRefusalError
from business.workflows.quote_pipeline import run_job_quote


@click.group()
def main() -> None:
    """Draft a job quote packet from a source checkout."""


@main.command("run")
@click.option("--root", required=True, type=str, help="Explicit source workspace.")
@click.option("--job", required=True, type=str, help="Workspace-relative job request JSON.")
@click.option(
    "--output-dir",
    required=True,
    type=str,
    help="New directory inside the workspace. Existing destinations are refused.",
)
def run_command(root: str, job: str, output_dir: str) -> None:
    """Validate local records and write one draft quote packet."""
    try:
        result = run_job_quote(root=root, job=job, output_dir=output_dir)
    except JobQuoteRefusalError as exc:
        click.echo(f"error: {exc}", err=True)
        raise SystemExit(2) from None
    except JobQuoteFailureError as exc:
        click.echo(f"error: {exc}", err=True)
        raise SystemExit(1) from None
    click.echo(f"job_id: {result.job_id}")
    click.echo(f"status: {result.status}")
    click.echo(f"direct_manufacturing_cost: {result.direct_manufacturing_cost:.2f}")
    click.echo(f"quote_price: {result.quote_price:.2f}")
    click.echo(f"output_dir: {result.output_dir.as_posix()}")
    click.echo(f"customer_proposal: {result.customer_proposal_markdown.as_posix()}")


if __name__ == "__main__":
    main()

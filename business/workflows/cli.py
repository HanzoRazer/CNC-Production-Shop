"""Source-checkout commands for draft job quote packets.

Dev Orders: CNC-JOB-QUOTE-WORKFLOW-001, CNC-JOB-QUOTE-WORKFLOW-002,
and CNC-JOB-QUOTE-VERIFY-001.

``run`` writes one new draft packet. ``verify`` only reads an existing packet.
Neither command sends, approves, or releases manufacturing.
"""

from __future__ import annotations

import re

import click

from business.workflows.models import JobQuoteFailureError, JobQuoteRefusalError
from business.workflows.quote_pipeline import run_job_quote
from business.workflows.reporting import dumps_json
from business.workflows.verification import verify_job_quote_packet
from business.workflows.verification_models import (
    VerificationOperationalError,
    format_verification_text,
    verification_payload,
)

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@click.group()
def main() -> None:
    """Draft a job quote packet from a source checkout.

    Supported requests are guitar_estimate_input_v1 at record version 1.0.0
    and thin_skin_estimate_input_v2 at record version 2.0.0. Both are quantity
    1 and currency USD. The command does not choose a contract by filename.
    """


@main.command("run")
@click.option("--root", required=True, type=str, help="Explicit source workspace.")
@click.option(
    "--job",
    required=True,
    type=str,
    help="Workspace-relative job request JSON (v1 solid-body or v2 thin-skin).",
)
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


@main.command("verify")
@click.option(
    "--packet-dir",
    required=True,
    type=str,
    help="Existing saved quote packet directory.",
)
@click.option(
    "--expected-manifest-sha256",
    default=None,
    type=str,
    help="Caller-retained lowercase SHA-256 of manifest.json. Not an authority.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Write the verification result JSON to stdout.",
)
def verify_command(packet_dir: str, expected_manifest_sha256: str | None, as_json: bool) -> None:
    """Check a saved draft packet from its captured bytes. Writes nothing into it."""
    if expected_manifest_sha256 is not None and _DIGEST.fullmatch(expected_manifest_sha256) is None:
        raise click.BadParameter(
            "expected manifest SHA-256 must be 64 lowercase hex characters",
            param_hint="--expected-manifest-sha256",
        )
    try:
        result = verify_job_quote_packet(packet_dir, expected_manifest_sha256)
    except VerificationOperationalError as exc:
        click.echo(f"error: {exc}", err=True)
        raise SystemExit(1) from None
    rendered = (
        dumps_json(verification_payload(result)).decode("utf-8")
        if as_json
        else format_verification_text(result) + "\n"
    )
    click.echo(rendered, nl=False)
    if result.result != "valid":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

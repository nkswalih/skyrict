"""CLI entrypoint for the {name} service."""

from __future__ import annotations

import typer

app = typer.Typer(name="{name}", help="Skyrict {name} Service CLI")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8000, help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    log_level: str = typer.Option("info", help="Log level"),
) -> None:
    """Start the {name} service."""
    import uvicorn

    uvicorn.run(
        "{name}.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


@app.command()
def migrate(head: str = typer.Option("head", help="Alembic target revision")) -> None:
    """Run database migrations."""
    import subprocess

    subprocess.run(
        ["uv", "run", "alembic", "upgrade", head],
        cwd="services/{name}",
        check=True,
    )


@app.command()
def seed() -> None:
    """Load reference data."""
    typer.echo("Seeding reference data...")
    # TODO: Implement seed logic
    typer.echo("Done.")


if __name__ == "__main__":
    app()

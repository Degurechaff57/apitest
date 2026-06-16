from pathlib import Path
from typing import Optional

import typer

from apitest import __version__
from apitest.config import load_config
from apitest.engine.parser import parse_openapi, detect_format, parse_text
from apitest.engine.llm_client import LLMClient
from apitest.engine.generator import Generator
from apitest.engine.formatter import write_examples, read_examples, write_plan, read_plan
from apitest.engine.runner import TestRunner
from apitest.engine.reporter import Reporter
from apitest.engine.mock_server import create_mock_app, MockServer
from apitest.cli.init_wizard import InitWizard
from apitest.engine.schema_corrector import SchemaCorrector

app = typer.Typer(
    name="apitest",
    help="AI-powered API test automation toolkit",
)


def version_callback(value: bool):
    if value:
        print(f"apitest v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, help="Show version",
    ),
):
    pass


@app.command()
def init():
    """Run the interactive first-run setup wizard."""
    wizard = InitWizard()
    yaml_content = wizard.run()
    config_path = Path.cwd() / ".apitest.yaml"
    if config_path.exists():
        overwrite = typer.confirm(".apitest.yaml already exists. Overwrite?")
        if not overwrite:
            print("Aborted.")
            raise typer.Exit()
    config_path.write_text(yaml_content)
    print(f"\nConfig written to {config_path}")
    print("You're ready! Try: apitest go <your-api-doc>")


@app.command()
def examples(
    api_doc: str = typer.Argument(..., help="Path to API documentation"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    coverage: Optional[str] = typer.Option(None, "--coverage", help="Coverage level"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """Generate test examples from an API document."""
    config = load_config(config_path)
    fmt = output_format or config.examples_format
    cov = coverage or config.coverage

    doc_format = detect_format(api_doc)

    if doc_format == "markdown":
        client = LLMClient.create(
            config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
        )
        gen = Generator(client)
        print(f"Reading API doc from {api_doc}...")
        doc_text = parse_text(api_doc)
        print(f"Analyzing document with {config.llm_model} (coverage: {cov})...")
        test_examples = gen.generate_examples_from_text(doc_text, cov, config.areas)
    else:
        print(f"Parsing {api_doc}...")
        endpoints = parse_openapi(api_doc)
        print(f"Found {len(endpoints)} endpoints")
        gen = Generator()  # no LLM for OpenAPI — instant schema generation
        test_examples = gen.generate_examples_from_schema(endpoints, cov)

    output_dir = Path(config.examples_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"examples.{fmt}"

    write_examples(test_examples, str(output_path), fmt)
    print(f"Generated {len(test_examples)} examples -> {output_path}")


@app.command()
def plan(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """Orchestrate test examples into a test plan."""
    config = load_config(config_path)
    fmt = output_format or config.plan_format

    examples_dir = Path(config.examples_dir)
    examples_file = examples_dir / f"examples.{config.examples_format}"
    if not examples_file.exists():
        print(f"Examples not found: {examples_file}")
        print("Run 'apitest examples <api-doc>' first.")
        raise typer.Exit(code=1)

    print(f"Reading examples from {examples_file}...")
    test_examples = read_examples(str(examples_file), config.examples_format)

    print(f"Generating plan for {len(test_examples)} examples...")
    gen = Generator()  # no LLM — deterministic plan from examples
    test_plan = gen.generate_plan_from_schema(test_examples, config.coverage, config.areas)

    plan_path = config.plan_path
    if not plan_path.endswith(f".{fmt}"):
        plan_path = f"test_plan.{fmt}"

    write_plan(test_plan, plan_path, fmt)
    print(f"Plan written -> {plan_path}")
    print(f"  Phases: {len(test_plan.phases)}")
    print(f"  Total examples: {test_plan.total_examples}")
    print("Review the plan, then run: apitest run")


@app.command()
def run(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode: mock | real"),
):
    """Execute the test plan and generate an Allure report."""
    config = load_config(config_path)
    exec_mode = mode or config.execution_mode

    examples_dir = Path(config.examples_dir)
    examples_file = examples_dir / f"examples.{config.examples_format}"
    if not examples_file.exists():
        print(f"Examples not found: {examples_file}")
        print("Run 'apitest examples <api-doc>' first.")
        raise typer.Exit(code=1)

    plan_file = Path(config.plan_path)
    if not plan_file.exists():
        for fmt in ["md", "json", "yaml"]:
            alt = Path(f"test_plan.{fmt}")
            if alt.exists():
                plan_file = alt
                break

    if not plan_file.exists():
        print(f"Plan not found: {config.plan_path}")
        print("Run 'apitest plan' first.")
        raise typer.Exit(code=1)

    test_examples = read_examples(str(examples_file), config.examples_format)
    plan_fmt = plan_file.suffix.lstrip(".")
    test_plan = read_plan(str(plan_file), plan_fmt)

    mock_server = None
    if exec_mode == "mock":
        import yaml
        mock_spec_path = _resolve_mock_spec(config.api_doc, config)
        if mock_spec_path is None:
            print("Error: Mock mode requires an OpenAPI spec file.")
            print(f"  No OpenAPI spec found for: {config.api_doc}")
            print(f"  Provide an OpenAPI YAML/JSON spec, or use --mode real.")
            raise typer.Exit(code=1)
        with open(mock_spec_path) as f:
            spec = yaml.safe_load(f)
        mock_app = create_mock_app(spec)
        mock_server = MockServer(mock_app, port=config.execution_mock_server_port)
        mock_server.start()
        print(f"Mock server started at {mock_server.url}")

    try:
        print(f"Running {test_plan.total_examples} tests ({exec_mode} mode)...")
        runner = TestRunner(config)
        exit_code = runner.run(test_examples, test_plan, exec_mode, mock_server)

        reporter = Reporter(auto_serve=config.report_auto_serve, results_dir=config.report_dir)
        reporter.serve()

        if exit_code != 0:
            print(f"\nTests completed with failures (exit code: {exit_code})")
            raise typer.Exit(code=exit_code)
        print("\nAll tests passed!")
    finally:
        if mock_server:
            mock_server.stop()
            print("Mock server stopped.")


@app.command()
def go(
    api_doc: str = typer.Argument(..., help="Path to API documentation"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    coverage: Optional[str] = typer.Option(None, "--coverage", help="Coverage level"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode: mock | real"),
):
    """Run the full pipeline: examples -> plan -> run -> report."""
    config = load_config(config_path)
    cov = coverage or config.coverage
    exec_mode = mode or config.execution_mode
    doc_format = detect_format(api_doc)

    client = LLMClient.create(
        config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
    )
    gen = Generator(client)

    # Step 1: Examples
    print(f"\n{'='*50}")
    print(f"Step 1/3: Generating test examples")
    print(f"{'='*50}\n")

    if doc_format == "markdown":
        doc_text = parse_text(api_doc)
        print(f"Analyzing document with {config.llm_model} (coverage: {cov})...")
        test_examples = gen.generate_examples_from_text(doc_text, cov, config.areas)
    else:
        endpoints = parse_openapi(api_doc)
        print(f"Parsed {len(endpoints)} endpoints from {api_doc}")
        # Schema-based generation — instant, no LLM needed
        test_examples = gen.generate_examples_from_schema(endpoints, cov)
        print(f"Generated {len(test_examples)} examples from schema")

    output_dir = Path(config.examples_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    examples_path = output_dir / f"examples.{config.examples_format}"
    write_examples(test_examples, str(examples_path), config.examples_format)

    if len(test_examples) == 0:
        print("\nError: No test examples were generated. Check your LLM configuration:")
        print(f"  Provider: {config.llm_provider}")
        print(f"  Model: {config.llm_model}")
        print(f"  API key set: {'yes' if config.llm_api_key else 'NO — check your .apitest.yaml or env vars'}")
        raise typer.Exit(code=1)

    # Step 2: Plan
    print(f"\n{'='*50}")
    print(f"Step 2/3: Generating test plan")
    print(f"{'='*50}\n")
    # Schema-based plan — instant, no LLM needed
    test_plan = gen.generate_plan_from_schema(test_examples, cov, config.areas)
    plan_path = config.plan_path
    write_plan(test_plan, plan_path, config.plan_format)
    print(f"Plan written -> {plan_path}")
    print(f"  Phases: {len(test_plan.phases)}, Total: {test_plan.total_examples} examples")

    # Step 3: Execute
    print(f"\n{'='*50}")
    print(f"Step 3/3: Running tests")
    print(f"{'='*50}\n")
    mock_server = None
    if exec_mode == "mock":
        import yaml
        mock_spec_path = _resolve_mock_spec(api_doc, config)
        if mock_spec_path is None:
            print("Error: Mock mode requires an OpenAPI spec file.")
            print(f"  The doc '{api_doc}' is a markdown file.")
            print(f"  Provide an OpenAPI YAML/JSON spec, or use --mode real.")
            print(f"  Tip: place an OpenAPI spec alongside your markdown doc,")
            print(f"       e.g. demo/specs/<name>-openapi.yaml")
            raise typer.Exit(code=1)
        with open(mock_spec_path) as f:
            spec = yaml.safe_load(f)
        mock_app = create_mock_app(spec)
        mock_server = MockServer(mock_app, port=config.execution_mock_server_port)
        mock_server.start()
        print(f"Mock server started at {mock_server.url}")

    try:
        print(f"Running {test_plan.total_examples} tests ({exec_mode} mode)...")
        runner = TestRunner(config)
        exit_code = runner.run(test_examples, test_plan, exec_mode, mock_server)
        reporter = Reporter(auto_serve=config.report_auto_serve, results_dir=config.report_dir)
        reporter.serve()
        if exit_code != 0:
            print(f"\nTests completed with failures (exit code: {exit_code})")
            raise typer.Exit(code=exit_code)
        print("\nAll tests passed!")
    finally:
        if mock_server:
            mock_server.stop()
            print("Mock server stopped.")


@app.command()
def report(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Re-serve the last Allure report."""
    config = load_config(config_path)
    reporter = Reporter(auto_serve=True, results_dir=config.report_dir)
    reporter.serve()


def _correct_examples_against_endpoints(examples, endpoints):
    """Fix request bodies, status codes, and headers based on parsed API spec."""
    corrector = SchemaCorrector()
    return corrector.correct(examples, endpoints)


def _resolve_mock_spec(api_doc: str, config) -> str | None:
    """Find the best OpenAPI spec for mock mode. Returns path or None."""
    # If the doc is already OpenAPI, use it
    if detect_format(api_doc) == "openapi":
        return api_doc

    # For markdown docs, look for a matching OpenAPI spec
    from pathlib import Path
    doc_path = Path(api_doc)
    doc_stem = doc_path.stem  # e.g., "xiaohongshu-api"

    # 1. Check specs/ subdirectory next to the doc
    specs_dir = doc_path.parent / "specs"
    if specs_dir.is_dir():
        for candidate in specs_dir.glob("*.yaml"):
            if "openapi" in candidate.stem.lower():
                return str(candidate)
        for candidate in specs_dir.glob("*.yml"):
            if "openapi" in candidate.stem.lower():
                return str(candidate)

    # 2. Check same directory with .yaml extension
    yaml_path = doc_path.with_suffix(".yaml")
    if yaml_path.exists():
        return str(yaml_path)

    # 3. Fall back to config.api_doc if it exists and is OpenAPI
    config_doc = config.api_doc
    if Path(config_doc).exists() and detect_format(config_doc) == "openapi":
        return config_doc

    return None


if __name__ == "__main__":
    app()

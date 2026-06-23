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
from apitest.engine.cache import get_cached_examples, put_cached_examples, clear_cache
from apitest.engine.preflight import PreflightValidator

app = typer.Typer(
    name="apitest",
    help="Generate, execute, and report on API tests from any spec — powered by LLMs",
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

    test_now = typer.confirm("Test the LLM connection?")
    if test_now:
        _test_llm_connection(config_path)


@app.command()
def test(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Test the LLM connection. Verifies API key and model access."""
    _test_llm_connection(config_path)


@app.command()
def examples(
    api_doc: str = typer.Argument(..., help="Path to API documentation"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    coverage: Optional[str] = typer.Option(None, "--coverage", help="Coverage level"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
    fast: bool = typer.Option(False, "--fast", help="Schema-only generation (no LLM, instant)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip cache, force LLM call"),
    thinking: Optional[bool] = typer.Option(
        None, "--thinking/--no-thinking",
        help="Enable LLM thinking mode (on by default; disable if you trust the LLM or want fewer tokens)",
    ),
):
    """Generate test examples from an API document."""
    config = load_config(config_path)
    fmt = output_format or config.examples_format
    cov = coverage or config.coverage
    effective_thinking = config.llm_thinking_enabled if thinking is None else thinking
    skip_cache = no_cache or not config.llm_cache_enabled

    doc_format = detect_format(api_doc)

    if doc_format == "markdown":
        # Check cache
        if not skip_cache:
            cached = get_cached_examples(api_doc, cov, config.areas)
            if cached:
                print(f"Using cached examples ({len(cached)} examples)")
                output_dir = Path(config.examples_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"examples.{fmt}"
                write_examples(cached, str(output_path), fmt)
                print(f"Generated {len(cached)} examples -> {output_path}")
                return

        client = LLMClient.create(
            config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
            thinking_enabled=effective_thinking,
        )
        gen = Generator(client)
        print(f"Reading API doc from {api_doc}...")
        doc_text = parse_text(api_doc)
        print(f"Analyzing document with {config.llm_model} (coverage: {cov})...")
        test_examples = gen.generate_examples_from_text(doc_text, cov, config.areas)
        put_cached_examples(api_doc, cov, config.areas, test_examples)
    else:
        print(f"Parsing {api_doc}...")
        endpoints = parse_openapi(api_doc)
        print(f"Found {len(endpoints)} endpoints")

        if fast:
            gen = Generator()
            test_examples = gen.generate_examples_from_schema(endpoints, cov)
        else:
            # Check cache
            if not skip_cache:
                cached = get_cached_examples(api_doc, cov, config.areas)
                if cached:
                    print(f"Using cached examples ({len(cached)} examples)")
                    test_examples = cached
                    output_dir = Path(config.examples_dir)
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_path = output_dir / f"examples.{fmt}"
                    write_examples(test_examples, str(output_path), fmt)
                    print(f"Generated {len(test_examples)} examples -> {output_path}")
                    return

            print(f"Calling {config.llm_model} to generate examples (coverage: {cov})...")
            client = LLMClient.create(
                config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
                thinking_enabled=effective_thinking,
            )
            gen = Generator(client)
            test_examples = gen.generate_examples(endpoints, cov, config.areas)
            test_examples = _correct_examples_against_endpoints(test_examples, endpoints)
            # Store in cache
            put_cached_examples(api_doc, cov, config.areas, test_examples)

    output_dir = Path(config.examples_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"examples.{fmt}"

    write_examples(test_examples, str(output_path), fmt)
    print(f"Generated {len(test_examples)} examples -> {output_path}")


@app.command()
def plan(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
    llm_plan: bool = typer.Option(False, "--llm-plan", help="Use LLM for plan generation (slower)"),
    thinking: Optional[bool] = typer.Option(
        None, "--thinking/--no-thinking",
        help="Enable LLM thinking mode (on by default; disable if you trust the LLM or want fewer tokens)",
    ),
):
    """Orchestrate test examples into a test plan. Deterministic by default."""
    config = load_config(config_path)
    effective_thinking = config.llm_thinking_enabled if thinking is None else thinking
    fmt = output_format or config.plan_format

    examples_dir = Path(config.examples_dir)
    examples_file = examples_dir / f"examples.{config.examples_format}"
    if not examples_file.exists():
        print(f"Examples not found: {examples_file}")
        print("Run 'apitest examples <api-doc>' first.")
        raise typer.Exit(code=1)

    print(f"Reading examples from {examples_file}...")
    test_examples = read_examples(str(examples_file), config.examples_format)

    if llm_plan:
        print(f"Generating LLM plan for {len(test_examples)} examples...")
        client = LLMClient.create(
            config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
            thinking_enabled=effective_thinking,
        )
        gen = Generator(client)
    else:
        print(f"Generating deterministic plan for {len(test_examples)} examples...")
        gen = Generator()
    test_plan = gen.generate_plan(test_examples, config.coverage, config.areas, use_llm=llm_plan)

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

    reporter = Reporter(auto_serve=config.report_auto_serve, results_dir=config.report_dir)
    try:
        print(f"Running {test_plan.total_examples} tests ({exec_mode} mode)...")
        runner = TestRunner(config)
        exit_code = runner.run(test_examples, test_plan, exec_mode, mock_server)

        reporter.serve(notify=True)

        if exit_code != 0:
            print(f"\nTests completed with failures (exit code: {exit_code})")
            raise typer.Exit(code=exit_code)
        print("\nAll tests passed!")
    finally:
        if mock_server:
            mock_server.stop()
            print("Mock server stopped.")
        reporter.stop()


@app.command()
def go(
    api_doc: str = typer.Argument(..., help="Path to API documentation"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    coverage: Optional[str] = typer.Option(None, "--coverage", help="Coverage level"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode: mock | real"),
    fast: bool = typer.Option(False, "--fast", help="Schema-only generation (no LLM, instant)"),
    llm_plan: bool = typer.Option(False, "--llm-plan", help="Use LLM for plan generation (slower)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip cache, force LLM call"),
    thinking: Optional[bool] = typer.Option(
        None, "--thinking/--no-thinking",
        help="Enable LLM thinking mode (on by default; disable if you trust the LLM or want fewer tokens)",
    ),
):
    """Run the full pipeline: examples -> plan -> run -> report."""
    config = load_config(config_path)
    cov = coverage or config.coverage
    exec_mode = mode or config.execution_mode
    effective_thinking = config.llm_thinking_enabled if thinking is None else thinking
    skip_cache = no_cache or not config.llm_cache_enabled
    doc_format = detect_format(api_doc)

    # Step 1: Examples
    print(f"\n{'='*50}")
    print(f"Step 1/3: Generating test examples")
    print(f"{'='*50}\n")

    if doc_format == "markdown":
        # Check cache
        if not skip_cache:
            cached = get_cached_examples(api_doc, cov, config.areas)
            if cached:
                test_examples = cached
                gen = Generator()  # no LLM needed
            else:
                cached = None
        else:
            cached = None

        if cached is None:
            client = LLMClient.create(
                config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
                thinking_enabled=effective_thinking,
            )
            gen = Generator(client)
            doc_text = parse_text(api_doc)
            print(f"Analyzing document with {config.llm_model} (coverage: {cov})...")
            test_examples = gen.generate_examples_from_text(doc_text, cov, config.areas)
            put_cached_examples(api_doc, cov, config.areas, test_examples)
        else:
            print(f"Using cached examples ({len(cached)} examples)")
    else:
        endpoints = parse_openapi(api_doc)
        print(f"Parsed {len(endpoints)} endpoints from {api_doc}")

        if fast:
            gen = Generator()
            test_examples = gen.generate_examples_from_schema(endpoints, cov)
        else:
            # Check cache
            if not skip_cache:
                cached = get_cached_examples(api_doc, cov, config.areas)
                if cached:
                    test_examples = cached
                    gen = Generator()  # no LLM needed if cache hit
                else:
                    cached = None
            else:
                cached = None

            if cached is None:
                print(f"Calling {config.llm_model} to generate examples (coverage: {cov})...")
                client = LLMClient.create(
                    config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
                    thinking_enabled=effective_thinking,
                )
                gen = Generator(client)
                test_examples = gen.generate_examples(endpoints, cov, config.areas)
                test_examples = _correct_examples_against_endpoints(test_examples, endpoints)
                put_cached_examples(api_doc, cov, config.areas, test_examples)
            else:
                print(f"Using cached examples ({len(cached)} examples)")

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

    # Step 1.5: Start mock server early for preflight validation
    mock_server = None
    if exec_mode == "mock":
        import yaml
        mock_spec_path = _resolve_mock_spec(api_doc, config)
        if mock_spec_path is None:
            print("Error: Mock mode requires an OpenAPI spec file.")
            print(f"  The doc '{api_doc}' is a markdown file.")
            print(f"  Provide an OpenAPI YAML/JSON spec, or use --mode real.")
            raise typer.Exit(code=1)
        with open(mock_spec_path) as f:
            spec = yaml.safe_load(f)
        mock_app = create_mock_app(spec)
        mock_server = MockServer(mock_app, port=config.execution_mock_server_port)
        mock_server.start()

        # Preflight: run each example against mock, correct expected_status
        print(f"\n  Preflight validating against mock server at {mock_server.url}...")
        validator = PreflightValidator(mock_server.url)
        test_examples = validator.validate(test_examples)
        # Update cache and disk with corrected examples
        put_cached_examples(api_doc, cov, config.areas, test_examples)
        write_examples(test_examples, str(examples_path), config.examples_format)

    # Step 2: Plan
    print(f"\n{'='*50}")
    print(f"Step 2/3: Generating test plan")
    print(f"{'='*50}\n")
    if fast or not llm_plan:
        plan_gen = Generator()
        test_plan = plan_gen.generate_plan(test_examples, cov, config.areas)
    else:
        plan_gen = Generator(client if doc_format != "markdown" else
            LLMClient.create(config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
                             thinking_enabled=effective_thinking))
        test_plan = plan_gen.generate_plan(test_examples, cov, config.areas, use_llm=True)
    plan_path = config.plan_path
    write_plan(test_plan, plan_path, config.plan_format)
    print(f"Plan written -> {plan_path}")
    print(f"  Phases: {len(test_plan.phases)}, Total: {test_plan.total_examples} examples")

    # Step 3: Execute (mock server already running)
    print(f"\n{'='*50}")
    print(f"Step 3/3: Running tests")
    print(f"{'='*50}\n")

    reporter = Reporter(auto_serve=config.report_auto_serve, results_dir=config.report_dir)
    try:
        print(f"Running {test_plan.total_examples} tests ({exec_mode} mode)...")
        runner = TestRunner(config)
        exit_code = runner.run(test_examples, test_plan, exec_mode, mock_server)
        reporter.serve(notify=True)
        if exit_code != 0:
            print(f"\nTests completed with failures (exit code: {exit_code})")
            raise typer.Exit(code=exit_code)
        print("\nAll tests passed!")
    finally:
        if mock_server:
            mock_server.stop()
            print("Mock server stopped.")
        reporter.stop()


@app.command()
def report(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Re-serve the last Allure report."""
    config = load_config(config_path)
    reporter = Reporter(auto_serve=True, results_dir=config.report_dir)
    reporter.serve()


@app.command()
def cache_clear(
    spec_path: str = typer.Argument(..., help="Path to the API spec whose cache to clear"),
):
    """Clear cached LLM responses for a spec. Forces regeneration on next run."""
    count = clear_cache(spec_path)
    if count:
        print(f"Cleared {count} cache entr{'y' if count == 1 else 'ies'} for {spec_path}")
    else:
        print(f"No cache entries found for {spec_path}")


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


def _test_llm_connection(config_path: str | None = None) -> None:
    config = load_config(config_path)

    if not config.llm_api_key:
        print("Error: No API key configured.")
        print("  Set one in .apitest.yaml or via environment variable.")
        print("  Run 'apitest init' to reconfigure.")
        raise typer.Exit(code=1)

    print(f"Testing connection to {config.llm_provider} (model: {config.llm_model})...")

    client = LLMClient.create(
        config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
    )
    ok, message = client.ping()

    if ok:
        print(f"  Connection verified ({message})")
        print()
        print("  You're all set! Here's what you can do:")
        print()
        print("    # Full pipeline (recommended):")
        print("    apitest go <your-api-doc> --mode mock")
        print()
        print("    # Or step by step:")
        print("    apitest examples <your-api-doc>   # Generate test examples")
        print("    apitest plan                      # Orchestrate into test plan")
        print("    apitest run                       # Execute and generate report")
        print("    apitest report                    # Re-serve the last report")
        print()
        print("    # Quick, no LLM assisted:")
        print("    apitest go <your-api-doc> --fast --mode mock")
    else:
        print(f"  Connection failed: {message}")
        print("\n  Troubleshooting:")
        print(f"    - Check your API key: run 'apitest init' to reconfigure")
        print(f"    - Check your network connection")
        print(f"    - Provider: {config.llm_provider}, Model: {config.llm_model}")
        if config.llm_base_url:
            print(f"    - Base URL: {config.llm_base_url}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

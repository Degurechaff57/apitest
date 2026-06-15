import questionary


class InitWizard:
    """Interactive first-run setup wizard with arrow-key navigation."""

    def run(self) -> str:
        print("Welcome to apitest — API test automation toolkit\n")
        answers = {}

        provider = questionary.select(
            "Choose LLM provider:",
            choices=[
                questionary.Choice("Anthropic", value="anthropic"),
                questionary.Choice("OpenAI", value="openai"),
                questionary.Choice("Custom (OpenAI-compatible endpoint)", value="custom"),
            ],
        ).ask()
        if provider is None:
            raise KeyboardInterrupt()
        answers["provider"] = provider

        key_method = questionary.select(
            "How to provide API key?",
            choices=[
                questionary.Choice("From environment variable (recommended)", value="env"),
                questionary.Choice("Enter manually", value="manual"),
            ],
        ).ask()
        if key_method == "env":
            env_name = questionary.text(
                "Environment variable name:",
                default="ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY",
            ).ask()
            answers["api_key_env"] = env_name
            answers["api_key_manual"] = ""
        else:
            manual_key = questionary.password("API key:").ask()
            answers["api_key_env"] = ""
            answers["api_key_manual"] = manual_key

        preset_models = {
            "anthropic": ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"],
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "custom": [],
        }
        presets = preset_models.get(provider, [])
        choices = [questionary.Choice(m, value=m) for m in presets]
        choices.append(questionary.Choice("Custom (type model name)", value="__custom__"))

        model = questionary.select("Model:", choices=choices).ask()
        if model == "__custom__":
            model = questionary.text(
                "Model name:",
                instruction="Format: model-name (e.g. gpt-4o, claude-sonnet-4-6)",
            ).ask()
        answers["model"] = model

        if provider == "custom":
            base_url = questionary.text(
                "Custom endpoint URL:",
                default="https://api.example.com/v1",
                instruction="Format: https://host:port/v1",
            ).ask()
            answers["base_url"] = base_url
        else:
            answers["base_url"] = ""

        answers["api_doc"] = questionary.text(
            "Default API doc path:",
            default="specs/openapi.yaml",
        ).ask()

        answers["base_url_test"] = questionary.text(
            "Default base URL for test execution:",
            default="http://localhost:8080",
        ).ask()

        answers["examples_format"] = questionary.select(
            "Examples output format:",
            choices=[
                questionary.Choice("json (machine-readable, default)", value="json"),
                questionary.Choice("yaml", value="yaml"),
                questionary.Choice("md (markdown, human-readable)", value="md"),
                questionary.Choice("xlsx (Excel, for stakeholders)", value="xlsx"),
            ],
        ).ask()

        answers["plan_format"] = questionary.select(
            "Plan output format:",
            choices=[
                questionary.Choice("md (markdown, default)", value="md"),
                questionary.Choice("json", value="json"),
                questionary.Choice("yaml", value="yaml"),
                questionary.Choice("xlsx (Excel)", value="xlsx"),
            ],
        ).ask()

        answers["coverage"] = questionary.select(
            "Default coverage depth:",
            choices=[
                questionary.Choice("smoke — 1 example per endpoint", value="smoke"),
                questionary.Choice("happy-path — ~3-5 examples per endpoint (default)", value="happy-path"),
                questionary.Choice("full — ~6-10 examples per endpoint", value="full"),
            ],
        ).ask()

        return self._build_config(answers)

    def _build_config(self, answers: dict) -> str:
        api_key = ""
        if answers["api_key_env"]:
            api_key = f"${{{answers['api_key_env']}}}"
        elif answers["api_key_manual"]:
            api_key = answers["api_key_manual"]

        lines = [
            "# apitest configuration",
            "",
            "llm:",
            f"  provider: {answers['provider']}",
            f"  model: {answers['model']}",
            f"  api_key: {api_key}",
        ]
        if answers.get("base_url"):
            lines.append(f"  base_url: {answers['base_url']}")

        lines += [
            "",
            f"api_doc: {answers['api_doc']}",
            "",
            "examples:",
            f"  format: {answers['examples_format']}",
            "  dir: tests/examples",
            "",
            "plan:",
            f"  format: {answers['plan_format']}",
            f"  path: test_plan.{answers['plan_format']}",
            "",
            f"base_url: {answers['base_url_test']}",
            f"coverage: {answers['coverage']}",
            "",
            "execution:",
            "  mode: mock",
            "  mock_server_port: null",
            "",
            "report:",
            "  auto_serve: true",
            "  dir: allure-results",
            "",
            "areas:",
            "  - functional",
        ]
        return "\n".join(lines) + "\n"

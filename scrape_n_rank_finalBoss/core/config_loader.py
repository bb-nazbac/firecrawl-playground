"""
Unified YAML Configuration Loader with Validation

Loads and validates pipeline run configuration YAML files.
Supports the unified schema with optional stages: search, qualify, dedupe, fact_check.
Validates all required fields and provides clear error messages.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict


# =====================================================================
# EXCEPTIONS
# =====================================================================

class ConfigValidationError(Exception):
    """Raised when config validation fails."""
    pass


# =====================================================================
# STAGE CONFIGS
# =====================================================================

@dataclass
class InputConfig:
    """Input configuration for starting from CSV instead of search."""
    file: str
    column: str = "domain"


@dataclass
class SearchConfig:
    """Search stage configuration."""
    mode: str  # "query_list" or "geo"
    queries: Optional[List[str]] = None  # for query_list mode
    query_template: Optional[str] = None  # for geo mode
    cities: Optional[List[str]] = None  # for geo mode
    results_per_query: Optional[int] = None  # for query_list mode
    results_per_city: Optional[int] = None  # for geo mode
    gl: str = "us"
    concurrency: int = 30


@dataclass
class QualifyConfig:
    """Qualify stage configuration."""
    spec: str  # refs configs/specs/{name}.json
    model: str = "claude-haiku-4-5-20251001"
    scrape_mode: str = "url"  # "url" or "domain"
    firecrawl_concurrency: int = 45
    llm_concurrency: int = 30
    max_pages: int = 11
    waterfall: bool = True


@dataclass
class DedupeConfig:
    """Dedupe stage configuration."""
    key_field: str = "domain"
    mode: str = "dedupe"  # "dedupe" or "group"


@dataclass
class FactCheckConfig:
    """Fact check stage configuration."""
    model: str = "sonar"
    concurrency: int = 3
    fields_to_verify: List[str] = field(default_factory=list)


@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""
    client: str
    name: str

    # Optional input (start from CSV instead of search)
    input: Optional[InputConfig] = None

    # Optional stages
    search: Optional[SearchConfig] = None
    qualify: Optional[QualifyConfig] = None
    dedupe: Optional[DedupeConfig] = None
    fact_check: Optional[FactCheckConfig] = None

    # Global options
    streaming: bool = False
    test_mode: Optional[int] = None
    max_cost_usd: Optional[float] = None
    dry_run: bool = False

    def to_dict(self) -> dict:
        """Convert to a serializable dictionary."""
        return asdict(self)

    @property
    def has_search(self) -> bool:
        return self.search is not None

    @property
    def has_qualify(self) -> bool:
        return self.qualify is not None

    @property
    def has_dedupe(self) -> bool:
        return self.dedupe is not None

    @property
    def has_fact_check(self) -> bool:
        return self.fact_check is not None

    @property
    def active_stages(self) -> List[str]:
        """Return list of active stage names in order."""
        stages = []
        if self.search is not None:
            stages.append("search")
        if self.qualify is not None:
            stages.append("qualify")
        if self.dedupe is not None:
            stages.append("dedupe")
        if self.fact_check is not None:
            stages.append("fact_check")
        return stages


# =====================================================================
# CONFIG LOADER
# =====================================================================

class ConfigLoader:
    """Loads and validates YAML pipeline configurations."""

    VALID_SEARCH_MODES = ["query_list", "geo"]
    VALID_SCRAPE_MODES = ["url", "domain"]
    VALID_DEDUPE_MODES = ["dedupe", "group"]

    def __init__(self, config_dir: Path = None):
        """
        Initialize config loader.

        Args:
            config_dir: Directory containing run configs (defaults to configs/runs/)
        """
        if config_dir is None:
            self.config_dir = Path(__file__).parent.parent / "configs" / "runs"
        else:
            self.config_dir = Path(config_dir)

    def load(self, config_name: str) -> PipelineConfig:
        """
        Load and validate a pipeline configuration.

        Args:
            config_name: Name of config file (with or without .yaml extension)

        Returns:
            Validated PipelineConfig object

        Raises:
            ConfigValidationError: If validation fails
            FileNotFoundError: If config file doesn't exist
        """
        if not config_name.endswith('.yaml') and not config_name.endswith('.yml'):
            config_name += '.yaml'

        config_path = self.config_dir / config_name

        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"Looking in: {self.config_dir}"
            )

        with open(config_path, 'r') as f:
            try:
                data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ConfigValidationError(f"Invalid YAML syntax: {e}")

        if not isinstance(data, dict):
            raise ConfigValidationError("Config must be a YAML mapping (dict)")

        return self._validate_and_construct(data, config_name)

    def _validate_and_construct(self, data: Dict[str, Any], config_name: str) -> PipelineConfig:
        """Validate config data and construct PipelineConfig object."""
        errors = []

        # --- Required top-level fields ---
        if 'client' not in data:
            errors.append("Missing required field: 'client'")
        elif not isinstance(data['client'], str) or not data['client'].strip():
            errors.append("Field 'client' must be a non-empty string")

        if 'name' not in data:
            errors.append("Missing required field: 'name'")
        elif not isinstance(data['name'], str) or not data['name'].strip():
            errors.append("Field 'name' must be a non-empty string")

        # --- Input config (optional) ---
        input_config = None
        if 'input' in data and data['input'] is not None:
            input_config, input_errors = self._validate_input(data['input'])
            errors.extend(input_errors)

        # --- Stages ---
        stages = data.get('stages', {})
        if not isinstance(stages, dict):
            errors.append("Field 'stages' must be a dictionary")
            stages = {}

        # Validate: must have at least input or search
        if input_config is None and 'search' not in stages:
            errors.append("Config must have either 'input' or 'stages.search' defined")

        # Search config
        search_config = None
        if 'search' in stages and stages['search'] is not None:
            search_config, search_errors = self._validate_search(stages['search'])
            errors.extend(search_errors)

        # Qualify config
        qualify_config = None
        if 'qualify' in stages and stages['qualify'] is not None:
            qualify_config, qualify_errors = self._validate_qualify(stages['qualify'])
            errors.extend(qualify_errors)

        # Dedupe config
        dedupe_config = None
        if 'dedupe' in stages and stages['dedupe'] is not None:
            dedupe_config, dedupe_errors = self._validate_dedupe(stages['dedupe'])
            errors.extend(dedupe_errors)

        # Fact check config
        fact_check_config = None
        if 'fact_check' in stages and stages['fact_check'] is not None:
            fact_check_config, fc_errors = self._validate_fact_check(stages['fact_check'])
            errors.extend(fc_errors)

        # --- Global options ---
        test_mode = self._validate_optional_positive_int(data.get('test_mode'), 'test_mode')
        if test_mode is False:
            errors.append("Field 'test_mode' must be a positive integer or null")
            test_mode = None

        max_cost_usd = self._validate_optional_positive_float(data.get('max_cost_usd'), 'max_cost_usd')
        if max_cost_usd is False:
            errors.append("Field 'max_cost_usd' must be a positive number or null")
            max_cost_usd = None

        streaming = bool(data.get('streaming', False))
        dry_run = bool(data.get('dry_run', False))

        # --- Raise all errors ---
        if errors:
            error_msg = f"Configuration validation failed for '{config_name}':\n"
            error_msg += "\n".join(f"  - {err}" for err in errors)
            raise ConfigValidationError(error_msg)

        return PipelineConfig(
            client=data['client'].strip(),
            name=data['name'].strip(),
            input=input_config,
            search=search_config,
            qualify=qualify_config,
            dedupe=dedupe_config,
            fact_check=fact_check_config,
            streaming=streaming,
            test_mode=test_mode,
            max_cost_usd=max_cost_usd,
            dry_run=dry_run,
        )

    def _validate_input(self, data: Any) -> tuple:
        """Validate input configuration."""
        errors = []

        if not isinstance(data, dict):
            return None, ["Field 'input' must be a dictionary"]

        if 'file' not in data:
            errors.append("Missing required field: 'input.file'")
        elif not isinstance(data['file'], str) or not data['file'].strip():
            errors.append("Field 'input.file' must be a non-empty string")

        if errors:
            return None, errors

        return InputConfig(
            file=data['file'].strip(),
            column=str(data.get('column', 'domain')).strip(),
        ), []

    def _validate_search(self, data: Any) -> tuple:
        """Validate search stage configuration."""
        errors = []

        if not isinstance(data, dict):
            return None, ["Field 'stages.search' must be a dictionary"]

        # Mode is required
        mode = data.get('mode')
        if mode not in self.VALID_SEARCH_MODES:
            errors.append(
                f"Field 'stages.search.mode' must be one of: {', '.join(self.VALID_SEARCH_MODES)}"
            )
            mode = 'query_list'  # default for remaining validation

        # Mode-specific validation
        queries = None
        query_template = None
        cities = None
        results_per_query = None
        results_per_city = None

        if mode == 'query_list':
            queries = data.get('queries')
            if not queries or not isinstance(queries, list) or len(queries) == 0:
                errors.append("Field 'stages.search.queries' is required for query_list mode and must be a non-empty list")
            elif not all(isinstance(q, str) and q.strip() for q in queries):
                errors.append("All entries in 'stages.search.queries' must be non-empty strings")

            results_per_query = data.get('results_per_query')
            if results_per_query is not None:
                if not isinstance(results_per_query, int) or results_per_query < 1:
                    errors.append("Field 'stages.search.results_per_query' must be a positive integer")
            else:
                results_per_query = 100  # default

        elif mode == 'geo':
            query_template = data.get('query_template')
            if not query_template or not isinstance(query_template, str):
                errors.append("Field 'stages.search.query_template' is required for geo mode")

            cities = data.get('cities')
            if not cities or not isinstance(cities, list) or len(cities) == 0:
                errors.append("Field 'stages.search.cities' is required for geo mode and must be a non-empty list")
            elif not all(isinstance(c, str) and c.strip() for c in cities):
                errors.append("All entries in 'stages.search.cities' must be non-empty strings")

            results_per_city = data.get('results_per_city')
            if results_per_city is not None:
                if not isinstance(results_per_city, int) or results_per_city < 1:
                    errors.append("Field 'stages.search.results_per_city' must be a positive integer")
            else:
                results_per_city = 100  # default

        # Optional fields
        gl = str(data.get('gl', 'us')).strip().lower()
        concurrency = data.get('concurrency', 30)
        if not isinstance(concurrency, int) or concurrency < 1 or concurrency > 200:
            errors.append("Field 'stages.search.concurrency' must be an integer between 1 and 200")
            concurrency = 30

        if errors:
            return None, errors

        return SearchConfig(
            mode=mode,
            queries=[q.strip() for q in queries] if queries else None,
            query_template=query_template.strip() if query_template else None,
            cities=[c.strip() for c in cities] if cities else None,
            results_per_query=results_per_query,
            results_per_city=results_per_city,
            gl=gl,
            concurrency=concurrency,
        ), []

    def _validate_qualify(self, data: Any) -> tuple:
        """Validate qualify stage configuration."""
        errors = []

        if not isinstance(data, dict):
            return None, ["Field 'stages.qualify' must be a dictionary"]

        # Spec is required
        spec = data.get('spec')
        if not spec or not isinstance(spec, str):
            errors.append("Missing required field: 'stages.qualify.spec'")

        # Scrape mode
        scrape_mode = data.get('scrape_mode', 'url')
        if scrape_mode not in self.VALID_SCRAPE_MODES:
            errors.append(
                f"Field 'stages.qualify.scrape_mode' must be one of: {', '.join(self.VALID_SCRAPE_MODES)}"
            )
            scrape_mode = 'url'

        # Concurrency values
        firecrawl_concurrency = data.get('firecrawl_concurrency', 45)
        if not isinstance(firecrawl_concurrency, int) or firecrawl_concurrency < 1:
            errors.append("Field 'stages.qualify.firecrawl_concurrency' must be a positive integer")
            firecrawl_concurrency = 45

        llm_concurrency = data.get('llm_concurrency', 30)
        if not isinstance(llm_concurrency, int) or llm_concurrency < 1:
            errors.append("Field 'stages.qualify.llm_concurrency' must be a positive integer")
            llm_concurrency = 30

        max_pages = data.get('max_pages', 11)
        if not isinstance(max_pages, int) or max_pages < 1:
            errors.append("Field 'stages.qualify.max_pages' must be a positive integer")
            max_pages = 11

        model = str(data.get('model', 'claude-haiku-4-5-20251001'))
        waterfall = bool(data.get('waterfall', True))

        if errors:
            return None, errors

        return QualifyConfig(
            spec=spec.strip(),
            model=model,
            scrape_mode=scrape_mode,
            firecrawl_concurrency=firecrawl_concurrency,
            llm_concurrency=llm_concurrency,
            max_pages=max_pages,
            waterfall=waterfall,
        ), []

    def _validate_dedupe(self, data: Any) -> tuple:
        """Validate dedupe stage configuration."""
        errors = []

        if not isinstance(data, dict):
            return None, ["Field 'stages.dedupe' must be a dictionary"]

        key_field = str(data.get('key_field', 'domain')).strip()
        mode = str(data.get('mode', 'dedupe')).strip()

        if mode not in self.VALID_DEDUPE_MODES:
            errors.append(
                f"Field 'stages.dedupe.mode' must be one of: {', '.join(self.VALID_DEDUPE_MODES)}"
            )

        if errors:
            return None, errors

        return DedupeConfig(key_field=key_field, mode=mode), []

    def _validate_fact_check(self, data: Any) -> tuple:
        """Validate fact check stage configuration."""
        errors = []

        if not isinstance(data, dict):
            return None, ["Field 'stages.fact_check' must be a dictionary"]

        model = str(data.get('model', 'sonar'))

        concurrency = data.get('concurrency', 3)
        if not isinstance(concurrency, int) or concurrency < 1:
            errors.append("Field 'stages.fact_check.concurrency' must be a positive integer")
            concurrency = 3

        fields_to_verify = data.get('fields_to_verify', [])
        if not isinstance(fields_to_verify, list):
            errors.append("Field 'stages.fact_check.fields_to_verify' must be a list")
            fields_to_verify = []

        if errors:
            return None, errors

        return FactCheckConfig(
            model=model,
            concurrency=concurrency,
            fields_to_verify=fields_to_verify,
        ), []

    def _validate_optional_positive_int(self, value: Any, field_name: str) -> Union[Optional[int], bool]:
        """Validate optional positive integer. Returns False if invalid, None if not set, int if valid."""
        if value is None:
            return None
        if not isinstance(value, int) or value < 1:
            return False
        return value

    def _validate_optional_positive_float(self, value: Any, field_name: str) -> Union[Optional[float], bool]:
        """Validate optional positive float. Returns False if invalid, None if not set, float if valid."""
        if value is None:
            return None
        try:
            cost = float(value)
            if cost <= 0:
                return False
            return cost
        except (TypeError, ValueError):
            return False


# =====================================================================
# CONVENIENCE FUNCTION
# =====================================================================

def load_config(config_name: str, config_dir: Path = None) -> PipelineConfig:
    """
    Convenience function to load a pipeline config.

    Args:
        config_name: Name of config file (with or without .yaml extension)
        config_dir: Optional custom config directory

    Returns:
        Validated PipelineConfig object
    """
    loader = ConfigLoader(config_dir)
    return loader.load(config_name)

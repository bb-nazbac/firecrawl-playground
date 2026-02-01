"""
Unified Configuration Loader

Loads and validates YAML configs that drive both search and scrape stages.
Supports:
  - Flat query lists: search.queries
  - Template + variables: search.query + search.variables
  - Both combined
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field


@dataclass
class SearchConfig:
    """Search stage configuration"""
    queries: List[str]              # Final resolved list of queries
    results_per_query: int = 50
    gl: str = "us"
    concurrency: int = 30


@dataclass
class ScrapeConfig:
    """Scrape/qualify stage configuration"""
    spec: str                       # Name of spec file (without .json)
    model: str = "gpt-5-mini"
    firecrawl_concurrency: int = 100
    openai_concurrency: int = 100
    max_pages: int = 6
    use_waterfall: bool = True
    mode: str = "domain"            # "domain" (scrape homepage) or "url" (scrape exact URL from search)


@dataclass
class DedupeConfig:
    """Deduplication configuration"""
    enabled: bool = True
    key_field: str = "target_company_name"
    mode: str = "dedupe"    # "dedupe" = keep best row per key, "group" = keep all rows sorted by key


@dataclass
class FactCheckConfig:
    """Perplexity fact-check configuration"""
    enabled: bool = False
    model: str = "sonar"                # sonar (cheap) or sonar-pro (better)
    concurrency: int = 3                # Stay within Perplexity rate limits
    fields_to_verify: List[str] = None  # Which extracted fields to verify (None = all defaults)


@dataclass
class PipelineConfig:
    """Complete unified pipeline configuration"""
    client: str
    name: str
    search: SearchConfig
    scrape: ScrapeConfig
    dedupe: DedupeConfig = None
    fact_check: FactCheckConfig = None

    # Optional
    test_mode: Optional[int] = None
    max_cost_usd: Optional[float] = None
    dry_run: bool = False

    def __post_init__(self):
        if self.dedupe is None:
            self.dedupe = DedupeConfig()


class ConfigValidationError(Exception):
    """Raised when config validation fails"""
    pass


def _resolve_queries(search_data: Dict[str, Any]) -> List[str]:
    """
    Resolve the final list of search queries from config.

    Supports:
      - search.queries: flat list of queries
      - search.query + search.variables: template expansion
      - Both combined
    """
    queries = []

    # Option A: Flat query list
    if 'queries' in search_data:
        raw = search_data['queries']
        if isinstance(raw, list):
            queries.extend([q.strip() for q in raw if isinstance(q, str) and q.strip()])

    # Option B: Template + variables
    if 'query' in search_data and 'variables' in search_data:
        template = search_data['query']
        variables = search_data['variables']
        if isinstance(template, str) and isinstance(variables, list):
            for var in variables:
                if isinstance(var, str) and var.strip():
                    # Replace any {placeholder} with the variable value
                    expanded = template
                    # Support {variable}, {city}, {topic}, or any placeholder
                    import re
                    placeholders = re.findall(r'\{(\w+)\}', template)
                    for ph in placeholders:
                        expanded = expanded.replace(f'{{{ph}}}', var.strip())
                    queries.append(expanded)

    return queries


def load_config(config_name: str, config_dir: Path = None) -> PipelineConfig:
    """
    Load and validate a unified pipeline config.

    Args:
        config_name: Name of config file (with or without .yaml)
        config_dir: Optional custom config directory

    Returns:
        Validated PipelineConfig

    Raises:
        ConfigValidationError: If validation fails
        FileNotFoundError: If config file doesn't exist
    """
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / "configs"

    if not config_name.endswith('.yaml'):
        config_name += '.yaml'

    config_path = config_dir / config_name

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Looking in: {config_dir}"
        )

    with open(config_path, 'r') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"Invalid YAML: {e}")

    return _validate_and_construct(data, config_name)


def _validate_and_construct(data: Dict[str, Any], config_name: str) -> PipelineConfig:
    """Validate config data and construct PipelineConfig."""
    errors = []

    # Required top-level fields
    if not data.get('client'):
        errors.append("Missing required field: 'client'")
    if not data.get('name'):
        errors.append("Missing required field: 'name'")

    # Search section
    if 'search' not in data or not isinstance(data.get('search'), dict):
        errors.append("Missing required section: 'search'")
    else:
        search_data = data['search']
        queries = _resolve_queries(search_data)
        if not queries:
            errors.append(
                "No search queries resolved. Provide either 'search.queries' (list) "
                "or 'search.query' + 'search.variables' (template)"
            )

        rpc = search_data.get('results_per_query', 50)
        if not isinstance(rpc, int) or rpc < 1 or rpc > 1000:
            errors.append("'search.results_per_query' must be an integer between 1 and 1000")

    # Scrape section
    if 'scrape' not in data or not isinstance(data.get('scrape'), dict):
        errors.append("Missing required section: 'scrape'")
    else:
        scrape_data = data['scrape']
        if not scrape_data.get('spec'):
            errors.append("Missing required field: 'scrape.spec'")
        else:
            # Verify spec file exists
            spec_name = scrape_data['spec']
            if not spec_name.endswith('.json'):
                spec_name += '.json'
            spec_path = Path(__file__).parent.parent / "specs" / spec_name
            if not spec_path.exists():
                errors.append(f"Spec file not found: {spec_path}")

    # Optional validation
    test_mode = data.get('test_mode')
    if test_mode is not None and (not isinstance(test_mode, int) or test_mode < 1):
        errors.append("'test_mode' must be a positive integer")

    max_cost = data.get('max_cost_usd')
    if max_cost is not None:
        try:
            max_cost = float(max_cost)
            if max_cost <= 0:
                errors.append("'max_cost_usd' must be positive")
        except (TypeError, ValueError):
            errors.append("'max_cost_usd' must be a number")

    if errors:
        msg = f"Config validation failed for '{config_name}':\n"
        msg += "\n".join(f"  - {e}" for e in errors)
        raise ConfigValidationError(msg)

    # Construct
    search_data = data['search']
    scrape_data = data['scrape']
    dedupe_data = data.get('dedupe', {})

    search_config = SearchConfig(
        queries=_resolve_queries(search_data),
        results_per_query=search_data.get('results_per_query', 50),
        gl=search_data.get('gl', 'us'),
        concurrency=search_data.get('concurrency', 30),
    )

    scrape_config = ScrapeConfig(
        spec=scrape_data['spec'],
        model=scrape_data.get('model', 'gpt-5-mini'),
        firecrawl_concurrency=scrape_data.get('firecrawl_concurrency', 100),
        openai_concurrency=scrape_data.get('openai_concurrency', 100),
        max_pages=scrape_data.get('max_pages', 6),
        use_waterfall=scrape_data.get('use_waterfall', True),
        mode=scrape_data.get('mode', 'domain'),
    )

    dedupe_config = DedupeConfig(
        enabled=dedupe_data.get('enabled', True),
        key_field=dedupe_data.get('key_field', 'target_company_name'),
        mode=dedupe_data.get('mode', 'dedupe'),
    )

    # Fact-check section (optional)
    fc_data = data.get('fact_check', {})
    fact_check_config = None
    if fc_data and fc_data.get('enabled', False):
        fact_check_config = FactCheckConfig(
            enabled=True,
            model=fc_data.get('model', 'sonar'),
            concurrency=fc_data.get('concurrency', 3),
            fields_to_verify=fc_data.get('fields_to_verify'),
        )

    return PipelineConfig(
        client=data['client'].strip(),
        name=data['name'].strip(),
        search=search_config,
        scrape=scrape_config,
        dedupe=dedupe_config,
        fact_check=fact_check_config,
        test_mode=data.get('test_mode'),
        max_cost_usd=data.get('max_cost_usd'),
        dry_run=data.get('dry_run', False),
    )

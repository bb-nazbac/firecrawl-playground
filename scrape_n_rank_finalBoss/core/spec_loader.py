"""
Analysis Spec Loader

Loads JSON analysis specifications that define how companies should be qualified.
Specs define categories, questions, classification logic, waterfall filters,
sufficiency checks, iteration logic, extraction fields, and output schemas.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field


# =====================================================================
# PROJECT ROOT
# =====================================================================

PROJECT_ROOT = Path(__file__).parent.parent
SPECS_DIR = PROJECT_ROOT / "configs" / "specs"


# =====================================================================
# DATA CLASS
# =====================================================================

@dataclass
class AnalysisSpec:
    """
    Loaded analysis specification defining how to qualify companies.

    Contains all the configuration needed for LLM-based analysis:
    - Categories: possible qualification outcomes
    - Questions: what to ask about each company
    - Classification logic: rules for categorizing
    - Waterfall filter: cheap pre-filter before full analysis
    - Sufficiency check: when is homepage enough vs needing more pages
    - Iteration logic: how to iterate for more information
    - Extraction fields: structured data to extract
    - Output schema: shape of the final output
    - LLM config: default model/max_tokens/temperature
    """
    spec_name: str
    description: str
    categories: List[Dict]
    questions: List[Dict]
    classification_logic: Dict
    waterfall_filter: Optional[Dict] = None
    sufficiency_check: Optional[Dict] = None
    iteration_logic: Optional[Dict] = None
    extraction_fields: Optional[Dict] = None
    output_schema: Optional[Dict] = None
    critical_questions: List[str] = field(default_factory=list)
    llm_config: Dict = field(default_factory=lambda: {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2000,
        "temperature": 0
    })

    @classmethod
    def load(cls, spec_path: Path) -> 'AnalysisSpec':
        """
        Load spec from a JSON file.

        Args:
            spec_path: Path to the JSON spec file

        Returns:
            Populated AnalysisSpec instance

        Raises:
            FileNotFoundError: If spec file doesn't exist
            json.JSONDecodeError: If spec file is invalid JSON
            ValueError: If required fields are missing
        """
        spec_path = Path(spec_path)
        if not spec_path.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_path}")

        with open(spec_path, 'r') as f:
            data = json.load(f)

        # Validate required fields
        if 'categories' not in data or not data['categories']:
            raise ValueError(f"Spec '{spec_path.name}' must have 'categories' defined")
        if 'questions' not in data or not data['questions']:
            raise ValueError(f"Spec '{spec_path.name}' must have 'questions' defined")

        # Extract critical questions from iteration_logic if present
        iteration_logic = data.get('iteration_logic', {})
        critical_questions = iteration_logic.get('critical_questions', [])

        # Extract LLM config
        llm_config = data.get('llm', {})
        if not llm_config:
            llm_config = {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 2000,
                "temperature": 0
            }

        # Extract client description for backward compatibility
        description = data.get('description', '')
        if not description:
            client_info = data.get('client', {})
            if isinstance(client_info, dict):
                description = client_info.get('who_we_target', client_info.get('description', ''))

        return cls(
            spec_name=data.get('spec_name', spec_path.stem),
            description=description,
            categories=data.get('categories', []),
            questions=data.get('questions', []),
            classification_logic=data.get('classification_logic', {}),
            waterfall_filter=data.get('waterfall_filter', None),
            sufficiency_check=data.get('sufficiency_check', None),
            iteration_logic=iteration_logic if iteration_logic else None,
            extraction_fields=data.get('extraction_fields', None),
            output_schema=data.get('output_schema', None),
            critical_questions=critical_questions,
            llm_config=llm_config,
        )

    @property
    def category_names(self) -> List[str]:
        """Get list of category names/IDs."""
        names = []
        for cat in self.categories:
            name = cat.get('name') or cat.get('id') or cat.get('label', '')
            if name:
                names.append(name)
        return names

    @property
    def question_fields(self) -> List[str]:
        """Get list of question field names."""
        return [q.get('field', '') for q in self.questions if q.get('field')]

    @property
    def default_model(self) -> str:
        """Get default LLM model from spec."""
        return self.llm_config.get('model', 'claude-haiku-4-5-20251001')

    @property
    def default_max_tokens(self) -> int:
        """Get default max_tokens from spec."""
        return self.llm_config.get('max_tokens', 2000)

    @property
    def default_temperature(self) -> float:
        """Get default temperature from spec."""
        return self.llm_config.get('temperature', 0)

    def get_classification_rules(self) -> List[Dict]:
        """Get ordered classification rules."""
        return self.classification_logic.get('apply_in_order', [])

    def get_waterfall_questions(self) -> List[str]:
        """Get questions used in waterfall filter (cheap pre-check)."""
        if not self.waterfall_filter:
            return []
        return self.waterfall_filter.get('questions', [])

    def get_sufficiency_config(self) -> Dict:
        """Get sufficiency check configuration."""
        if not self.sufficiency_check:
            return {
                "enabled": False,
                "min_questions_answered": 0,
                "min_confidence": "low"
            }
        return self.sufficiency_check

    def to_dict(self) -> dict:
        """Convert to a serializable dictionary."""
        return {
            "spec_name": self.spec_name,
            "description": self.description,
            "categories": self.categories,
            "questions": self.questions,
            "classification_logic": self.classification_logic,
            "waterfall_filter": self.waterfall_filter,
            "sufficiency_check": self.sufficiency_check,
            "iteration_logic": self.iteration_logic,
            "extraction_fields": self.extraction_fields,
            "output_schema": self.output_schema,
            "critical_questions": self.critical_questions,
            "llm_config": self.llm_config,
        }


# =====================================================================
# CONVENIENCE FUNCTION
# =====================================================================

def load_spec(spec_name: str, specs_dir: Path = None) -> AnalysisSpec:
    """
    Convenience function to load a spec by name.

    Args:
        spec_name: Name of spec file (with or without .json extension)
        specs_dir: Optional custom specs directory (defaults to configs/specs/)

    Returns:
        Loaded AnalysisSpec instance

    Raises:
        FileNotFoundError: If spec file doesn't exist
    """
    if specs_dir is None:
        specs_dir = SPECS_DIR

    specs_dir = Path(specs_dir)

    # Add .json extension if not present
    if not spec_name.endswith('.json'):
        spec_name += '.json'

    spec_path = specs_dir / spec_name

    # If not found directly, try looking in subdirectories
    if not spec_path.exists():
        for child in specs_dir.iterdir():
            if child.is_dir():
                candidate = child / spec_name
                if candidate.exists():
                    spec_path = candidate
                    break

    return AnalysisSpec.load(spec_path)

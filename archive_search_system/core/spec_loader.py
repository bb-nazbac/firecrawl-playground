"""
JSON Analysis Spec Loader with Validation

Loads and validates analysis specification JSON files.
Analysis specs define HOW to analyze webpages (categories, extraction, questions).
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class Category:
    """Classification category"""
    id: str
    label: str
    description: str


@dataclass
class ExtractionField:
    """Field to extract from webpage"""
    name: str
    type: str
    required: bool
    description: str


@dataclass
class Question:
    """Question to ask about the webpage"""
    field: str
    question: str
    answer_type: str
    reasoning_required: bool
    evidence_required: bool


@dataclass
class LLMConfig:
    """LLM configuration for classification"""
    model: str
    max_tokens: int
    temperature: float


@dataclass
class AnalysisSpec:
    """Complete analysis specification"""
    spec_name: str
    description: str
    categories: List[Category]
    extraction_fields: Dict[str, ExtractionField]
    questions: List[Question]
    llm: LLMConfig


class SpecValidationError(Exception):
    """Raised when spec validation fails"""
    pass


class SpecLoader:
    """Loads and validates JSON analysis specifications"""

    VALID_FIELD_TYPES = ["string", "number", "boolean", "array", "url", "phone", "email"]
    VALID_ANSWER_TYPES = ["boolean", "string", "number", "array"]
    VALID_LLM_MODELS = [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-sonnet-3-5-20241022",
        "claude-opus-3-5-20241022",
        "claude-3-5-haiku-20241022"
    ]

    def __init__(self, spec_dir: Path = None):
        """
        Initialize spec loader

        Args:
            spec_dir: Directory containing analysis specs (defaults to configs/specs/analysis/)
        """
        if spec_dir is None:
            # Default to search_system/configs/specs/analysis/
            self.spec_dir = Path(__file__).parent.parent / "configs" / "specs" / "analysis"
        else:
            self.spec_dir = Path(spec_dir)

    def load(self, spec_name: str) -> AnalysisSpec:
        """
        Load and validate an analysis specification

        Args:
            spec_name: Name of spec file (with or without .json extension)

        Returns:
            Validated AnalysisSpec object

        Raises:
            SpecValidationError: If validation fails
            FileNotFoundError: If spec file doesn't exist
        """
        # Add .json extension if not present
        if not spec_name.endswith('.json'):
            spec_name += '.json'

        spec_path = self.spec_dir / spec_name

        if not spec_path.exists():
            raise FileNotFoundError(
                f"Spec file not found: {spec_path}\n"
                f"Looking in: {self.spec_dir}"
            )

        # Load JSON
        with open(spec_path, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise SpecValidationError(f"Invalid JSON syntax: {e}")

        # Validate and construct AnalysisSpec
        return self._validate_and_construct(data, spec_name)

    def _validate_and_construct(self, data: Dict[str, Any], spec_name: str) -> AnalysisSpec:
        """
        Validate spec data and construct AnalysisSpec object

        Args:
            data: Parsed JSON data
            spec_name: Name of spec file (for error messages)

        Returns:
            Validated AnalysisSpec object

        Raises:
            SpecValidationError: If validation fails
        """
        errors = []

        # Validate required top-level fields
        if 'spec_name' not in data:
            errors.append("Missing required field: 'spec_name'")
        elif not isinstance(data['spec_name'], str) or not data['spec_name'].strip():
            errors.append("Field 'spec_name' must be a non-empty string")

        if 'description' not in data:
            errors.append("Missing required field: 'description'")
        elif not isinstance(data['description'], str) or not data['description'].strip():
            errors.append("Field 'description' must be a non-empty string")

        # Validate categories
        categories = None
        if 'categories' not in data:
            errors.append("Missing required field: 'categories'")
        elif not isinstance(data['categories'], list):
            errors.append("Field 'categories' must be a list")
        elif len(data['categories']) == 0:
            errors.append("Field 'categories' must contain at least one category")
        else:
            categories, cat_errors = self._validate_categories(data['categories'])
            errors.extend(cat_errors)

        # Validate extraction_fields
        extraction_fields = None
        if 'extraction_fields' not in data:
            errors.append("Missing required field: 'extraction_fields'")
        elif not isinstance(data['extraction_fields'], dict):
            errors.append("Field 'extraction_fields' must be a dictionary")
        else:
            extraction_fields, field_errors = self._validate_extraction_fields(data['extraction_fields'])
            errors.extend(field_errors)

        # Validate questions
        questions = None
        if 'questions' not in data:
            errors.append("Missing required field: 'questions'")
        elif not isinstance(data['questions'], list):
            errors.append("Field 'questions' must be a list")
        elif len(data['questions']) == 0:
            errors.append("Field 'questions' must contain at least one question")
        else:
            questions, q_errors = self._validate_questions(data['questions'])
            errors.extend(q_errors)

        # Validate LLM config
        llm_config = None
        if 'llm' not in data:
            errors.append("Missing required field: 'llm'")
        elif not isinstance(data['llm'], dict):
            errors.append("Field 'llm' must be a dictionary")
        else:
            llm_config, llm_errors = self._validate_llm_config(data['llm'])
            errors.extend(llm_errors)

        # If there are errors, raise exception with all errors
        if errors:
            error_msg = f"Spec validation failed for '{spec_name}':\n"
            error_msg += "\n".join(f"  - {err}" for err in errors)
            raise SpecValidationError(error_msg)

        # Construct and return AnalysisSpec
        return AnalysisSpec(
            spec_name=data['spec_name'].strip(),
            description=data['description'].strip(),
            categories=categories,
            extraction_fields=extraction_fields,
            questions=questions,
            llm=llm_config
        )

    def _validate_categories(self, categories_data: List[Dict]) -> tuple:
        """
        Validate categories

        Returns:
            Tuple of (list of Category objects or None, list of error messages)
        """
        errors = []
        categories = []
        seen_ids = set()

        for i, cat in enumerate(categories_data):
            if not isinstance(cat, dict):
                errors.append(f"Category {i} must be a dictionary")
                continue

            # Validate required fields
            if 'id' not in cat:
                errors.append(f"Category {i}: missing required field 'id'")
            elif not isinstance(cat['id'], str) or not cat['id'].strip():
                errors.append(f"Category {i}: 'id' must be a non-empty string")
            elif cat['id'] in seen_ids:
                errors.append(f"Category {i}: duplicate id '{cat['id']}'")
            else:
                seen_ids.add(cat['id'])

            if 'label' not in cat:
                errors.append(f"Category {i}: missing required field 'label'")
            elif not isinstance(cat['label'], str) or not cat['label'].strip():
                errors.append(f"Category {i}: 'label' must be a non-empty string")

            if 'description' not in cat:
                errors.append(f"Category {i}: missing required field 'description'")
            elif not isinstance(cat['description'], str) or not cat['description'].strip():
                errors.append(f"Category {i}: 'description' must be a non-empty string")

            # If all fields present, create Category
            if all(k in cat for k in ['id', 'label', 'description']):
                categories.append(Category(
                    id=cat['id'].strip(),
                    label=cat['label'].strip(),
                    description=cat['description'].strip()
                ))

        if errors:
            return None, errors

        return categories, []

    def _validate_extraction_fields(self, fields_data: Dict[str, Dict]) -> tuple:
        """
        Validate extraction fields

        Returns:
            Tuple of (dict of ExtractionField objects or None, list of error messages)
        """
        errors = []
        extraction_fields = {}

        for field_name, field_spec in fields_data.items():
            if not isinstance(field_spec, dict):
                errors.append(f"Extraction field '{field_name}' must be a dictionary")
                continue

            # Validate type
            if 'type' not in field_spec:
                errors.append(f"Extraction field '{field_name}': missing required field 'type'")
            elif field_spec['type'] not in self.VALID_FIELD_TYPES:
                errors.append(
                    f"Extraction field '{field_name}': invalid type '{field_spec['type']}'. "
                    f"Must be one of: {', '.join(self.VALID_FIELD_TYPES)}"
                )

            # Validate required
            if 'required' not in field_spec:
                errors.append(f"Extraction field '{field_name}': missing required field 'required'")
            elif not isinstance(field_spec['required'], bool):
                errors.append(f"Extraction field '{field_name}': 'required' must be a boolean")

            # Validate description
            if 'description' not in field_spec:
                errors.append(f"Extraction field '{field_name}': missing required field 'description'")
            elif not isinstance(field_spec['description'], str) or not field_spec['description'].strip():
                errors.append(f"Extraction field '{field_name}': 'description' must be a non-empty string")

            # If all fields present, create ExtractionField
            if all(k in field_spec for k in ['type', 'required', 'description']):
                extraction_fields[field_name] = ExtractionField(
                    name=field_name,
                    type=field_spec['type'],
                    required=field_spec['required'],
                    description=field_spec['description'].strip()
                )

        if errors:
            return None, errors

        return extraction_fields, []

    def _validate_questions(self, questions_data: List[Dict]) -> tuple:
        """
        Validate questions

        Returns:
            Tuple of (list of Question objects or None, list of error messages)
        """
        errors = []
        questions = []
        seen_fields = set()

        for i, q in enumerate(questions_data):
            if not isinstance(q, dict):
                errors.append(f"Question {i} must be a dictionary")
                continue

            # Validate field
            if 'field' not in q:
                errors.append(f"Question {i}: missing required field 'field'")
            elif not isinstance(q['field'], str) or not q['field'].strip():
                errors.append(f"Question {i}: 'field' must be a non-empty string")
            elif q['field'] in seen_fields:
                errors.append(f"Question {i}: duplicate field '{q['field']}'")
            else:
                seen_fields.add(q['field'])

            # Validate question text
            if 'question' not in q:
                errors.append(f"Question {i}: missing required field 'question'")
            elif not isinstance(q['question'], str) or not q['question'].strip():
                errors.append(f"Question {i}: 'question' must be a non-empty string")

            # Validate answer_type
            if 'answer_type' not in q:
                errors.append(f"Question {i}: missing required field 'answer_type'")
            elif q['answer_type'] not in self.VALID_ANSWER_TYPES:
                errors.append(
                    f"Question {i}: invalid answer_type '{q['answer_type']}'. "
                    f"Must be one of: {', '.join(self.VALID_ANSWER_TYPES)}"
                )

            # Validate reasoning_required
            if 'reasoning_required' not in q:
                errors.append(f"Question {i}: missing required field 'reasoning_required'")
            elif not isinstance(q['reasoning_required'], bool):
                errors.append(f"Question {i}: 'reasoning_required' must be a boolean")

            # Validate evidence_required
            if 'evidence_required' not in q:
                errors.append(f"Question {i}: missing required field 'evidence_required'")
            elif not isinstance(q['evidence_required'], bool):
                errors.append(f"Question {i}: 'evidence_required' must be a boolean")

            # If all fields present, create Question
            if all(k in q for k in ['field', 'question', 'answer_type', 'reasoning_required', 'evidence_required']):
                questions.append(Question(
                    field=q['field'].strip(),
                    question=q['question'].strip(),
                    answer_type=q['answer_type'],
                    reasoning_required=q['reasoning_required'],
                    evidence_required=q['evidence_required']
                ))

        if errors:
            return None, errors

        return questions, []

    def _validate_llm_config(self, llm_data: Dict) -> tuple:
        """
        Validate LLM configuration

        Returns:
            Tuple of (LLMConfig or None, list of error messages)
        """
        errors = []

        # Validate model
        if 'model' not in llm_data:
            errors.append("LLM config: missing required field 'model'")
        elif llm_data['model'] not in self.VALID_LLM_MODELS:
            errors.append(
                f"LLM config: invalid model '{llm_data['model']}'. "
                f"Must be one of: {', '.join(self.VALID_LLM_MODELS)}"
            )

        # Validate max_tokens
        if 'max_tokens' not in llm_data:
            errors.append("LLM config: missing required field 'max_tokens'")
        elif not isinstance(llm_data['max_tokens'], int) or llm_data['max_tokens'] < 1:
            errors.append("LLM config: 'max_tokens' must be a positive integer")
        elif llm_data['max_tokens'] > 8192:
            errors.append("LLM config: 'max_tokens' must be <= 8192")

        # Validate temperature
        if 'temperature' not in llm_data:
            errors.append("LLM config: missing required field 'temperature'")
        elif not isinstance(llm_data['temperature'], (int, float)):
            errors.append("LLM config: 'temperature' must be a number")
        elif llm_data['temperature'] < 0 or llm_data['temperature'] > 1:
            errors.append("LLM config: 'temperature' must be between 0 and 1")

        if errors:
            return None, errors

        return LLMConfig(
            model=llm_data['model'],
            max_tokens=llm_data['max_tokens'],
            temperature=float(llm_data['temperature'])
        ), []


def load_spec(spec_name: str, spec_dir: Path = None) -> AnalysisSpec:
    """
    Convenience function to load a spec

    Args:
        spec_name: Name of spec file (with or without .json extension)
        spec_dir: Optional custom spec directory

    Returns:
        Validated AnalysisSpec object
    """
    loader = SpecLoader(spec_dir)
    return loader.load(spec_name)

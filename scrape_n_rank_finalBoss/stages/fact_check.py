import os
import csv
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from stages.base import BaseStage

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


FC_OUTPUT_FIELDS = [
    "fc_verified", "fc_acquirer_name", "fc_target_company_name",
    "fc_deal_value", "fc_deal_date", "fc_deal_status",
    "fc_ai_vertical", "fc_deal_type", "fc_corrections",
    "fc_confidence", "fc_citations",
]


class FactCheckStage(BaseStage):
    STAGE_NAME = "fact_check"

    def run(self, input_data) -> Dict[str, Any]:
        """input_data: dict with 'deduped_csv' or 'results_csv' path."""
        input_csv = None
        if isinstance(input_data, dict):
            input_csv = input_data.get('deduped_csv') or input_data.get('results_csv', '')

        if not input_csv:
            # Try to find deduped or results
            deduped = self.output.output_dir / "deduped_results.csv"
            results = self.output.output_dir / "results.csv"
            input_csv = str(deduped if deduped.exists() else results)

        input_path = Path(input_csv)
        if not input_path.exists():
            self.logger.warning(f"Fact-check: Input CSV not found: {input_csv}")
            return {}

        output_path = self.output.output_dir / "factchecked_results.csv"

        model = self.config.get('model', 'sonar')
        concurrency = self.config.get('concurrency', 3)
        fields_to_verify = self.config.get('fields_to_verify', [
            "acquirer_name", "target_company_name", "deal_value",
            "deal_date", "deal_status", "ai_vertical", "deal_type"
        ])
        key_field = "target_company_name"  # Get from dedupe config if available

        self.analytics.start_stage("fact_check")

        stats = self._fact_check(input_path, output_path, model, concurrency, fields_to_verify, key_field)

        self.analytics.complete_stage("fact_check")

        return {"factchecked_csv": str(output_path), "stats": stats}

    def _fact_check(self, input_csv, output_csv, model, concurrency, fields, key_field) -> dict:
        """Core fact-checking logic using Perplexity."""
        # Read all rows
        rows = []
        with open(input_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames)
            for row in reader:
                rows.append(row)

        # Find rows that need fact-checking (DEAL_FOUND or similar positive classification)
        deal_rows = [r for r in rows if r.get('classification') not in ('NOT_MNA', 'DISQUALIFIED', 'not_qualified')]
        other_rows = [r for r in rows if r.get('classification') in ('NOT_MNA', 'DISQUALIFIED', 'not_qualified')]

        self.logger.info(f"Fact-check: {len(deal_rows)} deals to verify, {len(other_rows)} skipped")

        # Group by key and pick best representative
        groups = defaultdict(list)
        for row in deal_rows:
            key = (row.get(key_field) or '').strip().lower()
            if key:
                groups[key].append(row)
            else:
                groups[id(row)] = [row]

        representatives = {}
        for key, group in groups.items():
            best = max(group, key=lambda r: sum(1 for v in r.values() if v and str(v).strip()))
            representatives[key] = best

        deals_to_check = list(representatives.values())
        self.logger.info(f"  Sending {len(deals_to_check)} unique deals to Perplexity ({model})")

        # Run fact-checks
        fc_results = asyncio.run(
            self._run_async_checks(deals_to_check, fields, model, concurrency)
        )

        # Map back to keys
        fc_by_key = {}
        for deal_row, fc_data in zip(deals_to_check, fc_results):
            key = (deal_row.get(key_field) or '').strip().lower()
            fc_by_key[key] = fc_data

        # Attach to all rows
        output_fieldnames = fieldnames + [f for f in FC_OUTPUT_FIELDS if f not in fieldnames]

        for row in rows:
            key = (row.get(key_field) or '').strip().lower()
            if key in fc_by_key:
                row.update(fc_by_key[key])
            else:
                for f in FC_OUTPUT_FIELDS:
                    row.setdefault(f, '')

        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=output_fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        verified = sum(1 for v in fc_by_key.values() if v.get('fc_verified') == 'true')

        return {
            "total_checked": len(deals_to_check),
            "verified": verified,
            "not_verified": len(deals_to_check) - verified,
        }

    async def _run_async_checks(self, deals, fields, model, concurrency):
        api_key = os.environ.get("PERPLEXITY_API_KEY")
        if not api_key:
            raise ValueError("PERPLEXITY_API_KEY not set")

        client = AsyncOpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        sem = asyncio.Semaphore(concurrency)

        tasks = [self._verify_deal(client, deal, fields, model, sem) for deal in deals]
        return await asyncio.gather(*tasks)

    async def _verify_deal(self, client, row, fields, model, sem):
        async with sem:
            try:
                lines = []
                for f in fields:
                    val = row.get(f, '')
                    if val:
                        lines.append(f"- {f.replace('_', ' ').title()}: {val}")
                deal_desc = "\n".join(lines) or "- (no details)"

                prompt = f"""Verify this transaction using web search. Return JSON only.

Claimed:
{deal_desc}

JSON: {{"deal_verified":bool,"acquirer_name":"...","target_company_name":"...","deal_value":"...","deal_date":"...","deal_status":"...","ai_vertical":"...","deal_type":"...","corrections":"...","confidence":"high/medium/low"}}"""

                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Verify M&A deals. Return only JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                )

                raw = response.choices[0].message.content
                citations = getattr(response, 'citations', None)
                return self._parse_fc_response(raw, citations)

            except Exception as e:
                result = {f: '' for f in FC_OUTPUT_FIELDS}
                result['fc_corrections'] = f"API error: {str(e)[:200]}"
                return result

    def _parse_fc_response(self, raw, citations):
        result = {f: '' for f in FC_OUTPUT_FIELDS}
        try:
            data = json.loads(raw)
            result['fc_verified'] = str(data.get('deal_verified', '')).lower()
            result['fc_acquirer_name'] = data.get('acquirer_name') or ''
            result['fc_target_company_name'] = data.get('target_company_name') or ''
            result['fc_deal_value'] = data.get('deal_value') or ''
            result['fc_deal_date'] = data.get('deal_date') or ''
            result['fc_deal_status'] = data.get('deal_status') or ''
            result['fc_ai_vertical'] = data.get('ai_vertical') or ''
            result['fc_deal_type'] = data.get('deal_type') or ''
            result['fc_corrections'] = data.get('corrections') or ''
            result['fc_confidence'] = data.get('confidence') or ''
            if citations:
                result['fc_citations'] = ' | '.join(citations)
        except (json.JSONDecodeError, TypeError):
            result['fc_corrections'] = f"Parse error: {raw[:200]}"
        return result

#!/usr/bin/env python3
"""
Analyze L3 outputs for hospital and university affiliations
"""

import json
import glob
import os

# Find all L3 output files from today's run with hospital/university data (latest versions only)
l3_files = glob.glob('l3_llm_classify/outputs/l3_classified_*_20251106_13[2-3]*.json')

print("=" * 70)
print("HOSPITAL & UNIVERSITY AFFILIATION ANALYSIS")
print("=" * 70)
print(f"\nAnalyzing {len(l3_files)} L3 output files...\n")

total_clinics = 0
hospital_or_dept = 0
university_affiliated = 0
both_hospital_and_university = 0
neither = 0

clinic_details = []

for l3_file in sorted(l3_files):
    with open(l3_file, 'r') as f:
        data = json.load(f)

    query = data.get('metadata', {}).get('query', 'Unknown')
    print(f"Processing: {query}")

    for page in data.get('pages', []):
        classification = page.get('classification', '')

        # Only count actual clinics
        if classification in ['neurology_clinic_individual', 'neurology_clinic_group']:
            total_clinics += 1

            # Check hospital/dept status
            is_hospital = page.get('is_hospital_or_dept', {}).get('answer', 'no') == 'yes'

            # Check university affiliation
            is_university = page.get('university_affiliated', {}).get('answer', 'no') == 'yes'

            # Count categories
            if is_hospital and is_university:
                both_hospital_and_university += 1
            elif is_hospital:
                hospital_or_dept += 1
            elif is_university:
                university_affiliated += 1
            else:
                neither += 1

            # Store details for interesting cases
            if is_hospital or is_university:
                clinic_details.append({
                    'url': page.get('url'),
                    'name': page.get('extracted_data', {}).get('clinic_name', 'Unknown'),
                    'is_hospital': is_hospital,
                    'hospital_reasoning': page.get('is_hospital_or_dept', {}).get('reasoning', ''),
                    'is_university': is_university,
                    'university_reasoning': page.get('university_affiliated', {}).get('reasoning', '')
                })

print("\n" + "=" * 70)
print("SUMMARY RESULTS")
print("=" * 70)
print(f"\nTotal Clinics Found: {total_clinics}")
print(f"\nBreakdown:")
print(f"  - Hospital/Dept ONLY: {hospital_or_dept} ({100*hospital_or_dept/total_clinics:.1f}%)")
print(f"  - University ONLY: {university_affiliated} ({100*university_affiliated/total_clinics:.1f}%)")
print(f"  - BOTH Hospital AND University: {both_hospital_and_university} ({100*both_hospital_and_university/total_clinics:.1f}%)")
print(f"  - NEITHER: {neither} ({100*neither/total_clinics:.1f}%)")

total_with_affiliation = hospital_or_dept + university_affiliated + both_hospital_and_university
print(f"\n✅ Total with Hospital OR University: {total_with_affiliation} ({100*total_with_affiliation/total_clinics:.1f}%)")
print(f"❌ Total with NEITHER: {neither} ({100*neither/total_clinics:.1f}%)")

print("\n" + "=" * 70)
print("SAMPLE HOSPITAL/UNIVERSITY CLINICS (First 10)")
print("=" * 70)
for i, clinic in enumerate(clinic_details[:10], 1):
    print(f"\n{i}. {clinic['name']}")
    print(f"   URL: {clinic['url'][:60]}...")
    if clinic['is_hospital']:
        print(f"   🏥 Hospital: {clinic['hospital_reasoning'][:80]}")
    if clinic['is_university']:
        print(f"   🎓 University: {clinic['university_reasoning'][:80]}")

print("\n" + "=" * 70)

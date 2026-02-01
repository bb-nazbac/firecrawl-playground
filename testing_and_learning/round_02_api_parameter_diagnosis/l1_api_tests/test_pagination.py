#!/usr/bin/env python3
"""Test if Firecrawl v2 /search supports pagination"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv('../../../.env')
api_key = os.getenv('FIRECRAWL_API_KEY')

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

base_url = "https://api.firecrawl.dev/v2/search"

print("=" * 70)
print("PAGINATION TESTING - Can we get results beyond first 100?")
print("=" * 70)
print()

# Baseline: First 10 results
print("BASELINE: First 10 results")
resp = requests.post(base_url, json={
    "query": "clínica dental Madrid",
    "limit": 10
}, headers=headers)
if resp.status_code == 200:
    data = resp.json()
    results = data['data']['web']
    print(f"  ✅ Got {len(results)} results")
    print(f"  First: {results[0]['title'][:60]}...")
    print(f"  Last:  {results[-1]['title'][:60]}...")
    baseline_first = results[0]['url']
    baseline_last = results[-1]['url']
else:
    print(f"  ❌ Failed: {resp.status_code}")
    baseline_first = None
    baseline_last = None

print()

# Test 1: offset parameter
print("TEST 1: 'offset' parameter (results 10-19)")
resp = requests.post(base_url, json={
    "query": "clínica dental Madrid",
    "limit": 10,
    "offset": 10
}, headers=headers)
print(f"  HTTP: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    if 'data' in data and 'web' in data['data']:
        results = data['data']['web']
        print(f"  ✅ Got {len(results)} results")
        if results:
            print(f"  First: {results[0]['title'][:60]}...")
            # Check if this is different from baseline (proves pagination works)
            if results[0]['url'] != baseline_first:
                print(f"  🎉 DIFFERENT from baseline! Pagination works with 'offset'!")
            else:
                print(f"  ⚠️  Same as baseline (pagination not working)")
else:
    data = resp.json()
    print(f"  ❌ Error: {data.get('error', 'Unknown')}")

print()

# Test 2: page parameter
print("TEST 2: 'page' parameter (page 2)")
resp = requests.post(base_url, json={
    "query": "clínica dental Madrid",
    "limit": 10,
    "page": 2
}, headers=headers)
print(f"  HTTP: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    if 'data' in data and 'web' in data['data']:
        results = data['data']['web']
        print(f"  ✅ Got {len(results)} results")
        if results and results[0]['url'] != baseline_first:
            print(f"  🎉 Pagination works with 'page'!")
else:
    data = resp.json()
    print(f"  ❌ Error: {data.get('error', 'Unknown')}")

print()

# Test 3: skip parameter
print("TEST 3: 'skip' parameter (skip first 10)")
resp = requests.post(base_url, json={
    "query": "clínica dental Madrid",
    "limit": 10,
    "skip": 10
}, headers=headers)
print(f"  HTTP: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    if 'data' in data and 'web' in data['data']:
        results = data['data']['web']
        print(f"  ✅ Got {len(results)} results")
        if results and results[0]['url'] != baseline_first:
            print(f"  🎉 Pagination works with 'skip'!")
else:
    data = resp.json()
    print(f"  ❌ Error: {data.get('error', 'Unknown')}")

print()

# Test 4: start parameter
print("TEST 4: 'start' parameter")
resp = requests.post(base_url, json={
    "query": "clínica dental Madrid",
    "limit": 10,
    "start": 10
}, headers=headers)
print(f"  HTTP: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    if 'data' in data and 'web' in data['data']:
        results = data['data']['web']
        print(f"  ✅ Got {len(results)} results")
        if results and results[0]['url'] != baseline_first:
            print(f"  🎉 Pagination works with 'start'!")
else:
    data = resp.json()
    print(f"  ❌ Error: {data.get('error', 'Unknown')}")

print()
print("=" * 70)
print("TESTING COMPLETE")
print("=" * 70)

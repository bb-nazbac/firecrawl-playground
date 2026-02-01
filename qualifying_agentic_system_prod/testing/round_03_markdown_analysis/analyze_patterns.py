#!/usr/bin/env python3
"""Analyze markdown patterns to find strippable content."""

import re
from pathlib import Path

SAMPLES_DIR = Path(__file__).parent / 'samples'

def analyze_markdown(content: str, domain: str) -> dict:
    """Analyze a markdown file for strippable patterns."""
    original_chars = len(content)
    original_lines = len(content.split('\n'))

    patterns = {}

    # 1. Empty lines (consecutive newlines)
    empty_lines = len(re.findall(r'\n\s*\n', content))
    patterns['empty_lines'] = {
        'count': empty_lines,
        'example': '(consecutive blank lines)'
    }

    # 2. Image markdown: ![alt](url) or [![alt](url)](url)
    images = re.findall(r'!?\[(?:[^\]]*)\]\([^)]+\)', content)
    image_chars = sum(len(img) for img in images)
    patterns['image_markdown'] = {
        'count': len(images),
        'chars': image_chars,
        'example': images[0][:80] + '...' if images else 'N/A'
    }

    # 3. SVG data URLs (HUGE!)
    svg_data = re.findall(r'data:image/svg\+xml[^)]+', content)
    svg_chars = sum(len(s) for s in svg_data)
    patterns['svg_data_urls'] = {
        'count': len(svg_data),
        'chars': svg_chars,
        'example': 'data:image/svg+xml,...' if svg_data else 'N/A'
    }

    # 4. Skip to content links
    skip_links = re.findall(r'\[Skip to [^\]]+\]\([^)]+\)', content, re.IGNORECASE)
    patterns['skip_links'] = {
        'count': len(skip_links),
        'chars': sum(len(s) for s in skip_links)
    }

    # 5. reCAPTCHA / Privacy / Terms
    recaptcha = re.findall(r'(?:reCAPTCHA|Recaptcha|Privacy.*Terms|protected by)', content, re.IGNORECASE)
    patterns['recaptcha_privacy'] = {
        'count': len(recaptcha),
    }

    # 6. Copyright lines
    copyright_lines = re.findall(r'©.*?\n|Copyright.*?\n', content)
    patterns['copyright'] = {
        'count': len(copyright_lines),
        'chars': sum(len(c) for c in copyright_lines)
    }

    # 7. Social media links (Facebook, Twitter, Instagram, etc.)
    social = re.findall(r'\[(?:Facebook|Twitter|Instagram|Linkedin|Youtube|Tiktok|X,|Visit us on)[^\]]*\]\([^)]+\)', content, re.IGNORECASE)
    patterns['social_links'] = {
        'count': len(social),
        'chars': sum(len(s) for s in social)
    }

    # 8. App store buttons
    app_store = re.findall(r'\[!\[Download.*?App\].*?\]\([^)]+\)', content, re.IGNORECASE)
    patterns['app_store_buttons'] = {
        'count': len(app_store),
        'chars': sum(len(a) for a in app_store)
    }

    # 9. Squarespace/CDN URLs (verbose)
    cdn_urls = re.findall(r'https://[^)]*(?:squarespace-cdn|cloudinary|cdn|wp-content/uploads)[^)]*', content)
    patterns['cdn_urls'] = {
        'count': len(cdn_urls),
        'chars': sum(len(c) for c in cdn_urls)
    }

    # Calculate strippable chars
    strippable = (
        patterns['svg_data_urls']['chars'] +
        patterns['image_markdown']['chars'] +
        patterns['social_links']['chars'] +
        patterns['app_store_buttons']['chars'] +
        patterns['copyright']['chars'] +
        patterns['skip_links']['chars']
    )

    return {
        'domain': domain,
        'original_chars': original_chars,
        'original_lines': original_lines,
        'strippable_chars': strippable,
        'reduction_pct': round(strippable / original_chars * 100, 1),
        'patterns': patterns
    }


def strip_markdown(content: str) -> str:
    """Apply all stripping patterns to markdown."""

    # 1. Remove SVG data URLs entirely (replace image with placeholder)
    content = re.sub(r'!\[([^\]]*)\]\(data:image/svg\+xml[^)]+\)', r'[ICON]', content)

    # 2. Remove image markdown (keep alt text if meaningful)
    content = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'[\1]', content)

    # 3. Remove linked images [![...](img)](link) -> just keep link text
    content = re.sub(r'\[!\[[^\]]*\]\([^)]+\)\]\(([^)]+)\)', r'[Link: \1]', content)

    # 4. Remove skip to content
    content = re.sub(r'\[Skip to [^\]]+\]\([^)]+\)\n*', '', content, flags=re.IGNORECASE)

    # 5. Remove reCAPTCHA sections
    content = re.sub(r'reCAPTCHA.*?Terms\)', '', content, flags=re.IGNORECASE | re.DOTALL)

    # 6. Collapse multiple blank lines to single
    content = re.sub(r'\n{3,}', '\n\n', content)

    # 7. Remove social media icon links
    content = re.sub(r'\[(?:Facebook|Twitter|Instagram|Linkedin|Youtube|Tiktok)[^\]]*\]\([^)]+\)', '', content, flags=re.IGNORECASE)

    # 8. Remove app store buttons
    content = re.sub(r'\[!\[Download.*?App\].*?\]\([^)]+\)', '', content, flags=re.IGNORECASE)

    # 9. Remove copyright lines
    content = re.sub(r'(?:©|Copyright).*?\n', '', content)

    return content.strip()


def main():
    print("="*70)
    print("MARKDOWN PATTERN ANALYSIS")
    print("="*70)

    for md_file in sorted(SAMPLES_DIR.glob('*_raw.md')):
        content = md_file.read_text()
        domain = md_file.stem.replace('_raw', '').replace('_', '.')

        analysis = analyze_markdown(content, domain)

        print(f"\n{domain}")
        print("-"*50)
        print(f"Original: {analysis['original_chars']:,} chars, {analysis['original_lines']} lines")
        print(f"Strippable: ~{analysis['strippable_chars']:,} chars ({analysis['reduction_pct']}%)")
        print()

        for pattern, data in analysis['patterns'].items():
            if data.get('count', 0) > 0:
                chars = data.get('chars', 0)
                print(f"  {pattern}: {data['count']} occurrences" + (f" ({chars:,} chars)" if chars else ""))

    print("\n" + "="*70)
    print("STRIPPED MARKDOWN COMPARISON")
    print("="*70)

    for md_file in sorted(SAMPLES_DIR.glob('*_raw.md')):
        content = md_file.read_text()
        domain = md_file.stem.replace('_raw', '').replace('_', '.')

        stripped = strip_markdown(content)

        # Save stripped version
        stripped_file = md_file.parent / md_file.name.replace('_raw', '_stripped')
        stripped_file.write_text(stripped)

        reduction = (1 - len(stripped) / len(content)) * 100
        print(f"\n{domain}:")
        print(f"  Before: {len(content):,} chars")
        print(f"  After:  {len(stripped):,} chars")
        print(f"  Reduction: {reduction:.1f}%")


if __name__ == '__main__':
    main()

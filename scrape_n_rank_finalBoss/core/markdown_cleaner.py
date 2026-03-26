"""
Markdown cleaner utility to strip useless content before sending to LLM.

Strips:
- SVG data URLs (huge inline icons)
- Base64 image data URLs
- Image markdown (URLs provide no value for qualification)
- Skip to content links
- reCAPTCHA/Privacy/Terms boilerplate
- Social media icon links
- App store buttons
- Copyright lines
- "Powered by" lines
- Empty link placeholders
- Excessive blank lines
"""

import re


def strip_markdown(content: str) -> str:
    """
    Strip useless patterns from markdown to reduce token count.

    Preserves:
    - Headings and text content
    - Regular links (for navigation context)
    - Lists and structure

    Removes:
    - Images and SVGs (no value for text-based qualification)
    - Boilerplate (copyright, reCAPTCHA, social links)
    - Excessive whitespace

    Args:
        content: Raw markdown string

    Returns:
        Cleaned markdown with ~20-60% fewer characters
    """
    if not content:
        return content

    # 1. Remove SVG data URLs entirely
    # These are inline base64/SVG icons that can be 5-30k chars each
    content = re.sub(r'!\[[^\]]*\]\(data:image/svg\+xml[^)]+\)', '', content)

    # 2. Remove base64 image data URLs
    content = re.sub(r'!\[[^\]]*\]\(data:image/[^)]+\)', '', content)

    # 3. Remove image markdown ![alt](url) - keep alt text if meaningful
    # But for most cases, alt text is empty or generic
    content = re.sub(
        r'!\[([^\]]*)\]\([^)]+\)',
        lambda m: f'[{m.group(1)}]' if m.group(1) and len(m.group(1)) > 2 else '',
        content
    )

    # 4. Remove linked images [![alt](img)](link) -> keep link only
    content = re.sub(r'\[!\[[^\]]*\]\([^)]+\)\]\(([^)]+)\)', r'[Link](\1)', content)

    # 5. Remove skip to content links
    content = re.sub(r'\[Skip to [^\]]+\]\([^)]+\)\s*', '', content, flags=re.IGNORECASE)

    # 6. Remove reCAPTCHA sections
    content = re.sub(
        r'reCAPTCHA.*?(?:\[Terms\]\([^)]+\)|\n\n)',
        '',
        content,
        flags=re.IGNORECASE | re.DOTALL
    )
    content = re.sub(
        r'protected by \*\*reCAPTCHA\*\*.*?Terms\)',
        '',
        content,
        flags=re.IGNORECASE | re.DOTALL
    )

    # 7. Remove social media icon links
    social_patterns = [
        r'\[(?:Facebook|Twitter|Instagram|Linkedin|Youtube|Tiktok|Pinterest|X)[^\]]*\]\([^)]+\)\s*',
        r'\[Visit us on (?:Facebook|Twitter|Instagram|X|LinkedIn|YouTube)[^\]]*\]\([^)]+\)\s*',
        r'\[Follow us on (?:Facebook|Twitter|Instagram|X|LinkedIn|YouTube)[^\]]*\]\([^)]+\)\s*',
    ]
    for pattern in social_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE)

    # 8. Remove app store buttons (iOS/Android download links with images)
    content = re.sub(
        r'\[!\[Download[^\]]*App\][^\]]*\]\([^)]+\)\s*',
        '',
        content,
        flags=re.IGNORECASE
    )
    content = re.sub(
        r'\[(?:Download on the App Store|Get it on Google Play)[^\]]*\]\([^)]+\)\s*',
        '',
        content,
        flags=re.IGNORECASE
    )

    # 9. Remove copyright lines
    content = re.sub(r'(?:©|Copyright)[^\n]*(?:\n|$)', '', content, flags=re.IGNORECASE)

    # 10. Remove "Powered by" lines
    content = re.sub(r'Powered [Bb]y[^\n]*(?:\n|$)', '', content)

    # 11. Remove empty link placeholders we created
    content = re.sub(r'\[\]\([^)]+\)', '', content)
    content = re.sub(r'\[\s*\]', '', content)

    # 12. Collapse multiple blank lines to max 2
    content = re.sub(r'\n{3,}', '\n\n', content)

    # 13. Remove lines that are just whitespace
    content = re.sub(r'\n\s+\n', '\n\n', content)

    # 14. Remove trailing backslashes from broken markdown
    content = re.sub(r'\\\s*\n', '\n', content)

    return content.strip()


def get_reduction_stats(original: str, stripped: str) -> dict:
    """
    Get statistics about the reduction achieved by stripping.

    Args:
        original: Original markdown content
        stripped: Stripped markdown content

    Returns:
        Dict with original_chars, stripped_chars, chars_saved, reduction_pct
    """
    orig_chars = len(original)
    stripped_chars = len(stripped)

    return {
        'original_chars': orig_chars,
        'stripped_chars': stripped_chars,
        'chars_saved': orig_chars - stripped_chars,
        'reduction_pct': round((1 - stripped_chars / orig_chars) * 100, 1) if orig_chars > 0 else 0
    }

import httpx
import re

r = httpx.get(
    "https://www.brenda-enzymes.org/enzyme.php",
    params={"ecno": "1.1.1.27"},
    timeout=15
)

html = r.text

# Search for Km value patterns in the raw HTML
# BRENDA typically embeds data in tables with patterns like "0.09" near "Homo sapiens"
km_patterns = re.findall(
    r'(\d+\.?\d*)\s*(?:mM|µM|uM|nM)',
    html
)

human_sections = []
lines = html.split('\n')
for i, line in enumerate(lines):
    if 'Homo sapiens' in line or 'homo sapiens' in line.lower():
        # grab surrounding context
        context = '\n'.join(lines[max(0,i-2):i+3])
        human_sections.append(context)

print(f"Total Km-like values found in page: {len(km_patterns)}")
print(f"First 10: {km_patterns[:10]}")
print(f"\nHomo sapiens mentions: {len(human_sections)}")
print("\nFirst 2 human contexts:")
for ctx in human_sections[:2]:
    print("---")
    print(ctx[:300])

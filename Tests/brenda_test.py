import httpx

# BRENDA REST endpoint - test if accessible
try:
    r = httpx.get(
        "https://www.brenda-enzymes.org/index.php",
        params={"ecNumber": "1.1.1.27"},
        timeout=8
    )
    print("BRENDA web:", r.status_code)
except Exception as e:
    print("BRENDA web failed:", e)

# BRENDA has a public API endpoint - test it
try:
    r2 = httpx.get(
        "https://www.brenda-enzymes.org/enzyme.php",
        params={"ecno": "1.1.1.27"},
        timeout=8
    )
    print("BRENDA enzyme page:", r2.status_code, len(r2.text), "chars returned")
except Exception as e:
    print("BRENDA enzyme page failed:", e)
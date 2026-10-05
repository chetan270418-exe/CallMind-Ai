import urllib.request, json

pins = [
    'fastapi==0.115.6',
    'uvicorn==0.32.1',
    'pydantic==2.10.3',
    'pydantic-settings==2.7.0',
    'email-validator==2.2.0',
    'sqlalchemy==2.0.36',
    'rapidfuzz==3.11.1',
    'twilio==9.4.1',
    'bcrypt==4.0.1',
    'passlib==1.7.4',
    'python-jose==3.3.0',
    'python-multipart==0.0.20',
]

ok = True
for p in pins:
    name, want = p.split('==')
    url = f'https://pypi.org/pypi/{name}/json'
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.load(r)
            releases = data.get('releases', {})
            version = releases.get(want)
            latest = max(releases.keys(), key=lambda v: tuple(int(x) for x in v.split('.') if x.isdigit())) if releases else '?'
            if version is None:
                print(f'  MISSING  {name:24s} wanted {want}   latest={latest}')
                ok = False
            else:
                print(f'  ok       {name:24s} wanted {want}')
    except Exception as e:
        print(f'  ERR      {name:24s} {e}')
        ok = False

print()
print('All pins valid' if ok else 'Some pins are INVALID - fix these')
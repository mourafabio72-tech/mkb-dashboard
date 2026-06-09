import sys; sys.path.insert(0,'.')
from app import app
with app.test_client() as c:
    r = c.get('/ingest')
    html = r.data.decode('utf-8', errors='replace')
    checks = {
        "status 200":         r.status_code == 200,
        "checkbox empresa_ct2": "empresa_ct2" in html,
        "opcao mkb":          'value="mkb"' in html,
        "opcao gnileb":       'value="gnileb"' in html,
        "CT1 upload present": "arquivo_ct1" in html,
    }
    for nome, ok in checks.items():
        print(f"  {'OK' if ok else 'FALHOU'}  {nome}")

all_ok = all(checks.values())
print()
print("Todos os testes passaram!" if all_ok else "FALHA!")
sys.exit(0 if all_ok else 1)

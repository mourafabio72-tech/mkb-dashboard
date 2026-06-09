from app import app

print("=== URL MAP COMPLETO ===")
for rule in sorted(app.url_map.iter_rules(), key=str):
    print(f"  {str(rule):<45}  [{', '.join(rule.methods)}]  -> {rule.endpoint}")

print("\n=== TESTE DE ROUTING ===")
urls_test = ["/dre/2026-04", "/dre/mensal/mkb", "/dre/mensal/consolidado", "/dre/mensal/mkb/detalhada"]
for url in urls_test:
    with app.test_request_context(url):
        from flask import request
        print(f"  {url:<40}  endpoint={request.endpoint}  args={request.view_args}")

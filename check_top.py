from dre_engine import calcular_top_custo, calcular_top_despesa

comps = ["2026-01","2026-02","2026-03","2026-04"]

c = calcular_top_custo(comps, 10)
d = calcular_top_despesa(comps, 10)

print(f"Top 10 CUSTO ({len(c)} contas):")
for x in c:
    print(f"  {x['label'][:35]:35s}  R$ {x['valor']:>12,}")

print(f"\nTop 10 DESPESA ({len(d)} contas):")
for x in d:
    print(f"  {x['label'][:35]:35s}  R$ {x['valor']:>12,}")

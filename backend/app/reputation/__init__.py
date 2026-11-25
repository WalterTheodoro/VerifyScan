"""Reputação de links (ADR-0028): o que o Google Safe Browsing e o VirusTotal dizem do domínio.

`verificador.py` é o URLChecker do RFC (§5.4.4); `safe_browsing.py` e `virustotal.py` falam
com cada base; `fatores.py` transforma o que elas apontaram em fatores do motor. Nos testes, o
transporte HTTP é falso: nenhuma chamada sai para a rede.
"""

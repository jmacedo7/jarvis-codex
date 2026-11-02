import re
from pathlib import Path


def ler_env(caminho):
    """Lê um .env simples sem executar shell ou interpolar variáveis."""
    valores = {}
    arquivo = Path(caminho).expanduser()
    try:
        linhas = arquivo.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return valores
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith("export "):
            linha = linha[7:].lstrip()
        if "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        valor = valor.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", chave):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in ("'", '"'):
            valor = valor[1:-1]
        valores[chave] = valor
    return valores


def atualizar_env(caminho, atualizacoes):
    """Atualiza somente as chaves indicadas, preservando comentários e segredos."""
    arquivo = Path(caminho)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    try:
        linhas = arquivo.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        linhas = []
    atualizacoes = {str(k): str(v) for k, v in atualizacoes.items()}
    gravadas = set()
    resultado = []
    for linha in linhas:
        candidata = linha.strip()
        if candidata.startswith("export "):
            candidata = candidata[7:].lstrip()
        if "=" in candidata and not candidata.startswith("#"):
            chave = candidata.split("=", 1)[0].strip()
            if chave in atualizacoes:
                if chave in gravadas:
                    continue
                resultado.append(f"{chave}={atualizacoes[chave]}")
                gravadas.add(chave)
                continue
        resultado.append(linha)
    for chave, valor in atualizacoes.items():
        if chave not in gravadas:
            resultado.append(f"{chave}={valor}")
    temporario = arquivo.with_name(arquivo.name + ".tmp")
    temporario.write_text("\n".join(resultado).rstrip() + "\n", encoding="utf-8")
    temporario.replace(arquivo)

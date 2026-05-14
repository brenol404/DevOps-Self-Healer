import os
import subprocess

def criar_projeto_cobaia():
    """Cria o ambiente de teste 'projeto_cobaia' com um erro lógico."""
    pasta_cobaia = "projeto_cobaia"
    os.makedirs(pasta_cobaia, exist_ok=True)
    
    # Módulo com erro intencional que requer pesquisa na documentação de uma API
    calc_code = """import urllib.request
import json

def buscar_dados_pokemon(nome):
    # Erro: Rota inexistente (v99). O correto é 'v2'.
    url = f"https://pokeapi.co/api/v99/pokemon/{nome}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())
"""

    # Teste unitário (deve falhar pois a API retornará erro HTTP 404)
    test_code = """from calculadora import buscar_dados_pokemon

def test_buscar_dados_pokemon():
    dados = buscar_dados_pokemon("pikachu")
    assert dados is not None
    assert dados["name"] == "pikachu"
"""

    with open(os.path.join(pasta_cobaia, "calculadora.py"), "w", encoding="utf-8") as f:
        f.write(calc_code)
        
    with open(os.path.join(pasta_cobaia, "test_calculadora.py"), "w", encoding="utf-8") as f:
        f.write(test_code)
        
    # Inicializa um repositório git para podermos testar o auto-commit
    try:
        subprocess.run(["git", "init"], cwd=pasta_cobaia, capture_output=True, check=True)
        subprocess.run(["git", "add", "."], cwd=pasta_cobaia, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "feat: projeto inicial com bug"], cwd=pasta_cobaia, capture_output=True, check=True)
    except Exception as e:
        print(f"Aviso: Não foi possível inicializar o Git na pasta. Certifique-se de que o Git está instalado. ({e})")

    print(f"Projeto cobaia criado com sucesso na pasta '{pasta_cobaia}'.")

if __name__ == "__main__":
    criar_projeto_cobaia()
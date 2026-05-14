import os
import subprocess

def criar_projeto_cobaia():
    """Cria o ambiente de teste 'projeto_cobaia' com um erro lógico."""
    pasta_cobaia = "projeto_cobaia"
    os.makedirs(pasta_cobaia, exist_ok=True)
    
    # Módulo com erro intencional
    calc_code = """def somar(a, b):
    # Erro: subtraindo em vez de somar
    return a - b
"""

    # Teste unitário (deve falhar)
    test_code = """from calculadora import somar

def test_somar():
    # Valida a soma de 2 + 3
    assert somar(2, 3) == 5
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
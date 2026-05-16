import os
import subprocess

def criar_projeto_cobaia():
    """Cria o ambiente de teste 'projeto_cobaia' com um erro quádruplo!"""
    pasta_cobaia = "projeto_cobaia"
    os.makedirs(pasta_cobaia, exist_ok=True)
    
    # 1. user.py
    user_code = '''class User:
    def __init__(self, name):
        self.name = name
        self.is_active = True
        
    def deactivate(self):
        self.is_actv = False  # ERRO 1: Typo no atributo
'''

    # 2. cart.py
    cart_code = '''class Cart:
    def __init__(self):
        self.items = []
        
    def add_item(self, item):
        self.item.append(item)  # ERRO 2: Typo no atributo (self.item)
        
    def get_total(self):
        return sum([item.price for item in self.items])
'''

    # 3. payment.py
    payment_code = '''def process_payment(cart, user):
    if not user.is_active:
        raise ValueError("User inactive")
    return cart.get_total() - 10  # ERRO 3: Lógica errada, subtraindo 10
'''

    # 4. email_service.py
    email_code = '''def send_receipt(user, amount):
    return f"Receipt sent to {user.nome} for {amount}"  # ERRO 4: Atributo errado
'''

    # 5. test_integration.py
    test_code = '''from user import User
from cart import Cart
from payment import process_payment
from email_service import send_receipt

class DummyItem:
    def __init__(self, price):
        self.price = price

def test_user_deactivation():
    u = User("Alice")
    u.deactivate()
    assert u.is_active is False

def test_cart_add_item():
    c = Cart()
    c.add_item(DummyItem(50))
    assert len(c.items) == 1

def test_payment_processing():
    c = Cart()
    c.items = [DummyItem(50), DummyItem(50)]
    u = User("Bob")
    total = process_payment(c, u)
    assert total == 100

def test_email_receipt():
    u = User("Charlie")
    msg = send_receipt(u, 100)
    assert "Charlie" in msg
'''

    arquivos = {
        "user.py": user_code,
        "cart.py": cart_code,
        "payment.py": payment_code,
        "email_service.py": email_code,
        "test_integration.py": test_code
    }

    for nome, conteudo in arquivos.items():
        with open(os.path.join(pasta_cobaia, nome), "w", encoding="utf-8") as f:
            f.write(conteudo)
        
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
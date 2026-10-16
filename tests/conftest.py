import os
import sys

# Permite importar as funcoes de src/ nos testes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

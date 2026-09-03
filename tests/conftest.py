import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "src"))
# Fake CRM — частина тестового стенда: контракт із CRM має перевірятися
# виконанням, а не лише читанням документа (D-056).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "tools"))

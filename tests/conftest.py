import sys
from pathlib import Path

# Дозволяє `pytest` з кореня репо без встановлення пакета
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

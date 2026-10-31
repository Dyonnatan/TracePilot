import os
import sys
from pathlib import Path

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("FRAUD_SCORE_ITERATIONS", "1000")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

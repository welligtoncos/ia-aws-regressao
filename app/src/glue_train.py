"""
Ponto de entrada do AWS Glue Job para treino XGBoost.
Script principal no S3; biblioteca em --extra-py-files (src/*.py).
"""

try:
    from src.main import main
except ImportError:
    from app.src.main import main

if __name__ == "__main__":
    main()

# QUANTLOG 1.0 — Institutional Trading Journal & Quantitative Risk Engine

QUANTLOG es un entorno integral de registro de operaciones, análisis biométrico-conductual y simulación estocástica de riesgo diseñado para traders independientes y operadores de firmas de fondeo (Prop Firms).

El sistema implementa una arquitectura **CQRS (Command Query Responsibility Segregation)**, delegando el cálculo de derivadas financieras al motor relacional, mientras mantiene una interfaz reactiva *offline-first* para operaciones en caliente.

## 🚀 Características Principales
- **Motor Cuantitativo de Riesgo (Quant Lab):** Simulación Monte Carlo, Bootstrap Resampling y Atribución de Eficiencia (MAE/MFE).
- **Biometría Conductual y Psicología:** Detección automatizada de *revenge trading* y overtrading.
- **Arquitectura Híbrida (API / Offline-First):** Cálculo determinista de métricas nativo en MariaDB.

## 🛠 Stack Tecnológico
- **Frontend:** React 18, Tailwind CSS, Lightweight Charts.
- **Backend:** Python, FastAPI, Uvicorn, Pydantic.
- **Base de Datos:** MariaDB / MySQL.

## ⚙️ Instalación y Despliegue Local
```bash
git clone https://github.com/danielonxp-sys/QUANTLOG.git
cd quantlog/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python setup_db.py
uvicorn main:app --reload --port 8000
```

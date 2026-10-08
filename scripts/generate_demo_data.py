"""Run from project root: python -m scripts.generate_demo_data"""
from services.demo_data_service import seed_demo_data

if __name__ == "__main__":
    seed_demo_data()

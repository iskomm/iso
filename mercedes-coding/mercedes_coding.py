#!/usr/bin/env python3
"""
Tek tikla baslatici. Cift tiklayarak ya da:  python mercedes_coding.py

GUI acilir (butun Mercedes modelleri + AMG menu + ariza/tanitma).
Ekran yoksa komut satiri icin:  python -m src.cli --help
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import main

if __name__ == "__main__":
    main()

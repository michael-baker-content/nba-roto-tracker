"""
conftest.py (root)
──────────────────
Ensures the project root is on sys.path so pytest can import
modules like nba, db, config, and web from any test file.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

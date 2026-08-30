"""
Aegis pytest configuration.
Adds the project root to sys.path so test modules can import
from simulator/ and scripts/ without path manipulation hacks.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

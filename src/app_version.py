"""The single place the released version is written.

Packaging may still override it with the PLCN_VERSION environment variable, so
CI can build a version without editing the tree.
"""
import os

VERSION = os.environ.get('PLCN_VERSION') or '3.3.1'

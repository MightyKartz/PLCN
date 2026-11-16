"""The single place the released version is written.

Packaging may still override it with the RETROARCH_ASSISTANT_VERSION environment variable, so
CI can build a version without editing the tree.
"""
import os

VERSION = os.environ.get('RETROARCH_ASSISTANT_VERSION') or '3.3.1'

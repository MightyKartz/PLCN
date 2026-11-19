"""Application release label and the numeric macOS bundle version."""
import os
import re

VERSION = os.environ.get('RETROARCH_ASSISTANT_VERSION') or 'beta1'
MACOS_BUNDLE_VERSION = VERSION if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', VERSION) else '4.0.0'

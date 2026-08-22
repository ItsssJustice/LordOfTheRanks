import os
import glob
modules = glob.glob(os.path.dirname(__file__) + "/*.py")
__all__ = [ os.path.basename(f)[:-3] for f in modules if os.path.isfile(f) and not os.path.basename(f).startswith('__')] # exclude __init__.py
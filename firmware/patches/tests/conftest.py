import os, sys
# rend patchlib/verifylib/build_patch1 (dans firmware/patches/) importables depuis tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

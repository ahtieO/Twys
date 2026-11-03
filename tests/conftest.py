"""Tests run with isolated empty v2 application storage, never a user's journal."""
import os
import tempfile
os.environ['TWYS_DATA_DIR']=tempfile.mkdtemp(prefix='twys-v2-test-')

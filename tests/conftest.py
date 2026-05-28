import os
import sys
from pathlib import Path
import pytest


def _candidate_roots():
    env = os.getenv('EMS_PROJECT_ROOT')
    if env:
        yield Path(env)
    # if tests are unpacked into project root
    yield Path(__file__).resolve().parents[2]
    # if tests/ is copied elsewhere but project root is cwd
    yield Path.cwd()


def _resolve_project_root():
    for cand in _candidate_roots():
        if (cand / 'modules').exists():
            return cand
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _resolve_project_root()
MODULES_DIR = PROJECT_ROOT / 'modules'

if MODULES_DIR.exists():
    sys.path.insert(0, str(MODULES_DIR))
if PROJECT_ROOT.exists():
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope='session')
def project_root():
    return PROJECT_ROOT


@pytest.fixture(scope='session')
def modules_dir(project_root):
    return project_root / 'modules'

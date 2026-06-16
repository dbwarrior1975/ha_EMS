import ast

import pytest


PYSCRIPT_RUNTIME_PATHS = (
    'ems_policy_engine.py',
    'ems_dispatch_state_applier.py',
    'ems_actuator_writers.py',
    'modules/ems_adapter',
    'modules/ems_core',
)

PYSCRIPT_UNSUPPORTED_AST_NODES = (
    ast.GeneratorExp,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.Lambda,
)

PYSCRIPT_UNSUPPORTED_CALL_PATTERNS = (
    ('sorted', 'key'),
)

PYSCRIPT_UNSUPPORTED_BINOP_PATTERNS = (
    ast.BitOr,
)


def _runtime_python_files(project_root):
    files = []
    for relative_path in PYSCRIPT_RUNTIME_PATHS:
        path = project_root / relative_path
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for child in path.rglob('*.py'):
                files.append(child)
    return files


@pytest.mark.smoke
def test_pyscript_runtime_uses_supported_ast_subset(project_root):
    violations = []
    for path in _runtime_python_files(project_root):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, PYSCRIPT_UNSUPPORTED_AST_NODES):
                source_segment = ast.get_source_segment(source, node) or ''
                relative_path = path.relative_to(project_root)
                violations.append(
                    f'{relative_path}:{node.lineno}: {type(node).__name__}: {' '.join(source_segment.split())}'
                )

    assert not violations, 'Pyscript runtime AST violations:\n' + '\n'.join(violations)


@pytest.mark.smoke
def test_pyscript_runtime_avoids_callback_sort_keys(project_root):
    violations = []
    for path in _runtime_python_files(project_root):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name):
                continue
            for function_name, keyword_name in PYSCRIPT_UNSUPPORTED_CALL_PATTERNS:
                if node.func.id != function_name:
                    continue
                for keyword in node.keywords:
                    if keyword.arg == keyword_name:
                        source_segment = ast.get_source_segment(source, node) or ''
                        relative_path = path.relative_to(project_root)
                        violations.append(
                            f'{relative_path}:{node.lineno}: {function_name}(..., {keyword_name}=...): {' '.join(source_segment.split())}'
                        )

    assert not violations, 'Pyscript runtime callback call violations:\n' + '\n'.join(violations)


@pytest.mark.smoke
def test_pyscript_runtime_avoids_pep604_union_syntax(project_root):
    violations = []
    for path in _runtime_python_files(project_root):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            if not isinstance(node.op, PYSCRIPT_UNSUPPORTED_BINOP_PATTERNS):
                continue
            source_segment = ast.get_source_segment(source, node) or ''
            relative_path = path.relative_to(project_root)
            violations.append(
                f'{relative_path}:{node.lineno}: BitOr union syntax: {' '.join(source_segment.split())}'
            )

    assert not violations, 'Pyscript runtime PEP 604 union syntax violations:\n' + '\n'.join(violations)


@pytest.mark.smoke
def test_pyscript_runtime_avoids_dataclass_default_factory(project_root):
    violations = []
    for path in _runtime_python_files(project_root):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name):
                continue
            if node.func.id != 'field':
                continue
            for keyword in node.keywords:
                if keyword.arg != 'default_factory':
                    continue
                source_segment = ast.get_source_segment(source, node) or ''
                relative_path = path.relative_to(project_root)
                violations.append(
                    f'{relative_path}:{node.lineno}: field(default_factory=...): {' '.join(source_segment.split())}'
                )

    assert not violations, 'Pyscript runtime dataclass default_factory violations:\n' + '\n'.join(violations)


@pytest.mark.smoke
def test_pyscript_runtime_avoids_runtime_property_descriptors(project_root):
    violations = []
    for path in _runtime_python_files(project_root):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Name):
                    continue
                if decorator.id != 'property':
                    continue
                relative_path = path.relative_to(project_root)
                violations.append(f'{relative_path}:{node.lineno}: @property {node.name}')

    assert not violations, 'Pyscript runtime property descriptor violations:\n' + '\n'.join(violations)


@pytest.mark.smoke
def test_pyscript_runtime_avoids_frozen_dataclasses(project_root):
    violations = []
    for path in _runtime_python_files(project_root):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Name):
                    continue
                if decorator.func.id != 'dataclass':
                    continue
                for keyword in decorator.keywords:
                    if keyword.arg != 'frozen':
                        continue
                    if not isinstance(keyword.value, ast.Constant):
                        continue
                    if keyword.value.value is not True:
                        continue
                    relative_path = path.relative_to(project_root)
                    violations.append(f'{relative_path}:{node.lineno}: @dataclass(frozen=True) {node.name}')

    assert not violations, 'Pyscript runtime frozen dataclass violations:\n' + '\n'.join(violations)


@pytest.mark.smoke
def test_pyscript_runtime_avoids_object_setattr(project_root):
    violations = []
    for path in _runtime_python_files(project_root):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr != '__setattr__':
                continue
            if not isinstance(node.value, ast.Name):
                continue
            if node.value.id != 'object':
                continue
            relative_path = path.relative_to(project_root)
            violations.append(f'{relative_path}:{node.lineno}: object.__setattr__')

    assert not violations, 'Pyscript runtime object.__setattr__ violations:\n' + '\n'.join(violations)
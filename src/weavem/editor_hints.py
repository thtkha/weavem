"""Safe, advisory callable hints for the local visual editor.

Only parses source: it never imports a task, evaluates an annotation/default, or
tries to recover a signature from a compiled artifact.
"""
from __future__ import annotations
import ast
import json
import math
from pathlib import Path
from typing import Any
from .contracts import SourceSpec

_MAX_SOURCE = 1024 * 1024
_MISSING = object()

def _json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)): return True
    if isinstance(value, float): return math.isfinite(value)
    if isinstance(value, list): return all(_json_value(item) for item in value)
    if isinstance(value, dict): return all(isinstance(key, str) and _json_value(item) for key,item in value.items())
    return False

def _annotation(node: ast.expr | None) -> str | None:
    if node is None: return None
    try: return ast.unparse(node)
    except (ValueError, TypeError): return None

def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name): return node.id
    if isinstance(node, ast.Attribute): return node.attr
    return None

def _kind(annotation: str | None) -> str:
    normal=(annotation or '').replace('typing.','').replace('builtins.','').lower()
    if normal in {'str','string'}: return 'string'
    if normal in {'int','float','number'}: return 'number'
    if normal in {'bool','boolean'}: return 'boolean'
    return 'json'

def _literal_choices(node: ast.expr | None) -> list[Any] | None:
    if not isinstance(node, ast.Subscript) or _name(node.value) != 'Literal': return None
    values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
    try: parsed=[ast.literal_eval(value) for value in values]
    except (ValueError, TypeError, MemoryError, RecursionError): return None
    return parsed if parsed and all(_json_value(value) for value in parsed) else None

def _nullable(node: ast.expr | None) -> bool:
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.BitOr): return False
    return isinstance(node.left, ast.Constant) and node.left.value is None or isinstance(node.right, ast.Constant) and node.right.value is None

def _typed_dict_fields(tree: ast.Module) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.ClassDef) or not any(_name(base) == 'TypedDict' for base in statement.bases): continue
        fields=[]
        for item in statement.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                annotation=_annotation(item.annotation)
                field={'name':item.target.id, 'kind':_kind(annotation), 'required':True, 'hasDefault':False}
                if annotation: field['annotation']=annotation
                choices=_literal_choices(item.annotation)
                if choices is not None: field['choices']=choices
                if _nullable(item.annotation): field['nullable']=True
                fields.append(field)
        result[statement.name]=fields
    return result

def _default(node: ast.expr | None) -> tuple[object | None, str | None, bool]:
    if node is None: return None,None,False
    try: value=ast.literal_eval(node)
    except (ValueError,TypeError,MemoryError,RecursionError): value=_MISSING
    if value is not _MISSING and _json_value(value): return value,None,True
    try: return None,ast.unparse(node)[:200],False
    except (ValueError,TypeError): return None,'<unsupported default>',False

def _metadata_parameters(inputs: tuple[str,...]) -> list[dict[str,Any]]:
    result=[]
    for item in inputs:
        name, sep, annotation=item.partition(':'); name,annotation=name.strip(),annotation.strip().partition('=')[0].strip()
        if not name.isidentifier(): continue
        row={'name':name,'kind':_kind(annotation if sep else None),'required':False,'hasDefault':False}
        if annotation: row['annotation']=annotation
        result.append(row)
    return result

def _rebinds_export(node: ast.stmt, export: str) -> bool:
    if isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
        targets=node.targets if isinstance(node,ast.Assign) else [node.target]
        return any(isinstance(target,ast.Name) and target.id==export for target in targets)
    if isinstance(node,(ast.Import,ast.ImportFrom)): return any((alias.asname or alias.name.split('.',1)[0])==export for alias in node.names)
    return isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.name==export

def _output_hint(annotation: ast.expr | None, typed: dict[str,list[dict[str,Any]]]) -> dict[str,Any] | None:
    text=_annotation(annotation)
    if text is None: return None
    hint={'kind':_kind(text), 'annotation':text}
    if isinstance(annotation,ast.Name) and annotation.id in typed: hint['fields']=typed[annotation.id]
    return hint

def source_parameter_hint(task_toml: Path, spec: SourceSpec, inputs: tuple[str,...]=()) -> dict[str,Any] | None:
    source=task_toml.parent/spec.source_path
    try:
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(task_toml.parent.resolve()) or source.stat().st_size>_MAX_SOURCE: return None
        tree=ast.parse(source.read_text(encoding='utf-8'),filename=str(source))
    except (OSError,UnicodeDecodeError,SyntaxError,ValueError,RecursionError): return None
    matches=[item for item in tree.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name==spec.export]
    if len(matches)!=1 or matches[0].decorator_list: return None
    function=matches[0]; position=tree.body.index(function)
    if any(_rebinds_export(item,spec.export) for item in tree.body[position+1:]): return None
    args=function.args
    if args.posonlyargs or args.vararg or args.kwarg: return None
    defaults=[None]*(len(args.args)-len(args.defaults))+list(args.defaults); metadata={item['name']:item for item in _metadata_parameters(inputs)}
    parameters=[]
    for argument,default in [*zip(args.args,defaults),*zip(args.kwonlyargs,args.kw_defaults)]:
        annotation=_annotation(argument.annotation); value,display,supported=_default(default)
        item={'name':argument.arg,'kind':_kind(annotation),'required':default is None,'hasDefault':default is not None}
        if annotation: item['annotation']=annotation
        elif argument.arg in metadata:
            item.update({key:value for key,value in metadata[argument.arg].items() if key in {'kind','annotation'}})
        choices=_literal_choices(argument.annotation)
        if choices is not None: item['choices']=choices
        if _nullable(argument.annotation): item['nullable']=True
        if supported: item['defaultValue']=value
        elif display: item['defaultDisplay']=display
        parameters.append(item)
    result={'origin':'source','parameters':parameters}
    doc=ast.get_docstring(function)
    if doc: result['description']=doc.strip()[:4096]
    output=_output_hint(function.returns,_typed_dict_fields(tree))
    if output is not None: result['output']=output
    return result

def metadata_parameter_hint(inputs: tuple[str,...]) -> dict[str,Any] | None:
    parameters=_metadata_parameters(inputs)
    return {'origin':'metadata','parameters':parameters} if parameters else None

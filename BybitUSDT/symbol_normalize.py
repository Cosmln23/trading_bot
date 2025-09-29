import json
from pathlib import Path

RENAMES_PATH = Path(__file__).resolve().parent.parent / 'config' / 'symbol_renames.json'

def _load_mapping() -> dict:
    try:
        with open(RENAMES_PATH, 'r') as f:
            return json.load(f) or {}
    except Exception:
        return {}

def normalize_symbol(sym: str) -> str:
    """Normalize a full symbol like 'PENGUUSDT' using config mapping.
    Returns uppercased normalized symbol if a mapping exists, else uppercased input.
    """
    m = _load_mapping()
    s = (sym or '').upper()
    return m.get(s, s)

def normalize_base(base: str) -> str:
    """Normalize base symbol (no suffix) using mapping inferred from full renames.
    Bidirectional: if mapping says KB->VB, returns VB when s==KB and returns KB when s==VB.
    This lets external feeds map to internal config base (or vice versa).
    """
    m = _load_mapping()
    s = (base or '').upper()
    for k, v in m.items():
        if k.endswith('USDT') and v.endswith('USDT'):
            kb, vb = k[:-4], v[:-4]
            if s == kb:
                return vb
            if s == vb:
                return kb
    return s

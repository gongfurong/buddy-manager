#!/usr/bin/env python3
"""
Buddy Manager - Claude Code companion management tool
Implements the full buddy generation algorithm in pure Python (wyhash + Mulberry32)
"""

import struct
import sys
import json


def _is_cli_mode():
    """Return True when running as a subprocess of Claude Code CLI (not a standalone terminal).

    Uses stdout.isatty(): when called by the AI via Bash tool, stdout is piped (not a tty),
    meaning we're in programmatic/signal mode. When user runs directly in a terminal,
    stdout IS a tty — save-only mode, no restart signals or kills.
    """
    return not sys.stdout.isatty()

# Force UTF-8 stdout/stderr on Windows (avoids GBK encode errors for box/block chars)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import os
import re
import shutil
import subprocess
import argparse
import random
import string

# ─────────────────────────────────────────────
# Zig std.hash.Wyhash (matches Bun.hash() exactly)
# ─────────────────────────────────────────────
_U64 = 0xFFFFFFFFFFFFFFFF
_SECRET = [
    0xa0761d6478bd642f,
    0xe7037ed1a0b428db,
    0x8ebc6af09c88c6e3,
    0x589965cc75374cc3,
]

def _read(n, data):
    if n == 8: return struct.unpack_from('<Q', data, 0)[0]
    if n == 4: return struct.unpack_from('<I', data, 0)[0]
    r = 0
    for i in range(n):
        r |= data[i] << (8 * i)
    return r

def _mum(a, b):
    x = (a & _U64) * (b & _U64)
    return x & _U64, (x >> 64) & _U64

def _mix(a, b):
    lo, hi = _mum(a, b)
    return (lo ^ hi) & _U64

def wyhash(key, seed=0):
    """Zig std.hash.Wyhash — matches Bun.hash() exactly."""
    if isinstance(key, str):
        data = key.encode('utf-8')
    else:
        data = bytes(key)
    n = len(data)

    # init(seed)
    s = (_mix((seed ^ _SECRET[0]) & _U64, _SECRET[1]) ^ seed) & _U64
    state = [s, s, s]
    a = b = 0

    if n <= 16:
        # smallKey
        if n >= 4:
            end = n - 4
            quarter = (n >> 3) << 2
            a = ((_read(4, data[0:]) << 32) | _read(4, data[quarter:])) & _U64
            b = ((_read(4, data[end:]) << 32) | _read(4, data[end - quarter:])) & _U64
        elif n > 0:
            a = ((data[0] << 16) | (data[n >> 1] << 8) | data[n - 1]) & _U64
            b = 0
        else:
            a = b = 0
    else:
        i = 0
        if n >= 48:
            while i + 48 < n:
                blk = data[i:i + 48]
                for k in range(3):
                    av = _read(8, blk[8 * (2 * k):])
                    bv = _read(8, blk[8 * (2 * k + 1):])
                    state[k] = _mix((av ^ _SECRET[k + 1]) & _U64, (bv ^ state[k]) & _U64)
                i += 48
            # final0
            state[0] = (state[0] ^ state[1] ^ state[2]) & _U64
        # final1(data, i)
        inp = data[i:]
        j = 0
        while j + 16 < len(inp):
            state[0] = _mix((_read(8, inp[j:]) ^ _SECRET[1]) & _U64,
                            (_read(8, inp[j + 8:]) ^ state[0]) & _U64)
            j += 16
        a = _read(8, data[n - 16:n - 8])
        b = _read(8, data[n - 8:n])

    # final2()
    a = (a ^ _SECRET[1]) & _U64
    b = (b ^ state[0]) & _U64
    lo, hi = _mum(a, b)
    a, b = lo, hi
    return _mix((a ^ _SECRET[0] ^ n) & _U64, (b ^ _SECRET[1]) & _U64)

def bun_hash_32(s):
    """Equivalent to Number(BigInt(Bun.hash(s)) & 0xffffffffn)"""
    return wyhash(s) & 0xFFFFFFFF

# ─────────────────────────────────────────────
# Mulberry32 PRNG
# ─────────────────────────────────────────────
import ctypes

def _imul(a, b):
    return ctypes.c_int32(ctypes.c_uint32(a).value * ctypes.c_uint32(b).value).value

def mulberry32(seed):
    state = [ctypes.c_int32(seed).value]  # signed int32, like JS
    def rng():
        state[0] = ctypes.c_int32(state[0] + 1831565813).value
        t = state[0]
        # Use unsigned right shift (>>>) to match JS behavior
        u = ctypes.c_uint32(t).value
        t = _imul(t ^ (u >> 15), 1 | t)
        u = ctypes.c_uint32(t).value
        t2 = _imul(t ^ (u >> 7), 61 | t)
        t = ctypes.c_int32(t + t2).value ^ t
        u = ctypes.c_uint32(t).value
        return ctypes.c_uint32(t ^ (u >> 14)).value / 4294967296
    return rng

# ─────────────────────────────────────────────
# Companion data
# ─────────────────────────────────────────────
SPECIES = ['duck', 'goose', 'blob', 'cat', 'dragon', 'octopus', 'owl',
           'penguin', 'turtle', 'snail', 'ghost', 'axolotl', 'capybara',
           'cactus', 'robot', 'rabbit', 'mushroom', 'chonk']

RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary']
RARITY_WEIGHTS = {'common': 60, 'uncommon': 25, 'rare': 10, 'epic': 4, 'legendary': 1}
RARITY_BASE_STAT = {'common': 5, 'uncommon': 15, 'rare': 25, 'epic': 35, 'legendary': 50}

STATS = ['DEBUGGING', 'PATIENCE', 'CHAOS', 'WISDOM', 'SNARK']
EYES = ['·', '✦', '×', '◉', '@', '°']
HATS = ['none', 'crown', 'tophat', 'propeller', 'halo', 'wizard', 'beanie', 'tinyduck']

VFK = [
    'thunder','biscuit','void','accordion','moss','velvet','rust','pickle',
    'crumb','whisper','gravy','frost','ember','soup','marble','thorn','honey',
    'static','copper','dusk','sprocket','bramble','cinder','wobble','drizzle',
    'flint','tinsel','murmur','clatter','gloom','nectar','quartz','shingle',
    'tremor','umber','waffle','zephyr','bristle','dapple','fennel','gristle',
    'huddle','kettle','lumen','mottle','nuzzle','pebble','quiver','ripple',
    'sable','thistle','vellum','wicker','yonder','bauble','cobble','doily',
    'fickle','gambit','hubris','jostle','knoll','larder','mantle','nimbus',
    'oracle','plinth','quorum','relic','spindle','trellis','urchin','vortex',
    'warble','xenon','yoke','zenith','alcove','brogue','chisel','dirge','epoch',
    'fathom','glint','hearth','inkwell','jetsam','kiln','lattice','mirth','nook',
    'obelisk','parsnip','quill','rune','sconce','tallow','umbra','verve','wisp',
    'yawn','apex','brine','crag','dregs','etch','flume','gable','husk','ingot',
    'jamb','knurl','loam','mote','nacre','ogle','prong','quip','rind','slat',
    'tuft','vane','welt','yarn','bane','clove','dross','eave','fern','grit',
    'hive','jade','keel','lilt','muse','nape','omen','pith','rook','silt',
    'tome','urge','vex','wane','yew','zest'
]

RARITY_EMOJI = {'common': '⚪', 'uncommon': '🟢', 'rare': '🔵', 'epic': '🟣', 'legendary': '🟡'}
SPECIES_EMOJI = {
    'duck': '🦆', 'goose': '🪿', 'blob': '🫧', 'cat': '🐱', 'dragon': '🐉',
    'octopus': '🐙', 'owl': '🦉', 'penguin': '🐧', 'turtle': '🐢', 'snail': '🐌',
    'ghost': '👻', 'axolotl': '🦎', 'capybara': '🦔', 'cactus': '🌵',
    'robot': '🤖', 'rabbit': '🐰', 'mushroom': '🍄', 'chonk': '🐾'
}

# ─────────────────────────────────────────────
# Core algorithm
# ─────────────────────────────────────────────
def wcy(seed, n):
    """wCY: pick n unique inspiration words from VFK using LCG"""
    state = ctypes.c_uint32(seed).value
    seen = set()
    words = []
    while len(words) < n:
        state = ctypes.c_uint32(_imul(state, 1664525) + 1013904223).value
        idx = state % len(VFK)
        if idx not in seen:
            seen.add(idx)
            words.append(VFK[idx])
    return words

def simulate(account_uuid, nv):
    """Full companion simulation: returns dict with all attributes"""
    full_seed = account_uuid + nv
    h = bun_hash_32(full_seed)
    rng = mulberry32(h)

    # Rarity
    total = sum(RARITY_WEIGHTS.values())
    r = rng() * total
    rarity = 'common'
    for name in RARITIES:
        r -= RARITY_WEIGHTS[name]
        if r < 0:
            rarity = name
            break

    # Species
    sp = SPECIES[int(rng() * len(SPECIES))]

    # Eye
    eye = EYES[int(rng() * len(EYES))]

    # Hat (only if not common)
    hat = 'none'
    if rarity != 'common':
        hat = HATS[int(rng() * len(HATS))]

    # Shiny
    shiny = rng() < 0.01

    # Stats (VV_)
    base = RARITY_BASE_STAT[rarity]
    z_idx = int(rng() * len(STATS))
    y_idx = int(rng() * len(STATS))
    while y_idx == z_idx:
        y_idx = int(rng() * len(STATS))
    stats = {}
    for i, stat in enumerate(STATS):
        if i == z_idx:
            stats[stat] = min(100, base + 50 + int(rng() * 30))
        elif i == y_idx:
            stats[stat] = max(1, base - 10 + int(rng() * 15))
        else:
            stats[stat] = base + int(rng() * 40)

    # Inspiration seed
    inspiration_seed = int(rng() * 1e9)
    words = wcy(inspiration_seed, 4)

    return {
        'species': sp,
        'rarity': rarity,
        'eye': eye,
        'hat': hat,
        'shiny': shiny,
        'stats': stats,
        'inspiration_words': words,
    }

def calibrate(account_uuid):
    """Check if wyhash implementation is correct using known data points"""
    # Verified against real Bun.hash() output
    KNOWN_HASHES = {
        '7ee5648e-2227-4516-89ca-fda097189e13': {
            'friend-2026-401': 2503417455,   # Bun.hash(...) & 0xffffffff
            'l8zaorv9xxxxxxx': 2540680215,
        }
    }
    KNOWN_SPECIES = {
        '7ee5648e-2227-4516-89ca-fda097189e13': {
            'friend-2026-401': 'ghost',
            'l8zaorv9xxxxxxx': 'capybara',
        }
    }
    if account_uuid not in KNOWN_HASHES:
        return True, "no calibration data for this account"
    # First verify the hash function itself
    for nv, expected_hash in KNOWN_HASHES[account_uuid].items():
        got_hash = bun_hash_32(account_uuid + nv)
        if got_hash != expected_hash:
            return False, f"hash mismatch: '{nv}' → expected {expected_hash}, got {got_hash}"
    # Then verify species prediction
    for nv, expected_species in KNOWN_SPECIES[account_uuid].items():
        result = simulate(account_uuid, nv)
        if result['species'] != expected_species:
            return False, f"species mismatch: '{nv}' → expected {expected_species}, got {result['species']}"
    return True, "ok"

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
def find_exe():
    """Find the claude executable (claude.exe on Windows, claude on Mac/Linux)."""
    if sys.platform == 'win32':
        try:
            result = subprocess.run(['where', 'claude'], capture_output=True, text=True)
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line.endswith('.exe') and os.path.exists(line):
                    return line
        except Exception:
            pass
        return None
    else:
        # Mac/Linux: use 'which claude' then check common install paths
        try:
            result = subprocess.run(['which', 'claude'], capture_output=True, text=True)
            path = result.stdout.strip()
            if path and os.path.exists(path):
                return path
        except Exception:
            pass
        for p in [
            os.path.expanduser('~/.local/bin/claude'),
            '/usr/local/bin/claude',
            '/usr/bin/claude',
            # Scan ~/.nvm for any installed node version
            *([os.path.join(p, 'bin', 'claude')
               for p in sorted(__import__('glob').glob(os.path.expanduser('~/.nvm/versions/node/*')), reverse=True)
               if os.path.exists(os.path.join(p, 'bin', 'claude'))]),
        ]:
            if os.path.exists(p):
                return p
        return None

def claude_json_path():
    return os.path.expanduser('~/.claude.json')

def get_account_uuid():
    path = claude_json_path()
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data.get('oauthAccount', {}).get('accountUuid') or data.get('userID')

def get_current_nv(exe_path):
    """Read current NV_ (companion seed) from exe binary.

    Supports multiple Claude Code exe versions:
    - Old: zI7="friend-2026-401" pattern (companion seed near S7 variable)
    - New: fC7="jate4vv9c0xfevm" pattern (companion seed near NI() function)
    """
    with open(exe_path, 'rb') as f:
        content = f.read()
    # New pattern: ,fC7="<seed>" (seen in updated exe with cS6/lS6 architecture)
    m = re.search(rb',(\w+C7)="([^"]{8,20})"', content)
    if m and b'return{' in content[content.rfind(b'function', 0, m.start()):m.start() + 200]:
        return m.group(2).decode('utf-8')
    # Old pattern: ;lS7="<seed>" or similar S7 variable
    m = re.search(rb'[,;](\w+S7)="([^"]{8,20})"', content)
    if m:
        return m.group(2).decode('utf-8')
    # Fallback: known original companion seeds
    for nv in [b'jate4vv9c0xfevm', b'friend-2026-401', b'5i1bhja1igm0000',
               b'2g25s2m7u0p0000', b'yxpfpve5gf00000']:
        if nv in content:
            return nv.decode('utf-8')
    return None

def get_companion_state():
    """Read companion state from .claude.json"""
    path = claude_json_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return {
        'companion': data.get('companion'),
        'companionMuted': data.get('companionMuted', False),
    }

def set_companion_state(companion=None, muted=None):
    """Update .claude.json companion fields"""
    path = claude_json_path()
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if companion is False:
        data.pop('companion', None)
    elif companion is not None:
        data['companion'] = companion
    if muted is not None:
        data['companionMuted'] = muted
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────
# Buddy Config  (skill_dir/buddy_config.json)
# ─────────────────────────────────────────────
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, 'buddy_config.json')


def get_official_id(species, rarity):
    """Deterministic ID 1-90: species_idx*5 + rarity_idx + 1."""
    return SPECIES.index(species) * 5 + RARITIES.index(rarity) + 1


def _empty_config():
    return {
        '_meta': {
            'version': '1.0',
            'account_uuid': '',
            'exe_hash': '',
            'last_updated': '',
            'current_id': None,
        },
        'official': [],   # ids 1-90, official species×rarity combos
        'custom': [],     # ids 91+, user-defined or migrated-out entries
    }


def load_config():
    """Load buddy_config.json; return empty structure if missing."""
    if not os.path.exists(CONFIG_PATH):
        return _empty_config()
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_config()


def save_config(cfg):
    """Write config to disk, stamping last_updated."""
    import datetime
    cfg.setdefault('_meta', {})
    cfg['_meta']['last_updated'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def cfg_find(cfg, species, rarity):
    """Find an entry by species+rarity (official first, then custom)."""
    for e in cfg.get('official', []) + cfg.get('custom', []):
        if e.get('species') == species and e.get('rarity') == rarity:
            return e
    return None


def cfg_get_current(cfg):
    """Return the current buddy entry, or None."""
    cid = cfg.get('_meta', {}).get('current_id')
    if cid is None:
        return None
    for e in cfg.get('official', []) + cfg.get('custom', []):
        if e.get('id') == cid:
            return e
    return None


def cfg_renumber(cfg):
    """
    Renumber all entries deterministically:
      official: id = get_official_id(species, rarity)   (1-90)
      custom:   id = max_official + 1, +2, …
    Entries in official that no longer map to known species/rarity are moved to custom.
    Updates current_id to track the renamed entry.
    """
    old_to_new = {}

    # Separate entries that still belong in official
    keep_official, migrate = [], []
    for e in cfg.get('official', []):
        sp, rar = e.get('species', ''), e.get('rarity', '')
        if sp in SPECIES and rar in RARITIES:
            keep_official.append(e)
        else:
            migrate.append(e)

    # Assign official IDs
    for e in keep_official:
        new_id = get_official_id(e['species'], e['rarity'])
        old_to_new[e.get('id')] = new_id
        e['id'] = new_id
    keep_official.sort(key=lambda x: x['id'])

    # Custom: migrated + original custom
    cfg['custom'] = migrate + cfg.get('custom', [])
    max_off = max((e['id'] for e in keep_official), default=90)
    for i, e in enumerate(cfg['custom']):
        old_to_new[e.get('id')] = max_off + 1 + i
        e['id'] = max_off + 1 + i

    cfg['official'] = keep_official

    # Fix current_id pointer
    cid = cfg.get('_meta', {}).get('current_id')
    if cid in old_to_new:
        cfg['_meta']['current_id'] = old_to_new[cid]
    return cfg


def _make_entry(official_id, species, rarity, nv_seed, bones, companion):
    """Build a config entry dict from simulation + companion data."""
    return {
        'id': official_id,
        'species': species,
        'rarity': rarity,
        'nv_seed': nv_seed,
        'name': companion.get('name', ''),
        'personality': companion.get('personality', ''),
        'eye': bones.get('eye', '·'),
        'hat': bones.get('hat', 'none'),
        'shiny': bones.get('shiny', False),
        'stats': bones.get('stats', {}),
        'inspiration_words': bones.get('inspiration_words', []),
        'source': 'official',
    }


def cli_startup_sync(cfg, status=None):
    """
    CLI startup: compare Claude's current buddy (from exe NV_) with config current.
    If they differ, update config. Returns (cfg, changed).
    status: callable(msg) for status messages, or None for silent.

    When bones-swap is active, companion.species in .claude.json overrides the NV_ result,
    so we use that as the authoritative species/rarity instead of simulating the NV_ seed.
    """
    exe = find_exe()
    nv = get_current_nv(exe) if exe else None
    uuid = get_account_uuid()
    if not nv or not uuid:
        return cfg, False

    bones = simulate(uuid, nv)

    # bones-swap: companion.species overrides the NV_ simulation result
    if exe and is_bones_swap_patched(exe):
        companion = (get_companion_state().get('companion') or {})
        cs = companion.get('species')
        cr = companion.get('rarity')
        if cs and cs in SPECIES:
            bones = dict(bones)
            bones['species'] = cs
            if cr and cr in RARITIES:
                bones['rarity'] = cr

    species, rarity = bones['species'], bones['rarity']
    official_id = get_official_id(species, rarity)
    current_id = cfg.get('_meta', {}).get('current_id')

    # Keep account_uuid fresh
    if cfg['_meta'].get('account_uuid') != uuid:
        cfg['_meta']['account_uuid'] = uuid

    if current_id == official_id:
        return cfg, False   # already in sync

    if status:
        status(f"  sync: config current={current_id} → {species}/{rarity} (id {official_id})")

    companion = (get_companion_state().get('companion') or {})
    entry = cfg_find(cfg, species, rarity)
    if entry is None:
        entry = _make_entry(official_id, species, rarity, nv, bones, companion)
        cfg['official'].append(entry)
        cfg['official'].sort(key=lambda x: x['id'])
    else:
        # Refresh live fields
        if companion.get('name'):
            entry['name'] = companion['name']
        if companion.get('personality'):
            entry['personality'] = companion['personality']
        entry['nv_seed'] = nv

    cfg['_meta']['current_id'] = official_id
    return cfg, True


def config_switch(cfg, species, rarity, nv_seed, bones, companion_data=None):
    """
    Update config to reflect a buddy switch.
    Does NOT touch the exe or .claude.json — caller is responsible for that.
    Returns updated cfg.
    """
    official_id = get_official_id(species, rarity) if species in SPECIES and rarity in RARITIES else None
    if official_id is None:
        # custom
        entry = cfg_find(cfg, species, rarity)
        if entry is None:
            max_id = max(
                (e['id'] for e in cfg.get('official', []) + cfg.get('custom', [])),
                default=90
            )
            entry = _make_entry(max_id + 1, species, rarity, nv_seed, bones, companion_data or {})
            entry['source'] = 'custom'
            cfg.setdefault('custom', []).append(entry)
        target_id = entry['id']
    else:
        entry = cfg_find(cfg, species, rarity)
        if entry is None:
            entry = _make_entry(official_id, species, rarity, nv_seed, bones, companion_data or {})
            cfg.setdefault('official', []).append(entry)
            cfg['official'].sort(key=lambda x: x['id'])
        else:
            entry['nv_seed'] = nv_seed
            if companion_data:
                if companion_data.get('name'):
                    entry['name'] = companion_data['name']
                if companion_data.get('personality'):
                    entry['personality'] = companion_data['personality']
        target_id = official_id

    cfg['_meta']['current_id'] = target_id
    return cfg


def patch_exe(exe_path, old_nv, new_nv):
    """Patch NV_ companion seed in exe, writing to .patched temp file.

    Replaces the companion seed (old_nv → new_nv) wherever it appears.
    Seeds must be the same byte length (all generated seeds are 15 chars).
    """
    old_b = old_nv.encode('utf-8')
    new_b = new_nv.encode('utf-8')
    if len(old_b) != len(new_b):
        return False, f"seed length mismatch: old={len(old_b)}, new={len(new_b)} (must be equal)"
    with open(exe_path, 'rb') as f:
        content = f.read()
    count = content.count(old_b)
    if count == 0:
        return False, f"seed '{old_nv}' not found in exe"
    new_content = content.replace(old_b, new_b)
    patched_path = exe_path + '.patched'
    with open(patched_path, 'wb') as f:
        f.write(new_content)
    return True, patched_path


# ─────────────────────────────────────────────
# Bones-swap patch  (one-time exe modification)
# ─────────────────────────────────────────────
# The companion bones are computed as:
#   _I() → return { ...H, ...$ }   H=companion, $=NV_seed_bones
# $ comes last, so NV_ species always wins.
# Swapping to { ...$, ...H } lets companion.species override the NV_ result.
# After this one-time patch, switching species only needs changing .claude.json,
# not re-patching the NV_ seed every time.
_BONES_OLD = b'return{...H,...$}'   # 17 bytes — $ wins (original)
_BONES_NEW = b'return{...$,...H}'   # 17 bytes — H wins (patched)


def is_bones_swap_patched(exe_path):
    """Return True if the companion bones spread is already swapped to {...$,...H}."""
    try:
        with open(exe_path, 'rb') as f:
            data = f.read()
    except OSError:
        return False
    # Patched: return{...$,...H} immediately before companion seed declaration
    # Supports both old (zI7) and new (fC7) exe variable naming
    import re as _re
    return bool(_re.search(
        rb'return\{\.\.\.\$,\.\.\.H\}\}(?:var\s+\w+,)?\w+[CI]7="[^"]{8,20}"',
        data
    ))


def patch_bones_swap(exe_path, version_changed=False):
    """
    Patch: swap { ...H, ...$ } → { ...$, ...H } in the _I() companion function.

    Source selection:
      version_changed=True  → use exe (fresh official); overwrite .bak with new version
      version_changed=False → use .bak; if .bak is already patched, fall back to exe

    If source is already patched:
      source is .bak → copy to .patched (exe still needs replacing)
      source is exe  → exe is already correct; return sentinel so caller skips copy

    .bak is never deleted.
    Returns (True, patched_path) or (True, 'EXE_ALREADY_OK') or (False, error_msg).
    """
    import shutil as _sh
    bak_path = exe_path + '.bak'

    # ── Determine source ─────────────────────────────────────────────────
    if version_changed:
        # New Claude version: exe is the fresh official binary
        try:
            _sh.copy2(exe_path, bak_path)   # update .bak to new version
        except OSError as e:
            return False, f"Failed to update backup {bak_path}: {e}"
        src_path = exe_path
    else:
        # Same version: prefer .bak; create it if missing
        if not os.path.exists(bak_path):
            try:
                _sh.copy2(exe_path, bak_path)
            except OSError as e:
                return False, f"Failed to create backup {bak_path}: {e}"
        src_path = bak_path

    # ── Read source ───────────────────────────────────────────────────────
    try:
        with open(src_path, 'rb') as f:
            data = f.read()
    except OSError as e:
        return False, str(e)

    # ── If .bak is already patched, fall back to exe ──────────────────────
    if _BONES_OLD not in data and src_path == bak_path:
        try:
            with open(exe_path, 'rb') as f:
                data = f.read()
            src_path = exe_path
        except OSError as e:
            return False, str(e)

    # ── Apply or detect already-patched ───────────────────────────────────
    if _BONES_OLD in data:
        new_data = data.replace(_BONES_OLD, _BONES_NEW)
    elif _BONES_NEW in data:
        if src_path == exe_path:
            # exe is already correctly patched — nothing to copy
            return True, 'EXE_ALREADY_OK'
        new_data = data   # .bak is patched — copy it to .patched to replace exe
    else:
        return False, f"pattern not found in {src_path}"

    patched_path = exe_path + '.patched'
    with open(patched_path, 'wb') as f:
        f.write(new_data)

    return True, patched_path


def set_companion_species(species, rarity, bones, name=None, personality=None):
    """
    Write species + rarity + visual data into .claude.json companion so that
    the bones-swap patch makes Claude Code display the correct species.
    Preserves existing name/personality if not provided.
    """
    state = get_companion_state()
    companion = dict(state.get('companion') or {})

    # Preserve existing identity if not given
    if name:
        companion['name'] = name
    if personality:
        companion['personality'] = personality

    # Override bones fields (these win over NV_ result after the swap patch)
    companion['species'] = species
    companion['rarity']  = rarity
    companion['eye']     = bones.get('eye', '·')
    companion['hat']     = bones.get('hat', 'none')
    companion['shiny']   = bones.get('shiny', False)
    companion['stats']   = bones.get('stats', {})

    if 'hatchedAt' not in companion:
        import time
        companion['hatchedAt'] = int(time.time() * 1000)

    set_companion_state(companion=companion)



def _find_claude_parent_pid():
    """Walk the process tree from current PID upward to find the claude process PID."""
    try:
        if sys.platform == 'win32':
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-WmiObject Win32_Process | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Csv -NoTypeInformation'],
                capture_output=True, text=True
            )
            procs = {}
            for line in result.stdout.strip().split('\n')[1:]:
                parts = line.strip().strip('"').split('","')
                if len(parts) == 3:
                    try:
                        procs[int(parts[0])] = (parts[2], int(parts[1]))
                    except ValueError:
                        pass
            cur = os.getpid()
            for _ in range(12):
                if cur not in procs:
                    break
                name, ppid = procs[cur]
                if name.lower().startswith('claude'):
                    return cur
                cur = ppid
        else:
            # Mac/Linux: use ps to walk parent chain
            result = subprocess.run(['ps', '-eo', 'pid,ppid,comm'],
                                    capture_output=True, text=True)
            procs = {}
            for line in result.stdout.strip().split('\n')[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        procs[int(parts[0])] = (parts[2], int(parts[1]))
                    except ValueError:
                        pass
            cur = os.getpid()
            for _ in range(12):
                if cur not in procs:
                    break
                name, ppid = procs[cur]
                if name.lower().startswith('claude'):
                    return cur
                cur = ppid
    except Exception:
        pass
    return None


def _kill_claude(pid=None):
    """Kill claude process: by PID if given, otherwise by process name."""
    import signal as _sig
    try:
        if sys.platform == 'win32':
            if pid:
                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(['taskkill', '/F', '/IM', 'claude.exe'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            if pid:
                os.kill(pid, _sig.SIGTERM)
            else:
                subprocess.run(['pkill', '-x', 'claude'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (ProcessLookupError, OSError):
        pass


def simple_restart():
    """Kill only this Claude instance (bones-swap is active, .claude.json already updated)."""
    import time; time.sleep(0.2)
    _kill_claude(_find_claude_parent_pid())


# ─────────────────────────────────────────────
# ASCII art sprite extraction & rendering
# ─────────────────────────────────────────────
_SPRITE_CACHE = None

def _load_sprites():
    global _SPRITE_CACHE
    if _SPRITE_CACHE is not None:
        return _SPRITE_CACHE
    exe = find_exe()
    if not exe:
        _SPRITE_CACHE = []
        return _SPRITE_CACHE
    with open(exe, 'rb') as f:
        content = f.read()
    # Sprites are stored as JS arrays of strings near the species name constants
    # Anchor: "beanie" hat data is ~8KB before the sprite arrays
    anchor = content.find(b'`-vvvv-')  # unique dragon tail
    if anchor < 0:
        _SPRITE_CACHE = []
        return _SPRITE_CACHE
    region = content[anchor - 12000: anchor + 4000].decode('utf-8', errors='replace')
    matches = list(re.finditer(r'\[\[.*?\]\]', region, re.DOTALL))
    arts = []
    for m in matches[:18]:
        arts.append(_parse_sprite(m.group()))
    _SPRITE_CACHE = arts
    return arts

def _parse_sprite(raw):
    """Parse JS string array like [["line1","line2",...],[...]] into list of frame line-lists."""
    lines = []
    i = 0
    while i < len(raw):
        if raw[i] in ('"', "'"):
            q = raw[i]; i += 1
            s = ''
            while i < len(raw) and raw[i] != q:
                c = raw[i]
                if c == '\\' and i + 1 < len(raw):
                    n = raw[i + 1]
                    if n == 'n':   s += '\n'; i += 2
                    elif n == '\\': s += '\\'; i += 2
                    elif n == "'":  s += "'";  i += 2
                    elif n == '"':  s += '"';  i += 2
                    elif n == 'u' and i + 5 < len(raw):
                        s += chr(int(raw[i+2:i+6], 16)); i += 6
                    elif n == 'x' and i + 3 < len(raw):
                        s += chr(int(raw[i+2:i+4], 16)); i += 4
                    else: s += n; i += 2
                else: s += c; i += 1
            lines.append(s); i += 1
        else:
            i += 1
    return [lines[f:f+5] for f in range(0, len(lines) - 4, 5)]

_HAT_ART = {
    'none':       '            ',
    'crown':      '   \\^^^/    ',
    'tophat':     '   [___]    ',
    'propeller':  '    -+-     ',
    'halo':       '   (   )    ',
    'wizard':     '    /^\\     ',
    'beanie':     '   (___)    ',
    'tinyduck':   '    ,>      ',
}

def render_sprite(species, eye='·', hat='none', frame=0):
    """Return list of 5 strings (one art frame), or [] on failure."""
    sprites = _load_sprites()
    try:
        idx = SPECIES.index(species)
    except ValueError:
        return []
    if idx >= len(sprites) or not sprites[idx]:
        return []
    frames = sprites[idx]
    art = frames[frame % len(frames)]
    result = []
    for i, line in enumerate(art):
        if i == 0 and hat != 'none':
            line = _HAT_ART.get(hat, line)
        result.append(line.replace('{E}', eye))
    return result

def _wrap(text, width):
    """Simple word-wrap, returns list of lines."""
    words = text.split()
    lines = []
    cur = ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w).strip()
    if cur:
        lines.append(cur)
    return lines


# ANSI helpers
_R  = '\033[0m'          # reset
_B  = '\033[1m'          # bold
_DIM = '\033[2m'         # dim
# Exact ANSI codes from Claude Code source (fy7 → Ay7 fallback)
# warning=legendary, success=uncommon, permission=rare, autoAccept=epic, inactive=common
_RARITY_CODE = {
    'common':    '90',   # ansi:blackBright  (inactive)
    'uncommon':  '32',   # ansi:green        (success)
    'rare':      '34',   # ansi:blue         (permission)
    'epic':      '35',   # ansi:magenta      (autoAccept)
    'legendary': '33',   # ansi:yellow       (warning)
}

def _col(text, *codes):
    return '\033[' + ';'.join(codes) + 'm' + text + _R

def _colorize_line(line, rar, section, color):
    """Apply ANSI colors matching Claude Code source (fy7/Ay7 palette) exactly."""
    if not color:
        return line
    rc = _RARITY_CODE.get(rar, '37')

    if not line:
        return line

    ch0 = line[0]
    # Round corners (╭╰) and top/bottom border
    if ch0 in ('╭', '╰'):
        return _col(line, rc)

    if ch0 == '│':
        inner = line[1:-1]
        border = _col('│', rc)
        end    = _col('│', rc)

        if section == 'header':
            # bold + rarity color  (source: bold:true, color:f)
            return border + _col(inner, rc, '1') + end
        elif section == 'name':
            # bold only, no color  (source: bold:true, no color prop)
            return border + _col(inner, '1') + end
        elif section == 'personality':
            # dimColor + italic  (source: dimColor:true, italic:true)
            return border + _col(inner, '2', '3') + end
        elif section == 'stat':
            # No color on bars (source: LM1 has no color prop)
            import re
            colored = inner
            colored = re.sub(r'(\d+)(\s*)$', lambda m: _col(m.group(1), '1') + m.group(2), colored)
            return border + colored + end
        elif section == 'sprite':
            # Sprite colored with rarity color (source: each line wrapped color:f)
            return border + _col(inner, rc) + end
        else:
            return border + inner + end

    return line


def render_card(companion_name, bones, personality=None, frame=0, color=False, width=None):
    """Render a full buddy card matching the Claude Code UI layout."""
    sp      = bones['species']
    rar     = bones['rarity']
    eye     = bones['eye']
    hat     = bones['hat']
    stats   = bones['stats']
    shiny   = bones.get('shiny', False)

    STARS = {'common': '★', 'uncommon': '★★', 'rare': '★★★',
             'epic': '★★★★', 'legendary': '★★★★★'}
    WIDTH = width if width else 52

    # Build plain lines first (padding must be done on plain text)
    plain_lines = []
    sections    = []   # parallel list of section tags

    def push(line, sec=''):
        plain_lines.append(line)
        sections.append(sec)

    push('╭' + '─' * WIDTH + '╮', 'border')

    stars = STARS.get(rar, '')
    left  = f" {stars} {rar.upper()}"
    right = f"{sp.upper()} "
    gap   = WIDTH - len(left) - len(right)
    push('│' + left + ' ' * max(gap, 1) + right + '│', 'header')
    push('│' + ' ' * WIDTH + '│', 'blank')

    art = render_sprite(sp, eye=eye, hat=hat, frame=frame)
    for art_line in art:
        push('│' + art_line.center(WIDTH) + '│', 'sprite')

    if shiny:
        push('│' + '  ✨ SHINY'.ljust(WIDTH) + '│', 'shiny')

    push('│' + ' ' * WIDTH + '│', 'blank')
    push('│' + f"  {companion_name}".ljust(WIDTH) + '│', 'name')
    push('│' + ' ' * WIDTH + '│', 'blank')

    if personality:
        wrapped = _wrap(f'"{personality}"', WIDTH - 4)
        for wl in wrapped:
            push('│' + f"  {wl}".ljust(WIDTH) + '│', 'personality')
        push('│' + ' ' * WIDTH + '│', 'blank')

    BAR_W = 10
    for stat, val in stats.items():
        filled = round(val / 10)   # source: Math.round(K/10), max 10
        bar = '█' * filled + '░' * (BAR_W - filled)
        row = f"  {stat:<10} {bar} {val:>3}"
        push('│' + row.ljust(WIDTH) + '│', 'stat')

    push('│' + ' ' * WIDTH + '│', 'blank')
    push('│' + ' ' * WIDTH + '│', 'blank')
    push('╰' + '─' * WIDTH + '╯', 'border')

    # Apply color post-process
    result = [_colorize_line(l, rar, s, color) for l, s in zip(plain_lines, sections)]
    return '\n'.join(result)




def _exe_hash():
    """Return sha256[:16] of the current claude.exe as a version fingerprint."""
    import hashlib
    exe_path = find_exe()
    if not exe_path:
        return ''
    try:
        with open(exe_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return ''


def get_claude_version():
    """Get Claude version string from `claude --version`. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ['claude', '--version'],
            capture_output=True, text=True, timeout=5, errors='replace'
        )
        line = (result.stdout + result.stderr).strip()
        m = re.search(r'(\d+\.\d+\.\S+)', line)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def get_patch_record():
    """Return stored patch record from buddy_config.json."""
    return load_config().get('_patch', {})


def save_patch_record(version=None, hash_val=None):
    """Save bones-swap patch record (version + hash) to buddy_config.json."""
    import time as _t
    cfg = load_config()
    cfg['_patch'] = {
        'version':    version,
        'hash':       hash_val,
        'patched_at': _t.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    save_config(cfg)


def find_seed(account_uuid, target_species, target_rarity=None, count=5, max_iter=500000):
    """Brute-force search for seeds matching target species/rarity"""
    results = []
    rng = random.Random(42)
    i = 0
    while len(results) < count and i < max_iter:
        nv = ''.join(rng.choices(string.ascii_lowercase + string.digits, k=15))
        r = simulate(account_uuid, nv)
        if r['species'] == target_species:
            if target_rarity is None or r['rarity'] == target_rarity:
                results.append({'nv': nv, **r})
        i += 1
    return results

# ─────────────────────────────────────────────
# Personality generation (real system prompt from claude.exe)
# ─────────────────────────────────────────────
_BUDDY_SYSTEM = (
    "You generate coding companions \u2014 small creatures that live in a developer\u2019s terminal "
    "and occasionally comment on their work.\n\n"
    "Given a rarity, species, stats, and a handful of inspiration words, invent:\n"
    "- A name: ONE word, max 12 characters. Memorable, slightly absurd. No titles, no \u201cthe X\u201d, "
    "no epithets. Think pet name, not NPC name. The inspiration words are loose anchors \u2014 riff on one, "
    "mash two syllables, or just use the vibe. Examples: Pith, Dusker, Crumb, Brogue, Sprocket.\n"
    "- A one-sentence personality (specific, funny, a quirk that affects how they\u2019d comment on code "
    "\u2014 should feel consistent with the stats)\n\n"
    "Higher rarity = weirder, more specific, more memorable. A legendary should be genuinely strange.\n"
    "Don\u2019t repeat yourself \u2014 every companion should feel distinct.\n\n"
    'Respond with valid JSON only: {"name": "...", "personality": "..."}'
)

def _find_claude_cli():
    """Find the claude executable path."""
    try:
        result = subprocess.run(
            ['where', 'claude'] if sys.platform == 'win32' else ['which', 'claude'],
            capture_output=True, text=True
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line and os.path.exists(line):
                return line
    except Exception:
        pass
    return 'claude'


def _find_git_bash():
    """Find git bash on Windows for CLAUDE_CODE_GIT_BASH_PATH. Returns native Windows path or None."""
    if sys.platform != 'win32':
        return None
    # 1. Already set by user
    if os.environ.get('CLAUDE_CODE_GIT_BASH_PATH'):
        return os.environ['CLAUDE_CODE_GIT_BASH_PATH']
    # 2. Derive from git executable location
    try:
        r = subprocess.run(['git', '--exec-path'], capture_output=True, text=True)
        exec_path = r.stdout.strip()  # e.g. C:/Program Files/Git/mingw64/libexec/git-core
        if exec_path:
            import pathlib
            p = pathlib.Path(exec_path)
            # Walk up to find the Git root (contains bin/bash.exe)
            for parent in p.parents:
                bash = parent / 'bin' / 'bash.exe'
                if bash.exists():
                    return str(bash)
    except Exception:
        pass
    # 3. Standard Windows install locations via env vars
    for base_var in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA', 'APPDATA'):
        base = os.environ.get(base_var, '')
        if base:
            candidate = os.path.join(base, 'Git', 'bin', 'bash.exe')
            if os.path.exists(candidate):
                return candidate
    return None


def generate_personality(bones):
    """Generate name+personality via `claude -p` CLI. Returns {name, personality} or None."""
    import json as _json, re as _re
    stats_str = ' '.join(f'{k}:{v}' for k, v in bones['stats'].items())
    words     = bones.get('inspiration_words', [])
    shiny_ln  = 'SHINY variant \u2014 extra special. ' if bones.get('shiny') else ''
    prompt    = (
        f"{_BUDDY_SYSTEM}\n\n"
        f"Generate a companion.\n"
        f"Rarity: {bones['rarity'].upper()}\n"
        f"Species: {bones['species']}\n"
        f"Stats: {stats_str}\n"
        f"Inspiration words: {', '.join(words)}\n"
        f"{shiny_ln}Make it memorable and distinct."
    )
    env = os.environ.copy()
    if sys.platform == 'win32':
        bash = _find_git_bash()
        if bash:
            env['CLAUDE_CODE_GIT_BASH_PATH'] = bash
    try:
        result = subprocess.run(
            [_find_claude_cli(), '-p', prompt],
            capture_output=True, text=True, timeout=60, env=env
        )
        text = result.stdout.strip()
        if not text:
            return None
        text = _re.sub(r'^```[a-z]*\n?', '', text)
        text = _re.sub(r'\n?```$', '', text).strip()
        data = _json.loads(text)
        return {'name': data.get('name', ''), 'personality': data.get('personality', '')}
    except Exception:
        return None

def cmd_update_pers(args, force=False):
    """Update buddy personalities and config.

    CLI mode:
      - Checks exe_hash; skips if unchanged (unless --force).
      - Finds a real NV_ seed for every species/rarity combo (uses brute-force for this account).
      - Calls Claude API (haiku) to generate name+personality for each combo.
      - Writes results to buddy_config.json (official group).
      - Custom entries in config are NEVER touched.
      - If an official entry is no longer in SPECIES×RARITIES → moved to custom.

    Standalone mode:
      - Just reloads buddy_config.json (no API calls, no exe access).
    """
    import os, re as _re

    force = force or (hasattr(args, 'force') and args.force)

    cfg = load_config()

    # ── Full update (works in both CLI and standalone terminal) ──────────
    current_hash = _exe_hash()
    cfg_hash = cfg.get('_meta', {}).get('exe_hash', '')

    if not force and cfg_hash and cfg_hash == current_hash:
        print("[ Update System ]")
        print(f"  Config is up to date (exe_hash={current_hash})")
        print("  Use --force to regenerate anyway.")
        return False

    if cfg_hash and cfg_hash != current_hash:
        print(f"[ Update System ]  Claude updated: {cfg_hash} → {current_hash}")
    elif not cfg_hash:
        print("[ Update System ]  First run — generating all 90 buddy entries")
    else:
        print("[ Update System ]  --force: regenerating all entries")

    account_uuid = get_account_uuid()
    if not account_uuid:
        print("ERROR: could not find account UUID")
        return False

    exe = find_exe()
    current_nv = get_current_nv(exe) if exe else None

    total = len(SPECIES) * len(RARITIES)
    print(f"\n  Searching seeds + generating {total} descriptions (18 × 5).")
    print(f"  Model: claude-haiku-4-5.  Est. ~2 min.\n")

    done = 0
    errors = 0

    for sp in SPECIES:
        for rar in RARITIES:
            done += 1
            official_id = get_official_id(sp, rar)

            # ── Find seed ─────────────────────────────────────────────
            # Use the current exe seed if it matches this combo, else brute-force
            seed_bones = None
            nv_seed = ''
            if current_nv:
                b = simulate(account_uuid, current_nv)
                if b['species'] == sp and b['rarity'] == rar:
                    seed_bones = b
                    nv_seed = current_nv

            if seed_bones is None:
                hits = find_seed(account_uuid, sp, rar, count=1, max_iter=200000)
                if hits:
                    nv_seed = hits[0]['nv']
                    seed_bones = hits[0]
                else:
                    # Fallback: synthesise bones without a real seed
                    insp_seed = hash(f'{sp}{rar}') & 0xFFFFFFFF
                    seed_bones = {
                        'species': sp, 'rarity': rar, 'eye': '·',
                        'hat': 'none' if rar == 'common' else 'wizard',
                        'shiny': False,
                        'stats': {stat: RARITY_BASE_STAT[rar] + 20 for stat in STATS},
                        'inspiration_words': wcy(insp_seed, 4),
                    }

            print(f"  [{done:2d}/{total}] {sp:<12} {rar:<10} ", end='', flush=True)

            # ── Generate personality ───────────────────────────────────
            gen = generate_personality(seed_bones)
            if gen and gen.get('personality'):
                name = gen['name']
                personality = gen['personality']
                print(f"{name}: {personality[:60]}...")
            else:
                name = ''
                personality = f"A {rar} {sp} of few words."
                print("(API failed — fallback)")
                errors += 1

            # ── Update config entry ────────────────────────────────────
            existing = cfg_find(cfg, sp, rar)
            if existing is None or existing.get('source') == 'official':
                entry = {
                    'id': official_id,
                    'species': sp,
                    'rarity': rar,
                    'nv_seed': nv_seed,
                    'name': name,
                    'personality': personality,
                    'eye': seed_bones.get('eye', '·'),
                    'hat': seed_bones.get('hat', 'none'),
                    'shiny': seed_bones.get('shiny', False),
                    'stats': seed_bones.get('stats', {}),
                    'inspiration_words': seed_bones.get('inspiration_words', []),
                    'source': 'official',
                }
                if existing is None:
                    cfg.setdefault('official', []).append(entry)
                else:
                    existing.update(entry)

    # ── Migrate stale official entries to custom ───────────────────────
    valid_ids = {get_official_id(sp, rar) for sp in SPECIES for rar in RARITIES}
    stale = [e for e in cfg.get('official', []) if e['id'] not in valid_ids]
    if stale:
        print(f"\n  Moving {len(stale)} stale official entries → custom group")
        for e in stale:
            e['source'] = 'custom'
            cfg.setdefault('custom', []).append(e)
        cfg['official'] = [e for e in cfg['official'] if e['id'] in valid_ids]

    # Sort official
    cfg['official'].sort(key=lambda x: x['id'])

    # Update meta
    cfg['_meta']['exe_hash'] = current_hash
    cfg['_meta']['account_uuid'] = account_uuid

    # Renumber (custom IDs may shift after migration)
    cfg_renumber(cfg)
    save_config(cfg)

    ok = total - errors
    status = '✓' if errors == 0 else '!'
    n_off = len(cfg.get('official', []))
    n_cus = len(cfg.get('custom', []))
    print(f'\n{status} Done: {ok}/{total}  |  official={n_off}  custom={n_cus}  hash={current_hash}')
    if errors:
        print(f'  {errors} API failures (fallback used). Re-run to retry.')
    return True



# ─────────────────────────────────────────────
# CLI commands
# ─────────────────────────────────────────────
def resolve_species(arg):
    """Accept species number (1-18) or name. Returns (species_name, error_str)."""
    arg = arg.strip()
    if arg.isdigit():
        n = int(arg)
        if 1 <= n <= len(SPECIES):
            return SPECIES[n - 1], None
        return None, f"Number {n} out of range. Valid: 1-{len(SPECIES)}"
    name = arg.lower()
    if name in SPECIES:
        return name, None
    return None, f"Unknown species '{arg}'. Use a number (1-{len(SPECIES)}) or name: {', '.join(SPECIES)}"


def cmd_info(args):
    account_uuid = get_account_uuid()
    if not account_uuid:
        print("ERROR: Could not find account UUID in ~/.claude.json")
        return

    exe = find_exe()
    nv = get_current_nv(exe) if exe else None
    state = get_companion_state()
    companion = state.get('companion') or {}
    muted = state.get('companionMuted', False)
    cfg = load_config()

    # Build bones:
    # - Standalone: config current entry (what user last saved)
    # - CLI + bones-swap: companion.species from .claude.json
    # - CLI without bones-swap: NV_ simulation
    cur = cfg_get_current(cfg)
    if not _is_cli_mode() and cur:
        bones = {k: cur.get(k, v) for k, v in
                 [('species', 'ghost'), ('rarity', 'common'), ('eye', '·'),
                  ('hat', 'none'), ('shiny', False), ('stats', {}), ('inspiration_words', [])]}
    elif nv and account_uuid:
        bones = simulate(account_uuid, nv)
        if exe and is_bones_swap_patched(exe) and companion.get('species') in SPECIES:
            bones = dict(bones)
            bones['species'] = companion['species']
            if companion.get('rarity') in RARITIES:
                bones['rarity'] = companion['rarity']
            for field in ('eye', 'hat', 'shiny', 'stats', 'inspiration_words'):
                if field in companion:
                    bones[field] = companion[field]
    elif cur:
        bones = {k: cur.get(k, v) for k, v in
                 [('species', 'ghost'), ('rarity', 'common'), ('eye', '·'),
                  ('hat', 'none'), ('shiny', False), ('stats', {}), ('inspiration_words', [])]}
    else:
        print("No buddy data found. Run: python buddy.py switch <species>")
        return

    # Name: companion > config > species name
    cur = cfg_get_current(cfg)
    name = companion.get('name') or (cur and cur.get('name')) or bones['species'].capitalize()

    print(render_card(name, bones))
    print()
    print(f"  Hat: {bones['hat']}   Eye: {bones['eye']}   Muted: {'YES' if muted else 'no'}")
    if nv:
        print(f"  Seed: {nv}")


def cmd_list(args):
    print()
    print("  ALL BUDDIES  (use number or name in commands)")
    print("  " + "─" * 50)
    cols = 3
    for row_start in range(0, len(SPECIES), cols):
        row_sp = SPECIES[row_start:row_start + cols]
        row_idx = list(range(row_start + 1, row_start + 1 + len(row_sp)))
        rendered = [render_sprite(sp, eye='·') for sp in row_sp]
        while len(rendered) < cols:
            rendered.append(['            '] * 5)
        for li in range(5):
            print('   '.join(r[li] if li < len(r) else '            ' for r in rendered))
        for i, sp in zip(row_idx, row_sp):
            e = SPECIES_EMOJI.get(sp, ' ')
            label = f"[{i:>2}] {e} {sp.upper()}"
            print(f"  {label:<18}", end='  ')
        print()
        print()
    print("  Rarities:")
    for r, w in RARITY_WEIGHTS.items():
        emoji = RARITY_EMOJI.get(r, '')
        print(f"    {emoji} {r:<10} {w}%")


def cmd_show(args):
    """Show ASCII art card for a specific species by number or name."""
    species, err = resolve_species(args.species)
    if err:
        print(f"ERROR: {err}")
        return

    account_uuid = get_account_uuid()
    exe = find_exe()
    nv = get_current_nv(exe) if exe else None

    idx = SPECIES.index(species) + 1
    emoji = SPECIES_EMOJI.get(species, '')
    print(f"\
  [{idx}] {emoji} {species.upper()}")
    print()

    # If this is the current active buddy, show real bones + name
    if account_uuid and nv:
        bones = simulate(account_uuid, nv)
        if bones['species'] == species:
            state = get_companion_state()
            companion = state.get('companion')
            name = companion['name'] if companion else species.capitalize()
            print(render_card(name, bones))
            print(f"  ← current buddy")
            return

    # Otherwise render a preview with default eye/no hat
    art = render_sprite(species, eye='·', hat='none', frame=0)
    if art:
        width = 38
        print('┌' + '─' * width + '┐')
        header = f"  {species.upper()} (preview)"
        print('│' + header.ljust(width) + '│')
        print('│' + ' ' * width + '│')
        for line in art:
            print('│' + line.center(width) + '│')
        print('│' + ' ' * width + '│')
        print('│' + f"  All eyes: {' '.join(EYES)}".ljust(width) + '│')
        print('│' + f"  All hats: {', '.join(h for h in HATS if h != 'none')}".ljust(width) + '│')
        print('└' + '─' * width + '┘')
    else:
        print(f"  (no sprite data available for {species})")
    print(f"\
  To switch: buddy switch {idx}")
    print(f"  Legendary: buddy switch {idx} legendary")


def cmd_search(args):
    account_uuid = get_account_uuid()
    if not account_uuid:
        print("ERROR: Could not find account UUID")
        return

    species, err = resolve_species(args.species)
    if err:
        print(f"ERROR: {err}")
        return

    rarity = args.rarity.lower() if args.rarity else None
    if rarity and rarity not in RARITIES:
        print(f"ERROR: Unknown rarity '{rarity}'. Valid: {', '.join(RARITIES)}")
        return

    ok, msg = calibrate(account_uuid)
    if not ok:
        print(f"WARNING: {msg}")

    print(f"Searching for {species}" + (f"/{rarity}" if rarity else "") + "...")
    results = find_seed(account_uuid, species, rarity, count=5)

    if not results:
        print(f"No seeds found after 500k iterations. Try without rarity filter.")
        return

    print(f"\
Found {len(results)} seed(s):")
    print(f"{'Seed':<20} {'Rarity':<12} {'Shiny'}")
    print("-" * 40)
    for r in results:
        shiny = "✨" if r.get('shiny') else ""
        print(f"  {r['nv']:<18} {r['rarity']:<12} {shiny}")


def check_sync():
    """Check if exe species matches companion in .claude.json.
    Returns (in_sync, exe_species, exe_rarity, companion_species_or_None).

    When bones-swap is active, companion.species overrides the NV_ result at runtime,
    so any companion.species is considered in-sync — no mismatch is possible.
    """
    account_uuid = get_account_uuid()
    exe = find_exe()
    if not account_uuid or not exe:
        return True, None, None, None
    nv = get_current_nv(exe)
    if not nv:
        return True, None, None, None
    bones = simulate(account_uuid, nv)
    exe_species = bones['species']
    exe_rarity  = bones['rarity']
    state = get_companion_state()
    companion = state.get('companion')
    if not companion:
        return False, exe_species, exe_rarity, None   # companion missing — needs regen
    comp_species = companion.get('species')
    # bones-swap: companion.species is authoritative — NV_ mismatch is expected and correct
    if is_bones_swap_patched(exe):
        return True, comp_species or exe_species, companion.get('rarity') or exe_rarity, comp_species
    if comp_species and comp_species != exe_species:
        return False, exe_species, exe_rarity, comp_species
    return True, exe_species, exe_rarity, comp_species


def cmd_sync(args):
    """Detect and fix exe/companion mismatch — run after a failed switch."""
    in_sync, exe_sp, exe_rar, comp_sp = check_sync()
    if in_sync and comp_sp:
        print(f"✓ In sync: exe and companion both {exe_sp}/{exe_rar}")
        return
    if not exe_sp:
        print("ERROR: could not read exe species")
        return
    emoji = RARITY_EMOJI.get(exe_rar, '')
    if comp_sp is None:
        print(f"Companion missing in .claude.json — exe is {emoji} {exe_sp}/{exe_rar}")
    else:
        print(f"Mismatch: exe={exe_sp}/{exe_rar}  companion.species={comp_sp}")
    print("Clearing companion so it regenerates from exe on next restart...")
    set_companion_state(companion=False)
    print(f"✓ Done. Restart Claude Code to hatch {exe_sp} ({exe_rar}).")


def cmd_setup(args):
    """One-time setup: update skill.md paths, add buddy-manager alias to ~/.bashrc."""
    import re as _re
    scripts_dir  = os.path.dirname(os.path.abspath(__file__))
    script_path  = os.path.abspath(__file__).replace('\\', '/')
    scripts_fwd  = scripts_dir.replace('\\', '/')

    # ── 1. Update skill.md with actual paths ──────────────────────────
    skill_md = os.path.join(scripts_dir, '..', 'skill.md')
    skill_md = os.path.normpath(skill_md)
    if os.path.exists(skill_md):
        with open(skill_md, encoding='utf-8') as f:
            md = f.read()
        # Replace any existing scripts path (any user's path) with the current one
        # Replace placeholder OR any existing absolute path
        md_new = md.replace('<SCRIPTS_DIR>', scripts_fwd)
        md_new = _re.sub(
            r'[A-Za-z/~][^\s\'"`]+/skills/buddy-manager/scripts',
            scripts_fwd,
            md_new
        )
        if md_new != md:
            with open(skill_md, 'w', encoding='utf-8') as f:
                f.write(md_new)
            print(f"✓ Updated skill.md paths → {scripts_fwd}")
        else:
            print("✓ skill.md paths already correct")

    # ── 2. Platform-specific setup ─────────────────────────────────────
    if sys.platform == 'win32':
        LINES = f'\nexport PYTHONUTF8=1\nalias buddy-manager=\'python "{script_path}"\'\n'
        rc_files = [os.path.expanduser('~/.bashrc')]
    else:
        sh_path = os.path.join(scripts_dir, 'launch_buddy.sh')
        if os.path.exists(sh_path):
            os.chmod(sh_path, 0o755)
            print(f"✓ Made executable: {sh_path}")
        LINES = f'\nalias buddy-manager=\'python3 "{script_path}"\'\n'
        # Mac defaults to zsh; Linux defaults to bash; write to whichever exists
        import platform as _plat
        if _plat.system() == 'Darwin':
            rc_files = [os.path.expanduser('~/.zshrc'), os.path.expanduser('~/.bashrc')]
        else:
            rc_files = [os.path.expanduser('~/.bashrc'), os.path.expanduser('~/.zshrc')]

    # Write to the first rc file that exists (or the first one if none exist)
    target_rc = next((f for f in rc_files if os.path.exists(f)), rc_files[0])
    if os.path.exists(target_rc):
        with open(target_rc, encoding='utf-8') as f:
            content = f.read()
        if 'buddy-manager' in content:
            print(f"✓ buddy-manager alias already in {target_rc}")
            return
    with open(target_rc, 'a', encoding='utf-8') as f:
        f.write(LINES)
    rc_name = os.path.basename(target_rc)
    print(f"✓ Added buddy-manager alias to ~/{rc_name}")
    print(f"  To apply now without restarting your terminal:")
    print(f"    In Claude Code:  ! source ~/{rc_name}")
    print(f"    In terminal:     source ~/{rc_name}")


def cmd_cfgsync(args):
    """Sync config with Claude's current buddy state (CLI only). Updates buddy_config.json."""
    if not _is_cli_mode():
        print("cfgsync: only meaningful in CLI mode (reads live exe + companion state)")
        return
    print("[ Syncing buddy_config.json with Claude... ]")
    cfg = load_config()
    cfg, changed = cli_startup_sync(cfg, status=print)
    if changed:
        save_config(cfg)
        cur = cfg_get_current(cfg)
        if cur:
            sp, rar = cur['species'], cur['rarity']
            print(f"✓ Config updated → current: {SPECIES_EMOJI.get(sp,'')} {sp}/{rar} (id {cur['id']})")
    else:
        cur = cfg_get_current(cfg)
        if cur:
            sp, rar = cur['species'], cur['rarity']
            print(f"✓ Already in sync: {SPECIES_EMOJI.get(sp,'')} {sp}/{rar} (id {cur['id']})")
        else:
            print("✓ Config is empty — run 'update' to populate all 90 buddies")


def cmd_switch(args):
    account_uuid = get_account_uuid()
    species, err = resolve_species(args.species)
    if err:
        print(f"ERROR: {err}")
        return
    rarity = args.rarity.lower() if args.rarity else None
    if rarity and rarity not in RARITIES:
        print(f"ERROR: Unknown rarity '{rarity}'")
        return

    cfg = load_config()

    # ── Standalone mode: save data only, no restart ───────────────────────
    if not _is_cli_mode():
        exe = find_exe()
        # Auto-apply pending bones-swap patch if claude is not running
        if exe and _apply_pending_patch(exe):
            print("✓ Bones-swap patch applied automatically.")
        existing = cfg_find(cfg, species, rarity or 'common')
        if existing and existing.get('nv_seed') and account_uuid:
            nv_seed = existing['nv_seed']
            bones = simulate(account_uuid, nv_seed)
        else:
            nv_seed = ''
            bones = {'species': species, 'rarity': rarity or 'common', 'eye': '·',
                     'hat': 'none', 'shiny': False, 'stats': {}, 'inspiration_words': []}
        actual_rarity = bones.get('rarity') or rarity or 'common'
        cfg = config_switch(cfg, species, actual_rarity, nv_seed, bones, existing or {})
        save_config(cfg)
        # Also update companion.species in .claude.json if bones-swap is active
        if exe and is_bones_swap_patched(exe):
            companion_data = existing or {}
            existing_companion = get_companion_state().get('companion') or {}
            inherited_name = companion_data.get('name') or existing_companion.get('name') or ''
            set_companion_species(
                species, actual_rarity, bones,
                name=inherited_name,
                personality=companion_data.get('personality') or existing_companion.get('personality'),
            )
            print(f"✓ {SPECIES_EMOJI.get(species,'')} {species}/{actual_rarity} — data saved. Restart Claude Code to apply.")
        else:
            eid = cfg.get('_meta', {}).get('current_id')
            print(f"✓ Config switched → {SPECIES_EMOJI.get(species,'')} {species}/{actual_rarity} (id {eid})")
        return

    # ── CLI mode ───────────────────────────────────────────────────────────
    exe = find_exe()
    if not exe:
        print("ERROR: claude.exe not found")
        return
    if not account_uuid:
        print("ERROR: Could not find account UUID")
        return

    ok, msg = calibrate(account_uuid)
    if not ok:
        print(f"WARNING: wyhash calibration failed: {msg}")

    swapped = is_bones_swap_patched(exe)

    # ── Path A: bones-swap already applied → just update companion + simple restart ──
    if swapped:
        # Get bones for the target species/rarity from config or brute-force
        entry = cfg_find(cfg, species, rarity or 'common')
        if entry and entry.get('stats'):
            target_bones = entry
            actual_rarity = entry['rarity']
            nv_seed = entry.get('nv_seed', '')
        else:
            print(f"[ Searching seed for {species}" + (f"/{rarity}" if rarity else "") + "... ]")
            hits = find_seed(account_uuid, species, rarity, count=1)
            if hits:
                target_bones = hits[0]
                actual_rarity = hits[0]['rarity']
                nv_seed = hits[0]['nv']
            elif rarity:
                print(f"ERROR: No seed found for {species}/{rarity}")
                return
            else:
                # Synthetic bones (no seed available yet)
                actual_rarity = 'common'
                nv_seed = ''
                insp_seed = hash(f'{species}common') & 0xFFFFFFFF
                target_bones = {
                    'species': species, 'rarity': 'common',
                    'eye': '·', 'hat': 'none', 'shiny': False,
                    'stats': {s: RARITY_BASE_STAT['common'] + 20 for s in STATS},
                    'inspiration_words': wcy(insp_seed, 4),
                }

        companion_data = entry or {}
        # Preserve existing companion name if config entry has none
        existing_companion = get_companion_state().get('companion') or {}
        inherited_name = companion_data.get('name') or existing_companion.get('name') or ''

        emoji = SPECIES_EMOJI.get(species, '')
        print(f"[ bones-swap mode ] {emoji} {species}/{actual_rarity}")
        print(f"  Updating companion.species in .claude.json ...")
        set_companion_species(
            species, actual_rarity, target_bones,
            name=inherited_name,
            personality=companion_data.get('personality') or existing_companion.get('personality'),
        )
        cfg = config_switch(cfg, species, actual_rarity, nv_seed, target_bones, companion_data)
        save_config(cfg)
        eid = cfg.get('_meta', {}).get('current_id')
        print(f"✓ Config + companion updated (id {eid}). Restarting Claude...")

        if _is_cli_mode():
            # In CLI: signal AI to do simple restart (no file swap needed)
            print(f"SIMPLE_RESTART:{exe}")
            sys.exit(0)
        else:
            simple_restart(exe)
        return

    # ── Path B: bones-swap NOT applied yet → apply it first (one-time), then restart ──
    print(f"[ First-time setup: applying bones-swap patch to exe (one-time) ]")
    print(f"  After this, future switches only need .claude.json changes.")

    current_nv = get_current_nv(exe)
    if not current_nv:
        print("ERROR: Could not read current NV_ from exe")
        return

    current_bones = simulate(account_uuid, current_nv)

    # Apply swap patch
    ok, result = patch_bones_swap(exe)
    if not ok:
        print(f"ERROR applying bones-swap: {result}")
        # Fallback: old NV_-seed approach
        print("Falling back to NV_-seed patching...")
        hits = find_seed(account_uuid, species, rarity, count=1)
        if not hits:
            print("ERROR: No seed found")
            return
        new_nv = hits[0]['nv']
        new_bones = hits[0]
        ok2, result2 = patch_exe(exe, current_nv, new_nv)
        if not ok2:
            print(f"ERROR: {result2}")
            return
        cfg = config_switch(cfg, species, hits[0]['rarity'], new_nv, new_bones)
        save_config(cfg)
        set_companion_state(companion=False)
        _do_switch(result2, exe)
        return

    # Swap patch written — ALSO set companion species so it's ready on restart
    # Get bones for target
    entry = cfg_find(cfg, species, rarity or 'common')
    if entry and entry.get('stats'):
        target_bones = entry
        actual_rarity = entry['rarity']
        nv_seed = entry.get('nv_seed', current_nv)
    else:
        hits = find_seed(account_uuid, species, rarity, count=1)
        if hits:
            target_bones = hits[0]
            actual_rarity = hits[0]['rarity']
            nv_seed = hits[0]['nv']
        else:
            target_bones = current_bones
            actual_rarity = current_bones['rarity']
            nv_seed = current_nv

    companion_data = entry or {}
    set_companion_species(
        species, actual_rarity, target_bones,
        name=companion_data.get('name'),
        personality=companion_data.get('personality'),
    )
    cfg = config_switch(cfg, species, actual_rarity, nv_seed, target_bones, companion_data)
    save_config(cfg)
    eid = cfg.get('_meta', {}).get('current_id')
    print(f"✓ Swap patch created + config updated (id {eid}). Applying and restarting...")
    _do_switch(result, exe)


def cmd_name(args):
    state = get_companion_state()
    companion = state.get('companion')
    if not companion:
        print("ERROR: No active companion. Run /buddy first.")
        return
    old_name = companion.get('name', '')
    companion['name'] = args.name
    set_companion_state(companion=companion)
    print(f"✓ Renamed {old_name} → {args.name}")
    print("Restart Claude Code to see the change.")


def cmd_mute(args):
    set_companion_state(muted=True)
    print("✓ Buddy muted")


def cmd_unmute(args):
    set_companion_state(muted=False)
    print("✓ Buddy unmuted")


def _is_claude_running():
    """Return True if any claude process is currently running."""
    try:
        if sys.platform == 'win32':
            r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq claude.exe'],
                               capture_output=True, text=True, errors='replace')
            return 'claude.exe' in r.stdout
        else:
            r = subprocess.run(['pgrep', '-x', 'claude'], capture_output=True)
            return r.returncode == 0
    except Exception:
        return False



def _apply_pending_patch(exe_path):
    """If a .patched file exists and claude is not running, apply it now. Returns True if applied."""
    import shutil
    patched = exe_path + '.patched'
    if not os.path.exists(patched):
        return False
    if _is_claude_running():
        return False
    try:
        shutil.move(patched, exe_path)
        return True
    except OSError:
        return False


def _do_switch(patched_path, exe_path):
    """Apply bones-swap patch:

    - Claude NOT running → apply immediately (best case, no extra steps).
    - Claude IS running  → save .patched file, kill claude, signal done.
      Next time the standalone TUI or switch command runs (when claude is closed),
      it picks up the pending .patched and applies it automatically.
    """
    import shutil

    if not _is_claude_running():
        shutil.move(patched_path, exe_path)
        print("✓ Bones-swap patch applied.")
        if not _is_cli_mode():
            print("  Open Claude Code to use the new companion.")
        return

    # Claude is running — save patch for later, then kill
    if _is_cli_mode():
        print(f"PATCH_READY:{exe_path}")
        sys.exit(0)
    else:
        _kill_claude(_find_claude_parent_pid())
        print("Claude closed. Patch will be applied automatically next time you open the buddy TUI.")


def cmd_restore(args):
    exe = find_exe()
    if not exe:
        print("ERROR: claude.exe not found")
        return
    current_nv = get_current_nv(exe)
    if not current_nv:
        print("ERROR: Could not read current NV_ from exe")
        return
    original_nv = 'friend-2026-401'
    if current_nv == original_nv:
        print(f"Already at original NV_: {original_nv}")
        return
    ok, result = patch_exe(exe, current_nv, original_nv)
    if not ok:
        print(f"ERROR: {result}")
        return
    set_companion_state(companion=False)
    print(f"✓ Restore patch saved.")
    _do_switch(result, exe)


def cmd_calibrate(args):
    account_uuid = get_account_uuid()
    if not account_uuid:
        print("ERROR: Could not find account UUID")
        return
    ok, msg = calibrate(account_uuid)
    if ok:
        print(f"✓ wyhash calibration: {msg}")
    else:
        print(f"✗ wyhash calibration failed: {msg}")


def cmd_preview(args):
    """Render a full buddy card for any species/rarity — used by conversation mode in Claude.

    Outputs: ASCII card + personality description + seed info.
    If this IS the current buddy, shows name/personality from buddy_config.json.
    """
    species, err = resolve_species(args.species)
    if err:
        print(f"ERROR: {err}")
        return

    rarity = args.rarity.lower() if getattr(args, 'rarity', None) else None
    if rarity and rarity not in RARITIES:
        print(f"ERROR: Unknown rarity '{rarity}'. Valid: {', '.join(RARITIES)}")
        return

    account_uuid = get_account_uuid()
    if not account_uuid:
        print("ERROR: Could not find account UUID")
        return

    # If this is the current active buddy, use real data
    exe = find_exe()
    nv  = get_current_nv(exe) if exe else None
    if nv:
        current_bones = simulate(account_uuid, nv)
        rar_match = (rarity is None or current_bones['rarity'] == rarity)
        if current_bones['species'] == species and rar_match:
            state     = get_companion_state()
            cfg_p    = load_config()
            cur_e    = cfg_get_current(cfg_p)
            name     = (cur_e.get('name') if cur_e else None) or species.capitalize()
            pers     = cur_e.get('personality') if cur_e else None
            print(render_card(name, current_bones, personality=pers))
            emoji = RARITY_EMOJI.get(current_bones['rarity'], '')
            print(f"\n  {emoji} {current_bones['rarity'].upper()}  ✨ SHINY" if current_bones.get('shiny') else f"\n  {emoji} {current_bones['rarity'].upper()}")
            print(f"  seed: {nv}  ← current buddy")
            return

    # Find a representative seed for the requested species/rarity
    target_rar = rarity or 'common'
    print(f"Searching for {species}/{target_rar}...", flush=True)
    results = find_seed(account_uuid, species, target_rar, count=1)
    if not results:
        print(f"No seed found for {species}/{target_rar} (tried 500k iterations).")
        return

    r     = results[0]
    bones = simulate(account_uuid, r['nv'])
    name  = species.capitalize()
    _cfg_show = load_config()
    pers  = (cfg_find(_cfg_show, species, bones['rarity']) or {}).get('personality')
    print(render_card(name, bones, personality=pers))
    emoji = RARITY_EMOJI.get(bones['rarity'], '')
    shiny = '  ✨ SHINY' if bones.get('shiny') else ''
    print(f"\n  {emoji} {bones['rarity'].upper()}{shiny}")
    print(f"  seed: {r['nv']}")


# ─────────────────────────────────────────────
# Interactive TUI
# ─────────────────────────────────────────────
_saved_console_mode = None
_console_in_handle  = None   # CONIN$ handle opened when stdin is piped

# Windows console INPUT_RECORD structures for ReadConsoleInputW
if sys.platform == 'win32':
    import ctypes
    from ctypes import Structure, Union, c_short, c_ushort, c_ulong, c_wchar, c_int

    class _COORD(Structure):
        _fields_ = [('X', c_short), ('Y', c_short)]

    class _WINDOW_BUFFER_SIZE_RECORD(Structure):
        _fields_ = [('dwSize', _COORD)]

    class _KEY_EVENT_RECORD(Structure):
        _fields_ = [('bKeyDown', c_int), ('wRepeatCount', c_ushort),  # Windows BOOL = 4 bytes (c_int), not c_bool (1 byte)
                    ('wVirtualKeyCode', c_ushort), ('wVirtualScanCode', c_ushort),
                    ('uChar', c_wchar), ('dwControlKeyState', c_ulong)]

    class _MOUSE_EVENT_RECORD(Structure):
        _fields_ = [('dwMousePosition', _COORD), ('dwButtonState', c_ulong),
                    ('dwControlKeyState', c_ulong), ('dwEventFlags', c_ulong)]

    class _EVENT_UNION(Union):
        _fields_ = [('KeyEvent', _KEY_EVENT_RECORD),
                    ('MouseEvent', _MOUSE_EVENT_RECORD),
                    ('WindowBufferSizeEvent', _WINDOW_BUFFER_SIZE_RECORD)]

    class _INPUT_RECORD(Structure):
        _fields_ = [('EventType', c_ushort), ('_pad', c_ushort), ('Event', _EVENT_UNION)]

    _KEY_EVENT_TYPE   = 0x0001
    _MOUSE_EVENT_TYPE = 0x0002
    _VK_MAP = {
        0x26: 'UP', 0x28: 'DOWN', 0x25: 'LEFT', 0x27: 'RIGHT',
        0x1B: 'ESC', 0x09: '\t',  0x0D: '\r',
    }


def _win_has_console():
    """True if a real Windows console is accessible (even when stdin/stdout are piped)."""
    if sys.platform != 'win32':
        return False
    import ctypes
    k32 = ctypes.windll.kernel32
    INVALID = ctypes.c_void_p(-1).value
    h = k32.CreateFileW('CONIN$', 0x80000000, 0x3, None, 3, 0, None)
    if not h or h == INVALID:
        return False
    k32.CloseHandle(h)
    return True


def _get_conin_handle():
    """Return a Windows handle for console input.
    Opens CONIN$ when stdin is piped; caches the handle for reuse."""
    global _console_in_handle
    if sys.platform != 'win32':
        return None
    import ctypes
    k32 = ctypes.windll.kernel32
    if sys.stdin.isatty():
        return k32.GetStdHandle(-10)   # STD_INPUT_HANDLE
    if _console_in_handle:
        return _console_in_handle
    INVALID = ctypes.c_void_p(-1).value
    h = k32.CreateFileW('CONIN$', 0xC0000000, 0x3, None, 3, 0, None)
    if h and h != INVALID:
        _console_in_handle = h
    return _console_in_handle


def _close_conin_handle():
    """Close the cached CONIN$ handle (call on exit)."""
    global _console_in_handle
    if _console_in_handle and sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.CloseHandle(_console_in_handle)
        _console_in_handle = None


def _enter_mouse_mode():
    """Disable Quick Edit, enable mouse input on Windows console."""
    global _saved_console_mode
    if sys.platform != 'win32':
        return
    import ctypes
    k32  = ctypes.windll.kernel32
    h    = _get_conin_handle()
    if not h:
        return
    mode = ctypes.c_ulong()
    k32.GetConsoleMode(h, ctypes.byref(mode))
    _saved_console_mode = mode.value
    ENABLE_MOUSE_INPUT = 0x0010
    # Keep Quick Edit enabled so mouse drag still selects text; single clicks still generate events
    k32.SetConsoleMode(h, _saved_console_mode | ENABLE_MOUSE_INPUT)


def _exit_mouse_mode():
    """Restore original console mode."""
    global _saved_console_mode
    if sys.platform != 'win32' or _saved_console_mode is None:
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    h   = _get_conin_handle()
    if h:
        k32.SetConsoleMode(h, _saved_console_mode)
    _saved_console_mode = None
    _close_conin_handle()





_BUDDY_TITLE = 'Buddy Manager'

def _focus_or_start():
    """If a Buddy Manager window is already open, focus it and return True (caller should exit)."""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, _BUDDY_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)   # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False

def _set_console_title(title):
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass
    else:
        try:
            sys.stdout.write(f']0;{title}')
            sys.stdout.flush()
        except Exception:
            pass

def cmd_interactive(_args=None):
    """Split-panel TUI: left=species list, right=buddy card, bottom=rarity+action buttons."""
    import threading, time as _time

    # Singleton: if another instance is already open, focus it and exit
    if _focus_or_start():
        return

    # Mark this window as the active Buddy Manager
    _set_console_title(_BUDDY_TITLE)

    # Use real console when available — works even when stdin/stdout are piped (e.g. Claude Code Bash tool)
    if sys.platform == 'win32':
        is_tty = sys.stdin.isatty() or _win_has_console()
    else:
        is_tty = sys.stdin.isatty()

    # When stdout is piped but we have a real terminal, write directly to CONOUT$
    if is_tty and not sys.stdout.isatty() and sys.platform == 'win32':
        import io
        _con = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
        out  = _con
    else:
        _con = None
        out  = sys.stdout

    color  = is_tty

    # ── Auto-apply pending bones-swap patch if claude is not running ───
    account_uuid = get_account_uuid()
    exe          = find_exe()
    if exe and _apply_pending_patch(exe):
        nv = get_current_nv(exe)   # re-read after patch
        print("✓ Bones-swap patch applied. Species switching now works via config only.")
    else:
        nv = get_current_nv(exe) if exe else None

    # ── Load current buddy ─────────────────────────────────────────────
    state        = get_companion_state()
    companion    = state.get('companion')
    cfg          = load_config()

    # Build real_bones:
    # - Standalone mode: config current entry is authoritative (what user last saved)
    # - CLI mode with bones-swap: companion.species from .claude.json
    # - CLI mode without bones-swap: NV_ simulation result
    cur_entry = cfg_get_current(cfg)

    def _bones_from_entry(e):
        return {
            'species': e['species'], 'rarity': e['rarity'],
            'eye': e.get('eye', '·'), 'hat': e.get('hat', 'none'),
            'shiny': e.get('shiny', False), 'stats': e.get('stats', {}),
            'inspiration_words': e.get('inspiration_words', []),
        }

    if not _is_cli_mode() and cur_entry:
        # Standalone: show what was last saved in config
        real_bones = _bones_from_entry(cur_entry)
    elif account_uuid and nv:
        real_bones = simulate(account_uuid, nv)
        # bones-swap: companion.species overrides simulation result
        if exe and is_bones_swap_patched(exe) and companion:
            cs = companion.get('species')
            cr = companion.get('rarity')
            if cs and cs in SPECIES:
                real_bones = dict(real_bones)
                real_bones['species'] = cs
                if cr and cr in RARITIES:
                    real_bones['rarity'] = cr
                for field in ('eye', 'hat', 'shiny', 'stats', 'inspiration_words'):
                    if field in companion:
                        real_bones[field] = companion[field]
    elif cur_entry:
        real_bones = _bones_from_entry(cur_entry)
    else:
        print("No buddy data found. Run: python buddy.py switch <species>")
        return

    # Name and personality: config entry > companion > species name
    # Config is the user's source of truth; companion may have stale live state.
    cur_entry = cfg_get_current(cfg)
    if cur_entry:
        real_name = cur_entry.get('name') or real_bones['species'].capitalize()
        real_pers = cur_entry.get('personality')
    elif companion and companion.get('name'):
        real_name = companion['name']
        real_pers = companion.get('personality')
    else:
        real_name = real_bones['species'].capitalize()
        real_pers = None

    real_sp_idx  = SPECIES.index(real_bones['species'])
    real_rar_idx = RARITIES.index(real_bones['rarity'])

    # ── Mutable UI state (dict so closures can mutate freely) ──────────
    S = {
        'sp':     real_sp_idx,
        'rar':    real_rar_idx,
        'frame':  0,
        'focus':  'species',     # 'species' | 'rarity' | 'action'
        'act':    0,             # selected action button index
        'status': '',
        'muted':  state.get('companionMuted', False),
        # cached preview
        'seed':          nv,
        'bones':         real_bones,
        'name':          real_name,
        'pers':          real_pers,  # displayed personality (real or generated)
        'gen_pers':      None,   # API-generated personality for non-real buddies
        'update_status': '',     # right-side progress display (API update thread)
    }

    ACTIONS = ['save', 'reset', 'reload', 'api_update', 'patch', 'mute', 'quit']

    def _act_labels():
        mute_lbl = '[M] Buddy ON' if S['muted'] else '[M] Buddy OFF'
        upd_lbl  = '[A] Updating...' if S.get('updating') else '[A] Data Update'
        return ['[S] Save', '[R] Reset', '[U] Reload', upd_lbl, '[P] Patch', mute_lbl, '[Q] Quit']

    ALT_ON    = '\033[?1049h'
    ALT_OFF   = '\033[?1049l'
    HOME_CL   = '\033[H\033[J'
    MOUSE_ON  = '\033[?1000h\033[?1006h'   # SGR extended mouse tracking
    MOUSE_OFF = '\033[?1000l\033[?1006l'

    LEFT_W  = 22   # plain-text width of left panel
    DIVIDER = ('  \033[90m│\033[0m  ' if color else '  │  ')
    DIV_W   = 5    # plain-text width of '  │  '

    sprites_data = _load_sprites()

    def _n_frames():
        si = S['sp']
        if si < len(sprites_data) and sprites_data[si]:
            return len(sprites_data[si])
        return 1

    # ── Click-region registry ──────────────────────────────────────────
    # Each entry: (row, col1, col2, fn) — 1-indexed terminal coords
    _regions = []

    def _reg(row, c1, c2, fn):
        _regions.append((row, c1, c2, fn))

    def _hit(row, col):
        for r, c1, c2, fn in _regions:
            if r == row and c1 <= col <= c2:
                return fn
        return None

    # ── Rendering helpers ──────────────────────────────────────────────
    def _plain(s):
        return re.sub(r'\033\[[^m]*m', '', s)

    def _display_width(s):
        """Visual width: strip ANSI, count wide chars (emoji/CJK) as 2."""
        import unicodedata
        w = 0
        for c in _plain(s):
            w += 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1
        return w

    def _left_panel():
        """Returns (lines, vstart) — a scrolling viewport of the species list."""
        term_h = shutil.get_terminal_size((80, 30)).lines
        vp     = max(6, min(len(SPECIES), term_h - 9))
        vstart = max(0, min(S['sp'] - vp // 2, len(SPECIES) - vp))
        vend   = vstart + vp
        rc_sel = _RARITY_CODE.get(RARITIES[S['rar']], '37')
        lines  = []
        for i in range(vstart, vend):
            sp    = SPECIES[i]
            emoji = SPECIES_EMOJI.get(sp, ' ')
            label = f"[{i+1:>2}] {emoji} {sp:<10}"
            is_sel  = (i == S['sp'])
            is_real = (i == real_sp_idx)
            if color:
                if is_sel and S['focus'] == 'species':
                    line = f"\033[{rc_sel};7m {label}\033[0m"
                elif is_sel:
                    line = f"\033[{rc_sel};1m▶{label}\033[0m"
                elif is_real:
                    line = f"\033[2m\u2713{label[1:]}\033[0m"
                else:
                    line = f" {label}"
            else:
                if is_sel and S['focus'] == 'species':
                    line = f"▶{label}◄"
                elif is_sel:
                    line = f"▶{label}"
                elif is_real:
                    line = f"\u2713{label[1:]}"
                else:
                    line = f" {label}"
            lines.append(line)
        return lines, vstart

    def _card_width():
        """Compute card inner width to fill available terminal space."""
        term_w = shutil.get_terminal_size((80, 30)).columns
        return max(40, min(90, term_w - LEFT_W - DIV_W - 2))

    def _right_panel(fr=0):
        """Returns card lines for current selection."""
        bones = S['bones']
        name  = S['name']
        pers  = S['pers']
        return render_card(name, bones, personality=pers, frame=fr, color=color, width=_card_width()).split('\n')

    def _rarity_row(row_num):
        """Build rarity button line; register click regions. Returns line string."""
        col   = 3   # 1-indexed starting column (after 2-space prefix)
        parts = []
        for i, r in enumerate(RARITIES):
            rc      = _RARITY_CODE.get(r, '37')
            is_real_rar = (i == real_rar_idx)
            check   = '\u2713' if is_real_rar else ' '
            lbl     = f'[{check}{r.upper()}]'
            w       = len(lbl)
            is_sel  = (i == S['rar'])
            if color:
                if is_sel and S['focus'] == 'rarity':
                    s = f'\033[{rc};7;1m{lbl}\033[0m'
                elif is_sel:
                    s = f'\033[{rc};1;4m{lbl}\033[0m'
                else:
                    s = f'\033[{rc}m{lbl}\033[0m'
            else:
                s = f'▶{lbl}◄' if (is_sel and S['focus'] == 'rarity') else lbl
            ri = i
            _reg(row_num, col, col + w - 1, lambda _ri=ri: ('rar', _ri))
            parts.append(s)
            col += w + 2
        return '  ' + '  '.join(parts)

    def _action_row(row_num):
        """Build action button line; register click regions. Returns line string."""
        col   = 3
        parts = []
        for i, lbl in enumerate(_act_labels()):
            btn    = f'[{lbl}]'
            w      = len(btn)
            is_sel = (i == S['act'])
            if color:
                if is_sel and S['focus'] == 'action':
                    s = f'\033[7;1m{btn}\033[0m'
                else:
                    s = f'\033[1m{btn}\033[0m'
            else:
                s = f'▶{btn}◄' if (is_sel and S['focus'] == 'action') else btn
            ai = i
            _reg(row_num, col, col + w - 1, lambda _ai=ai: ('act', _ai))
            parts.append(s)
            col += w + 3
        return '  ' + '   '.join(parts)

    def _draw(fr=0):
        _regions.clear()
        left, vstart = _left_panel()
        right        = _right_panel(fr)

        # Truncate panels so bottom buttons always fit in the visible terminal area
        term_h    = shutil.get_terminal_size((80, 30)).lines
        BOTTOM_H  = 9   # separator + blank + rarity + blank + action + blank + sep + hint + status
        max_panel = max(4, term_h - BOTTOM_H)
        left  = left[:max_panel]
        # Truncate right panel but always keep the bottom border line
        if len(right) > max_panel:
            right = right[:max_panel - 1] + right[-1:]
        else:
            right = right[:max_panel]

        h = max(len(left), len(right))
        left  = left  + [''] * (h - len(left))
        right = right + [''] * (h - len(right))

        # HOME_CL written separately so buf[0] → terminal row 1 (no stray \n offset)
        buf = []

        # ── Side-by-side panel rows ──
        for i, (l, r) in enumerate(zip(left, right)):
            sp_idx = vstart + i
            if 0 <= sp_idx < len(SPECIES):
                si = sp_idx
                _reg(i + 1, 1, LEFT_W, lambda _si=si: ('sp', _si))
            dw  = _display_width(l)
            pad = ' ' * max(LEFT_W - dw, 0)
            buf.append(l + pad + DIVIDER + r)

        # ── Bottom panel ──
        cur_row = h + 1
        bar = '─' * (LEFT_W + DIV_W + _card_width() + 2)
        buf.append(('\033[90m' + bar + '\033[0m') if color else bar)
        cur_row += 1

        buf.append('')
        cur_row += 1
        buf.append(_rarity_row(cur_row))
        cur_row += 1

        buf.append('')
        cur_row += 1
        buf.append(_action_row(cur_row))
        cur_row += 1

        buf.append('')
        buf.append(('\033[90m' + bar + '\033[0m') if color else bar)

        # Second-to-last row: hints (left-aligned)
        hint_plain = '  ↑↓ species   Tab rarity/action   ←→ navigate   Enter confirm   q quit'
        buf.append(('\033[90m' + hint_plain + '\033[0m') if color else hint_plain)

        # Last row: status (left) + update_status (right)
        upd_plain  = S.get('update_status', '')
        status_str = S.get('status', '')
        total_w    = LEFT_W + DIV_W + _card_width() + 2
        if upd_plain:
            left  = '  ' + status_str if status_str else ''
            pad   = max(0, total_w - len(left) - len(upd_plain))
            if color:
                buf.append(('\033[33m' + left + '\033[0m' if left else '') +
                            ' ' * pad + '\033[36m' + upd_plain + '\033[0m')
            else:
                buf.append(left + ' ' * pad + upd_plain)
        elif status_str:
            buf.append(('\033[33m  ' + status_str + '\033[0m') if color else ('  ' + status_str))

        with _draw_lock:
            out.write(HOME_CL + '\n'.join(buf))
            out.flush()

    # ── Seed/card cache refresh ────────────────────────────────────────
    def _refresh():
        sp  = SPECIES[S['sp']]
        rar = RARITIES[S['rar']]
        # Bump generation to cancel any running background search
        _search_gen[0] += 1
        my_gen = _search_gen[0]
        if S['sp'] == real_sp_idx and S['rar'] == real_rar_idx:
            S['seed']    = nv
            S['bones']   = real_bones
            S['name']    = real_name
            S['pers']    = real_pers
            S['gen_pers'] = None
            S['status']  = ''
            S['frame']   = 0
        else:
            # Personality: config entry first, fallback to local dict
            _preview_entry = cfg_find(load_config(), sp, rar)
            S['name']    = (_preview_entry.get('name') if _preview_entry else None) or sp.capitalize()
            S['pers']    = _preview_entry.get('personality') if _preview_entry else None
            S['seed']    = None   # will be filled by background thread
            S['status']  = f'Searching {sp}/{rar}...'
            S['frame']   = 0

            def _bg(sp=sp, rar=rar, gen=my_gen):
                results = find_seed(account_uuid, sp, rar, count=1)
                if _search_gen[0] != gen:   # newer search started — discard result
                    return
                if results:
                    r = results[0]
                    S['seed']  = r['nv']
                    S['bones'] = simulate(account_uuid, r['nv'])
                    S['status'] = ''
                else:
                    S['status'] = f'No seed found for {sp}/{rar}'
                _draw(S['frame'])

            threading.Thread(target=_bg, daemon=True).start()

    # ── Mouse+keyboard event reader ────────────────────────────────────
    def _read_ev():
        """Returns a key string, direction string, or ('mouse', btn, col, row)."""
        if sys.platform == 'win32':
            import ctypes
            k32    = ctypes.windll.kernel32
            h      = _get_conin_handle()   # CONIN$ when stdin piped, else STD_INPUT_HANDLE
            record = _INPUT_RECORD()
            n_read = ctypes.c_ulong()
            while True:
                k32.ReadConsoleInputW(h, ctypes.byref(record), 1, ctypes.byref(n_read))
                if n_read.value == 0:
                    continue
                et = record.EventType

                if et == _MOUSE_EVENT_TYPE:
                    me = record.Event.MouseEvent
                    # Only left-button press (dwEventFlags==0 means click, not move/scroll)
                    if me.dwEventFlags == 0 and (me.dwButtonState & 1):
                        col = me.dwMousePosition.X + 1   # 0-indexed → 1-indexed
                        row = me.dwMousePosition.Y + 1
                        return ('mouse', 0, col, row)

                elif et == _KEY_EVENT_TYPE:
                    ke = record.Event.KeyEvent
                    if not ke.bKeyDown:
                        continue
                    if ke.wVirtualKeyCode in _VK_MAP:
                        return _VK_MAP[ke.wVirtualKeyCode]
                    ch = ke.uChar
                    if ch and ch != '\x00':
                        return ch
        else:
            import tty, termios, select as _sel
            fd  = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
                if ch == '\x1b':
                    r, _, _ = _sel.select([sys.stdin], [], [], 0.05)
                    if not r:
                        return 'ESC'
                    c2 = sys.stdin.read(1)
                    if c2 != '[':
                        return 'ESC'
                    r, _, _ = _sel.select([sys.stdin], [], [], 0.05)
                    if not r:
                        return 'ESC'
                    c3 = sys.stdin.read(1)
                    if c3 == '<':
                        seq = ''
                        for _ in range(40):
                            r2, _, _ = _sel.select([sys.stdin], [], [], 0.1)
                            if not r2:
                                break
                            c = sys.stdin.read(1)
                            seq += c
                            if c in ('M', 'm'):
                                break
                        if seq.endswith('M'):
                            try:
                                ps = seq[:-1].split(';')
                                return ('mouse', int(ps[0]), int(ps[1]), int(ps[2]))
                            except Exception:
                                pass
                        return None
                    return {'A': 'UP', 'B': 'DOWN', 'D': 'LEFT', 'C': 'RIGHT'}.get(c3)
                return ch
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # ── Animation thread ───────────────────────────────────────────────
    stop_anim    = threading.Event()
    _draw_lock   = threading.Lock()
    _search_gen  = [0]   # incremented each time a new search starts; lets old threads self-abort

    def _animate():
        while not stop_anim.is_set():
            stop_anim.wait(0.55)
            if stop_anim.is_set():
                break
            if _n_frames() > 1 and is_tty:
                S['frame'] = (S['frame'] + 1) % _n_frames()
                _draw(S['frame'])

    def _start_anim():
        nonlocal anim_thread
        stop_anim.clear()
        anim_thread = threading.Thread(target=_animate, daemon=True)
        if is_tty:
            anim_thread.start()

    def _stop_anim():
        stop_anim.set()
        if is_tty:
            anim_thread.join(timeout=1)

    # ── Enter alt screen ───────────────────────────────────────────────
    if is_tty:
        _enter_mouse_mode()          # disable Quick Edit, enable VT mouse input
        out.write(ALT_ON + MOUSE_ON)
        out.flush()

    anim_thread = threading.Thread(target=_animate, daemon=True)

    try:
        _draw(0)
        _start_anim()

        while True:
            ev = _read_ev() if is_tty else (input().strip()[:1] or 'q')
            if ev is None:
                continue

            _stop_anim()

            need_refresh = False
            run_action   = None

            # ── Mouse ────────────────────────────────────────────────
            if isinstance(ev, tuple) and ev[0] == 'mouse':
                _, _btn, col, row = ev
                fn = _hit(row, col)
                if fn:
                    result = fn()
                    kind, val = result
                    if kind == 'sp':
                        S['sp']  = val
                        need_refresh = True
                    elif kind == 'rar':
                        S['rar'] = val
                        need_refresh = True
                    elif kind == 'act':
                        run_action = ACTIONS[val]

            # ── Keyboard ─────────────────────────────────────────────
            elif ev == 'UP':
                S['sp'] = max(0, S['sp'] - 1)
                need_refresh = True
            elif ev == 'DOWN':
                S['sp'] = min(len(SPECIES) - 1, S['sp'] + 1)
                need_refresh = True
            elif ev == 'LEFT':
                if S['focus'] == 'rarity':
                    S['rar'] = max(0, S['rar'] - 1)
                    need_refresh = True
                elif S['focus'] == 'action':
                    S['act'] = max(0, S['act'] - 1)
            elif ev == 'RIGHT':
                if S['focus'] == 'rarity':
                    S['rar'] = min(len(RARITIES) - 1, S['rar'] + 1)
                    need_refresh = True
                elif S['focus'] == 'action':
                    S['act'] = min(len(ACTIONS) - 1, S['act'] + 1)
            elif ev == '\t':
                order     = ['species', 'rarity', 'action']
                S['focus'] = order[(order.index(S['focus']) + 1) % 3]
            elif ev in ('\r', '\n'):
                if S['focus'] == 'rarity':
                    need_refresh = True
                elif S['focus'] == 'action':
                    run_action = ACTIONS[S['act']]
                else:
                    S['focus'] = 'rarity'
            elif isinstance(ev, str):
                lo = ev.lower()
                if lo == 'q' or ev == 'ESC':
                    run_action = 'quit'
                elif lo == 's':
                    run_action = 'save'
                elif lo == 'r':
                    run_action = 'reset'
                elif lo == 'u':
                    run_action = 'reload'
                elif lo == 'a':
                    run_action = 'api_update'
                elif lo == 'p':
                    run_action = 'patch'
                elif lo == 'm':
                    run_action = 'mute'
                elif lo == 'c':
                    run_action = 'copy_status'

            # ── Execute action ────────────────────────────────────────
            # Clear confirmations if user does something else
            if run_action and run_action != 'patch':
                S['_patch_confirm'] = False
            if run_action and run_action != 'api_update':
                S['_update_confirm'] = False
                S['_cancel_confirm'] = False

            if run_action == 'quit':
                break
            elif run_action == 'save':
                if S['seed'] is None:
                    S['status'] = 'Still searching for seed, please wait...'
                elif S['bones'].get('species') == real_bones.get('species') and S['bones'].get('rarity') == real_bones.get('rarity'):
                    S['status'] = 'Already current buddy — nothing to save.'
                elif (not _is_cli_mode()) or (exe and is_bones_swap_patched(exe)):
                    # Standalone mode OR bones-swap active: JSON-only save, no exe touch
                    sp  = S['bones']['species']
                    rar = S['bones']['rarity']
                    existing_companion = get_companion_state().get('companion') or {}
                    if exe and is_bones_swap_patched(exe):
                        set_companion_species(
                            sp, rar, S['bones'],
                            name=S['name'] or existing_companion.get('name') or '',
                            personality=S.get('gen_pers') or existing_companion.get('personality'),
                        )
                        msg = f'\u2713 Saved {sp}/{rar}. Takes effect immediately.'
                    else:
                        msg = f'\u2713 Saved {sp}/{rar}. Restart Claude Code to apply.'
                    _cfg = load_config()
                    _cfg = config_switch(_cfg, sp, rar, S['seed'] or '', S['bones'])
                    save_config(_cfg)
                    real_bones.update(S['bones'])
                    real_sp_idx  = SPECIES.index(real_bones['species'])
                    real_rar_idx = RARITIES.index(real_bones['rarity'])
                    real_name    = S['name']
                    real_pers    = S.get('gen_pers') or real_pers
                    S['pers']    = real_pers
                    S['status'] = msg
                elif not nv:
                    S['status'] = 'Cannot patch: exe seed not readable. Run /buddy from Claude Code first.'
                else:
                    ok, patched = patch_exe(exe, nv, S['seed'])
                    if ok:
                        set_companion_state(companion=False)
                        out.write(ALT_OFF + MOUSE_OFF)
                        out.flush()
                        _do_switch(patched, exe)
                        return
                    else:
                        S['status'] = f'Patch failed: {patched}'
            elif run_action == 'reset':
                S['sp']     = real_sp_idx
                S['rar']    = real_rar_idx
                S['seed']   = nv
                S['bones']  = real_bones
                S['name']   = real_name
                S['pers']   = real_pers
                S['frame']  = 0
                S['status'] = 'Reset to current buddy.'
            elif run_action == 'reload':
                # Reload buddy_config.json without closing TUI
                new_cfg   = load_config()
                new_cur   = cfg_get_current(new_cfg)
                if new_cur:
                    new_b = _bones_from_entry(new_cur)
                    real_bones.clear()
                    real_bones.update(new_b)
                    real_sp_idx  = SPECIES.index(real_bones['species'])
                    real_rar_idx = RARITIES.index(real_bones['rarity'])
                    real_name    = new_cur.get('name') or real_bones['species'].capitalize()
                    real_pers    = new_cur.get('personality')
                    # Sync preview to the reloaded state
                    S['sp']    = real_sp_idx
                    S['rar']   = real_rar_idx
                    S['bones'] = dict(real_bones)
                    S['name']  = real_name
                    S['pers']  = real_pers
                    S['frame'] = 0
                    S['status'] = '✓ Config reloaded.'
                else:
                    S['status'] = 'Config is empty.'

            elif run_action == 'api_update':
                if S.get('updating'):
                    if not S.get('_cancel_confirm'):
                        S['_cancel_confirm'] = True
                        S['status'] = 'Update in progress. Press [A] again to cancel.'
                    else:
                        S['_cancel_confirm'] = False
                        S['updating']        = False
                        S['update_status']   = ''
                        S['status']          = 'Update cancelled. Config unchanged.'
                else:
                    cfg_meta     = load_config().get('_meta', {})
                    data_updated = cfg_meta.get('data_updated_at', '')   # buddy data version (independent of Claude version)
                    has_data     = bool(cfg_meta.get('data_updated_at') and load_config().get('official'))

                    if has_data and not S.get('_update_confirm'):
                        S['_update_confirm'] = True
                        label = data_updated[:10] if data_updated else '未知'
                        S['status'] = f'Data exists (updated {label}). Press [A] again to force update.'
                    else:
                        S['_update_confirm'] = False

                        _uuid = get_account_uuid()
                        if not _uuid:
                            S['status'] = '✗ Cannot read account UUID'
                        else:
                            S['updating'] = True
                            S['status']   = 'Starting update...'

                        def _do_api_update(_uuid=_uuid):
                            import concurrent.futures as _cf
                            _exe   = find_exe()
                            _nv    = get_current_nv(_exe) if _exe else None
                            combos = [(sp, rar) for sp in SPECIES for rar in RARITIES]
                            total  = len(combos)

                            # ── Phase 1: find seeds (fast, sequential) ────
                            seeds = {}
                            with _draw_lock:
                                S['update_status'] = f'[0/{total}] preparing seeds...'
                            _draw(S['frame'])
                            for i, (sp, rar) in enumerate(combos, 1):
                                if not S.get('updating'):
                                    with _draw_lock: S['update_status'] = ''
                                    _draw(S['frame']); return
                                nv_seed, seed_bones = '', None
                                if _nv:
                                    b = simulate(_uuid, _nv)
                                    if b['species'] == sp and b['rarity'] == rar:
                                        seed_bones, nv_seed = b, _nv
                                if seed_bones is None:
                                    hits = find_seed(_uuid, sp, rar, count=1, max_iter=200000)
                                    if hits:
                                        nv_seed, seed_bones = hits[0]['nv'], hits[0]
                                    else:
                                        insp_seed = hash(f'{sp}{rar}') & 0xFFFFFFFF
                                        seed_bones = {
                                            'species': sp, 'rarity': rar,
                                            'eye': '·', 'hat': 'none' if rar == 'common' else 'wizard',
                                            'shiny': False,
                                            'stats': {st: RARITY_BASE_STAT[rar] + 20 for st in STATS},
                                            'inspiration_words': wcy(insp_seed, 4),
                                        }
                                seeds[(sp, rar)] = (get_official_id(sp, rar), nv_seed, seed_bones)

                            # ── Phase 2: generate personalities (parallel) ─
                            results   = {}
                            done_n    = [0]
                            failed_at = [None]

                            def _gen(combo):
                                sp, rar = combo
                                if not S.get('updating'):
                                    return sp, rar, None, 'cancelled'
                                oid, nv_seed, seed_bones = seeds[combo]
                                gen = generate_personality(seed_bones)
                                if not gen or not gen.get('personality'):
                                    return sp, rar, None, 'failed'
                                return sp, rar, {
                                    'id': oid, 'species': sp, 'rarity': rar,
                                    'nv_seed': nv_seed,
                                    'name': gen['name'], 'personality': gen['personality'],
                                    'eye':   seed_bones.get('eye', '·'),
                                    'hat':   seed_bones.get('hat', 'none'),
                                    'shiny': seed_bones.get('shiny', False),
                                    'stats': seed_bones.get('stats', {}),
                                    'inspiration_words': seed_bones.get('inspiration_words', []),
                                    'source': 'official',
                                }, 'ok'

                            with _cf.ThreadPoolExecutor(max_workers=8) as pool:
                                futures = {pool.submit(_gen, c): c for c in combos}
                                for fut in _cf.as_completed(futures):
                                    sp, rar, entry, status = fut.result()
                                    if status == 'failed':
                                        failed_at[0] = f'{sp}/{rar}'
                                        S['updating'] = False
                                        break
                                    if status == 'cancelled':
                                        break
                                    done_n[0] += 1
                                    results[(sp, rar)] = entry
                                    with _draw_lock:
                                        S['update_status'] = f'[{done_n[0]}/{total}] generating...'
                                    _draw(S['frame'])

                            if not S.get('updating') or failed_at[0]:
                                with _draw_lock:
                                    S['updating']      = False
                                    S['update_status'] = ''
                                    if failed_at[0]:
                                        S['status'] = f'✗ {failed_at[0]} failed. Config unchanged.'
                                    else:
                                        S['status'] = 'Update cancelled. Config unchanged.'
                                _draw(S['frame'])
                                return

                            # reshape results to nested dict for compat
                            results_nested = {}
                            for (sp, rar), entry in results.items():
                                results_nested.setdefault(sp, {})[rar] = entry

                            # ── All 90 succeeded — write config ──────────
                            import datetime as _dt
                            cfg = load_config()
                            valid_ids = {get_official_id(sp, rar) for sp in SPECIES for rar in RARITIES}

                            # Move stale official → custom
                            stale = [e for e in cfg.get('official', []) if e.get('id') not in valid_ids]
                            for e in stale:
                                e['source'] = 'custom'
                                cfg.setdefault('custom', []).append(e)
                            cfg['official'] = [e for e in cfg.get('official', []) if e.get('id') in valid_ids]

                            # Update/insert official entries
                            for sp in SPECIES:
                                for rar in RARITIES:
                                    new_entry = results_nested[sp][rar]
                                    existing  = cfg_find(cfg, sp, rar)
                                    if existing is not None:
                                        existing.update(new_entry)
                                    else:
                                        cfg.setdefault('official', []).append(new_entry)

                            cfg['official'].sort(key=lambda x: x['id'])
                            cfg['_meta']['account_uuid']   = _uuid
                            cfg['_meta']['data_updated_at'] = _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                            cfg_renumber(cfg)
                            save_config(cfg)

                            # Reload TUI current-buddy state
                            new_cur = cfg_get_current(cfg)
                            if new_cur:
                                new_b = _bones_from_entry(new_cur)
                                real_bones.clear()
                                real_bones.update(new_b)

                            with _draw_lock:
                                S['updating']      = False
                                S['update_status'] = ''
                                S['status']        = f'✓ Update complete ({total}/{total}). Config saved.'
                            _draw(S['frame'])

                        threading.Thread(target=_do_api_update, daemon=True).start()
            elif run_action == 'patch':
                if not exe:
                    S['status'] = '\u2717 Cannot find claude.exe'
                else:
                    patched_now = is_bones_swap_patched(exe)
                    cur_ver     = get_claude_version()
                    cur_hash    = _exe_hash()
                    rec         = get_patch_record()
                    stored_ver  = rec.get('version')
                    stored_hash = rec.get('hash')
                    # Version match: same version string, or (no version) same hash
                    ver_match = (
                        (cur_ver and stored_ver and cur_ver == stored_ver) or
                        (not cur_ver and stored_hash and cur_hash == stored_hash)
                    )
                    do_patch    = False
                    ver_changed = False
                    reason      = ''
                    if patched_now and ver_match:
                        if not S.get('_patch_confirm'):
                            label = cur_ver or (cur_hash[:8] + '...')
                            S['_patch_confirm'] = True
                            S['status'] = f'Already patched (v{label}). Press [P] again to re-patch.'
                        else:
                            S['_patch_confirm'] = False
                            do_patch    = True
                            ver_changed = False   # same version — patch from .bak
                            reason      = 're-patch (same version)'
                    else:
                        S['_patch_confirm'] = False
                        do_patch    = True
                        ver_changed = not patched_now or not ver_match
                        if not patched_now:
                            reason = 'first time' if not stored_ver else 'Claude was updated'
                        elif not ver_match:
                            reason = 'version mismatch \u2014 re-patching'
                    if do_patch:
                        _stop_anim()
                        out.write(ALT_OFF + MOUSE_OFF)
                        out.flush()
                        _exit_mouse_mode()
                        print(f'\n\u2500\u2500 Buddy Patch ({reason}) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500')
                        print('Closing all Claude instances...')
                        _kill_claude()
                        import time as _t2; _t2.sleep(0.8)
                        print('Applying bones-swap patch...')
                        ok, result = patch_bones_swap(exe, version_changed=ver_changed)
                        if not ok:
                            print(f'\u2717 Patch failed: {result}')
                        else:
                            import shutil as _sh
                            if result == 'EXE_ALREADY_OK':
                                print('\u2713 Exe already correctly patched.')
                            else:
                                patched_file = exe + '.patched'
                                if os.path.exists(patched_file):
                                    try:
                                        _sh.move(patched_file, exe)
                                        print('\u2713 claude.exe replaced.')
                                    except OSError as e:
                                        print(f'\u2717 Failed to replace exe: {e}')
                                        ok = False
                            if ok:
                                save_patch_record(version=cur_ver, hash_val=cur_hash)
                                label = cur_ver or (cur_hash[:8] + '...')
                                print(f'\u2713 Patch applied (v{label}).')
                                print()
                                print('  Claude has been closed.')
                                print('  To resume:  claude --continue')
                                print('\u2500' * 45)
                        try:
                            input('\nPress Enter to close...')
                        except (EOFError, KeyboardInterrupt):
                            pass
                        return

            elif run_action == 'copy_status':
                text = S.get('status') or S.get('update_status') or ''
                if text:
                    try:
                        if sys.platform == 'win32':
                            subprocess.run(['clip'], input=text, text=True,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        elif sys.platform == 'darwin':
                            subprocess.run(['pbcopy'], input=text, text=True,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            for cmd in (['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']):
                                if subprocess.run(['which', cmd[0]], capture_output=True).returncode == 0:
                                    subprocess.run(cmd, input=text, text=True,
                                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    break
                        S['status'] = f'\u2713 Copied: {text[:60]}'
                    except Exception:
                        S['status'] = 'Copy failed — clipboard not available'
                else:
                    S['status'] = 'Nothing to copy'

            elif run_action == 'mute':
                new_muted = not S['muted']
                set_companion_state(muted=new_muted)
                S['muted'] = new_muted
                S['status'] = '\u2713 Buddy OFF (speech bubble hidden).' if new_muted else '\u2713 Buddy ON (speech bubble visible).'

            if need_refresh:
                _refresh()

            _draw(S['frame'])
            _start_anim()

    finally:
        stop_anim.set()
        if is_tty:
            out.write(MOUSE_OFF + ALT_OFF)
            out.flush()
            _exit_mouse_mode()       # restore original console mode
        if _con:
            _con.close()


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='Buddy Manager for Claude Code')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('info', help='Show current buddy details')
    sub.add_parser('list', help='List all species with numbers')

    p_show = sub.add_parser('show', help='Show a specific species by number or name')
    p_show.add_argument('species', help='Species number (1-18) or name')

    p_search = sub.add_parser('search', help='Find seeds for a species')
    p_search.add_argument('species', help='Species number (1-18) or name')
    p_search.add_argument('rarity', nargs='?', help='Target rarity (optional)')

    p_switch = sub.add_parser('switch', help='Switch to a different species')
    p_switch.add_argument('species', help='Species number (1-18) or name')
    p_switch.add_argument('rarity', nargs='?', help='Target rarity (optional)')

    p_name = sub.add_parser('name', help="Change buddy's name")
    p_name.add_argument('name', help='New name')

    sub.add_parser('mute', help='Mute buddy')
    sub.add_parser('unmute', help='Unmute buddy')
    sub.add_parser('restore', help='Restore original NV_ (ghost)')
    sub.add_parser('calibrate', help='Test wyhash accuracy')
    sub.add_parser('sync', help='Detect and fix exe/companion mismatch')
    sub.add_parser('cfgsync', help='Sync buddy_config.json with current Claude companion state (CLI only)')
    sub.add_parser('setup', help='One-time setup: add same-window auto-restart to ~/.bashrc')
    p_update = sub.add_parser('update', help='Update all buddy data: find seeds + generate personalities + save config')
    p_update.add_argument('--force', action='store_true', help='Force regeneration even if exe unchanged')

    p_preview = sub.add_parser('preview', help='Render a buddy card for any species/rarity (conversation mode)')
    p_preview.add_argument('species', help='Species number (1-18) or name')
    p_preview.add_argument('rarity', nargs='?', help='Rarity tier (optional)')

    args = parser.parse_args()
    cmds = {
        'info': cmd_info,
        'list': cmd_list,
        'show': cmd_show,
        'search': cmd_search,
        'switch': cmd_switch,
        'name': cmd_name,
        'mute': cmd_mute,
        'unmute': cmd_unmute,
        'restore': cmd_restore,
        'calibrate': cmd_calibrate,
        'update': cmd_update_pers,
        'preview': cmd_preview,
        'sync': cmd_sync,
        'cfgsync': cmd_cfgsync,
        'setup': cmd_setup,
    }
    if args.command in cmds:
        cmds[args.command](args)
    else:
        cmd_interactive(args)   # default: interactive TUI

if __name__ == '__main__':
    main()

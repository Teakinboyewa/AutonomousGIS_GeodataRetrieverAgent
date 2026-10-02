# import toml
try:
    import tomllib as tomli  # Python 3.11+ standard library
except ImportError:
    import tomli
import configparser
import contextlib
import re

from glob import glob
import os
import sys
import logging

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')


# Get the directory of the current script
Script_dir = os.path.dirname(os.path.abspath(__file__))
Handbooks_dir = os.path.join(Script_dir, 'Handbooks')
Keys_dir = os.path.join(Script_dir, 'Keys')
# Add the directory to sys.path
if Handbooks_dir not in sys.path:
    sys.path.append(Handbooks_dir)

if Keys_dir not in sys.path:
    sys.path.append(Keys_dir)


def _user_data_dir():
    """Folder for user-created handbooks and their keys. It lives in the QGIS
    profile, OUTSIDE the plugin folder, so it survives plugin updates (which
    replace the whole plugin folder)."""
    try:
        from qgis.core import QgsApplication
        profile_dir = QgsApplication.qgisSettingsDirPath()
    except Exception:
        profile_dir = ""
    if not profile_dir:
        profile_dir = os.path.expanduser("~")
    return os.path.normpath(os.path.join(profile_dir, "AutonomousGIS_GeodataRetrieverAgent_data"))


User_data_dir = _user_data_dir()
User_handbooks_dir = os.path.join(User_data_dir, 'Handbooks')
User_keys_dir = os.path.join(User_data_dir, 'Keys')


def ensure_user_dirs():
    os.makedirs(User_handbooks_dir, exist_ok=True)
    os.makedirs(User_keys_dir, exist_ok=True)


def is_user_handbook(source_ID):
    return os.path.exists(os.path.join(User_handbooks_dir, f'{source_ID}.toml'))


def handbook_file_for(source_ID):
    """Path of the handbook for ``source_ID``: a user handbook overrides a
    built-in one with the same ID. None if neither exists."""
    for folder in (User_handbooks_dir, Handbooks_dir):
        path = os.path.join(folder, f'{source_ID}.toml')
        if os.path.exists(path):
            return path
    return None


def keys_file_for(source_ID):
    """Path of the .keys file for ``source_ID`` (may not exist yet). User
    handbooks keep their keys in the user Keys folder; built-in handbooks keep
    theirs in the plugin Keys folder, unless the user folder already has one."""
    user_path = os.path.join(User_keys_dir, f"{source_ID}.keys")
    if is_user_handbook(source_ID) or os.path.exists(user_path):
        return user_path
    return os.path.join(Keys_dir, f"{source_ID}.keys")


def list_handbook_ids():
    """IDs of every available handbook (built-in and user), sorted."""
    return sorted(os.path.basename(p)[:-5] for p in collect_handbook_files())


class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr):
        return optionstr  # Override to preserve case sensitivity


def collect_a_handbook(source_ID, source_dir=None, keys_dir=None):

    if source_dir is None:
        handbook_file = handbook_file_for(source_ID) or os.path.join(Handbooks_dir, f'{source_ID}.toml')
    else:
        handbook_file = os.path.join(source_dir, f'{source_ID}.toml')

    # Check if handbook file exists
    if not os.path.exists(handbook_file):
        print(f"Warning: Handbook file not found: {handbook_file}")
        return None

    try:
        with open(handbook_file, "rb") as f:
            handbook = tomli.load(f)
        handbook_total_str = handbook['handbook']
    except Exception as e:
        print(f"Error loading handbook for {source_ID}: {e}")
        return None

    handbook_lines = handbook_total_str.strip().split('\n')
    numbered_handbook_str = ''
    for idx, line in enumerate(handbook_lines):
        line = line.strip(' ')
        numbered_handbook_str += f"{idx + 1}. {line}\n"

    for variable in handbook.keys():
        numbered_handbook_str = numbered_handbook_str.replace(f"{{{variable}}}",
                                                              str(handbook[variable]))

    # Replace {KEY_NAME} credential placeholders (case-insensitively), after the
    # variables above so that placeholders inside an inserted {code_example}
    # are filled in too.
    keys = effective_keys(source_ID, keys_dir)
    if keys:
        numbered_handbook_str = substitute_keys(numbered_handbook_str, keys)
    else:
        print(f"No keys found for: {source_ID}")

    # print(handbook['code_example'])
    return numbered_handbook_str


def load_keys_v0(source_ID,
                 keys_dir=Keys_dir):  # using .toml format, which requires quotation marks, not friendly for users
    key_file = os.path.join(keys_dir, f"{source_ID}.keys")
    with open(key_file, "rb") as f:
        keys = tomli.load(f)
    return keys


def _read_keys_config(key_file):
    config = CaseSensitiveConfigParser(interpolation=None)  # keys may contain '%'
    if os.path.exists(key_file):
        config.read(key_file, encoding="utf-8")
    return config


def load_keys(source_ID, keys_dir=None):  # using Python config format, which not requires quotation marks
    key_file = keys_file_for(source_ID) if keys_dir is None else os.path.join(keys_dir, f"{source_ID}.keys")
    config = _read_keys_config(key_file)
    # keys = config['API_Key'].keys()
    # print("config['API_Key'].keys():", config['API_Key'].keys())
    keys_dict = {}
    if 'API_Key' not in config:
        return keys_dict
    for key in config['API_Key'].keys():
        keys_dict[key] = config.get("API_Key", key)
        # print("Key:", key)

    # print("keys_dict:", keys_dict)
    return keys_dict


# ── API keys (GIS Co-Scientist convention) ───────────────────────────────────
# A handbook names its credentials in `key_name` (comma-separated, the
# provider's own names, e.g. FIRMS_MAP_KEY). `<ID>.keys` stores one value per
# name under [API_Key] (plus an optional [Links] section with the sign-up
# page). At run time the values are exported as environment variables, read by
# the code with os.environ["NAME"], and {NAME} placeholders in the handbook
# text are replaced. Older handbooks that only use {<ID>_key} placeholders
# keep working: their key names are the declared names they reference.

NO_KEY_MARKER = "do not require"


def is_no_key_marker(value):
    """Built-in .keys files mark sources that need no key with a sentence like
    'Data source do not require API Key'."""
    v = str(value or "").lower()
    return "do not require" in v or "don not require" in v


def key_value_is_set(value):
    """True when a value is a real, usable secret (not blank, a placeholder
    like 'XXXX'/'Example_Key', or the no-key marker)."""
    v = str(value or "").strip().lower()
    if not v or "xxxx" in v or v in ("none", "your_key", "example_key"):
        return False
    return not is_no_key_marker(v)


def split_key_names(key_name):
    return [n.strip() for n in re.split(r"[,\n]", str(key_name or "")) if n.strip()]


def _load_book(source_ID):
    path = handbook_file_for(source_ID)
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return tomli.load(f)
    except Exception:
        return None


def required_key_names(source_ID):
    """The credential names a source needs.

    * A handbook with requires_key = true and key_name: those names.
    * Otherwise the names declared in its .keys file that the handbook text or
      code example references as {placeholders} (case-insensitive), excluding
      names marked 'do not require'. Sources with no .keys file need no key."""
    book = _load_book(source_ID) or {}
    if str(book.get("requires_key", "")).strip().lower() in ("true", "1", "yes"):
        names = split_key_names(book.get("key_name", ""))
        if names:
            return names
    declared = {n: v for n, v in load_keys(source_ID).items()
                if n.strip().lower() != "example_key" and not is_no_key_marker(v)}
    if not declared:
        return []
    text = f"{book.get('handbook', '')}\n{book.get('code_example', '')}"
    placeholders = {m.lower() for m in re.findall(r"\{([A-Za-z0-9_]+)\}", text)}
    return [n for n in declared if n.lower() in placeholders]


def get_key_value(source_ID, name):
    """Stored value for one credential (case-insensitive name), or ''."""
    for k, v in load_keys(source_ID).items():
        if k.lower() == str(name).lower():
            return v
    return ""


def set_key_value(source_ID, name, value):
    """Store one credential value, keeping the file's other keys and links."""
    key_file = keys_file_for(source_ID)
    config = _read_keys_config(key_file)
    if 'API_Key' not in config:
        config['API_Key'] = {}
    for k in list(config['API_Key'].keys()):
        if k.lower() == str(name).lower() and k != name:
            config.remove_option('API_Key', k)
    config['API_Key'][name] = str(value or "").replace("\n", "").strip()
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    with open(key_file, "w", encoding="utf-8") as f:
        config.write(f)


def source_info(source_ID):
    """Everything the Data Sources cards show about one source, or None if
    its handbook cannot be read."""
    path = handbook_file_for(source_ID)
    book = _load_book(source_ID)
    if not path or book is None:
        return None
    names = required_key_names(source_ID)
    missing = [n for n in names if not key_value_is_set(get_key_value(source_ID, n))]
    is_user = is_user_handbook(source_ID)
    return {
        "id": source_ID,
        "name": str(book.get("data_source_name", "") or source_ID).strip(),
        "description": " ".join(str(book.get("brief_description", "") or "").split()),
        "handbook": str(book.get("handbook", "") or book.get("hand_book", "") or "").strip(),
        "code_example": str(book.get("code_example", "") or "").strip(),
        "website": str(book.get("website", "") or "").strip(),
        "caveats": str(book.get("caveats", "") or "").strip(),
        "key_names": names,
        "missing_keys": missing,
        "key_links": load_key_links(source_ID) if names else {},
        "is_user": is_user,
        "overrides_builtin": is_user and os.path.exists(os.path.join(Handbooks_dir, f"{source_ID}.toml")),
        "path": path,
    }


def list_sources():
    """source_info() for every available data source, sorted by name."""
    infos = [source_info(i) for i in list_handbook_ids()]
    return sorted((i for i in infos if i), key=lambda i: i["name"].lower())


def delete_user_handbook(source_ID):
    """Delete a user handbook and its keys (a built-in one with the same ID,
    if any, is used again afterwards)."""
    for path in (os.path.join(User_handbooks_dir, f"{source_ID}.toml"),
                 os.path.join(User_keys_dir, f"{source_ID}.keys")):
        if os.path.exists(path):
            os.remove(path)


def remove_key(source_ID, name):
    """Forget a stored credential: clear the value of a key the handbook
    needs (so it can be entered again), or drop an extra key entirely."""
    key_file = keys_file_for(source_ID)
    config = _read_keys_config(key_file)
    if 'API_Key' not in config:
        return
    needed = {n.lower() for n in required_key_names(source_ID)}
    for k in list(config['API_Key'].keys()):
        if k.lower() == str(name).lower():
            if k.lower() in needed:
                config['API_Key'][k] = ""
            else:
                config.remove_option('API_Key', k)
    with open(key_file, "w", encoding="utf-8") as f:
        config.write(f)


def key_entries():
    """Rows for the 'Data Sources API Keys' table: [(label, source_ID, name)].
    One row per credential a source needs or has a stored value for; sources
    without credentials get one row with name None. A credential named the
    old way (<ID>_key) is labelled by the source ID alone."""
    entries = []
    for source_ID in list_handbook_ids():
        names = list(required_key_names(source_ID))
        lowered = {n.lower() for n in names}
        for k, v in load_keys(source_ID).items():
            if k.lower() not in lowered and k.lower() != "example_key" and key_value_is_set(v):
                names.append(k)
                lowered.add(k.lower())
        if not names:
            entries.append((source_ID, source_ID, None))
            continue
        for name in names:
            legacy = len(names) == 1 and name.lower() == f"{source_ID}_key".lower()
            entries.append((source_ID if legacy else f"{source_ID} : {name}", source_ID, name))
    return entries


def write_keys_file(source_ID, values, signup_url=""):
    """(Re)write a user source's .keys file: one entry per credential name in
    ``values`` ({name: value}) and a [Links] section when a sign-up page is known."""
    ensure_user_dirs()
    config = CaseSensitiveConfigParser(interpolation=None)
    config['API_Key'] = {n: str(v or "").replace("\n", "").strip() for n, v in values.items()}
    if (signup_url or "").strip():
        config['Links'] = {"website": signup_url.strip()}
    with open(os.path.join(User_keys_dir, f"{source_ID}.keys"), "w", encoding="utf-8") as f:
        config.write(f)


def load_key_links(source_ID):
    """Where to apply for a source's key: [Links] in its .keys file, else the
    handbook's key_signup_url / website. {} when unknown."""
    config = _read_keys_config(keys_file_for(source_ID))
    if config.has_section('Links'):
        return {k: config.get('Links', k) for k in config['Links'].keys()}
    book = _load_book(source_ID) or {}
    url = str(book.get("key_signup_url", "") or book.get("website", "") or "").strip()
    return {"website": url} if url else {}


def effective_keys(source_ID, keys_dir=None):
    """{name: value} of the source's credentials that hold a usable value."""
    return {k: v for k, v in load_keys(source_ID, keys_dir).items() if key_value_is_set(v)}


def substitute_keys(text, keys):
    """Replace {NAME} credential placeholders with their values, matching the
    name case-insensitively. Other {tokens} are left alone."""
    if not keys or not text:
        return text
    keys_ci = {str(k).lower(): str(v) for k, v in keys.items()}

    def _sub(m):
        return keys_ci.get(m.group(1).lower(), m.group(0))
    return re.sub(r"\{([A-Za-z0-9_]+)\}", _sub, text)


_ENV_NAME_RE = re.compile(
    r"""os\.(?:environ\s*\[\s*|environ\.get\s*\(\s*|getenv\s*\(\s*)["']([A-Za-z_][A-Za-z0-9_]*)["']""")


def credential_names_in_code(code):
    """Environment-variable names a piece of code reads via os.environ/os.getenv."""
    return list(dict.fromkeys(_ENV_NAME_RE.findall(code or "")))


def keys_env_for_code(code):
    """Values for every os.environ name the code reads that any data source
    has a stored key for (used when running code from the code editor, where
    the data source is not known)."""
    wanted = {n.lower(): n for n in credential_names_in_code(code)}
    found = {}
    if not wanted:
        return found
    for source_ID in list_handbook_ids():
        for k, v in effective_keys(source_ID).items():
            if k.lower() in wanted and wanted[k.lower()] not in found:
                found[wanted[k.lower()]] = v
    return found


def source_keys_env(source_ID, code=None):
    """Environment variables to export for a download from ``source_ID``:
    every required credential (plus any os.environ name the code reads) that
    has a stored value, keyed by the exact name the code will look up."""
    names = list(required_key_names(source_ID))
    for n in credential_names_in_code(code or ""):
        if n not in names:
            names.append(n)
    keys_ci = {k.lower(): v for k, v in effective_keys(source_ID).items()}
    return {n: keys_ci[n.lower()] for n in names if n.lower() in keys_ci}


@contextlib.contextmanager
def keys_in_env(values):
    """Export ``values`` as environment variables for the duration of a block,
    restoring the previous environment afterwards (os.environ is process-wide)."""
    previous = {n: os.environ.get(n) for n in values}
    os.environ.update(values)
    try:
        yield list(values)
    finally:
        for n, old in previous.items():
            if old is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = old


def collect_datasources():
    return

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
def collect_handbook_files(source_dir=None):
    """Handbook files to offer the agent. By default: the built-in handbooks
    plus the user's own, where a user handbook replaces a built-in one with
    the same ID (file name)."""
    if source_dir is not None:
        source_dirs = [source_dir]
    else:
        source_dirs = [Handbooks_dir, User_handbooks_dir]

    by_id = {}
    for folder in source_dirs:  # later folders override earlier ones
        for path in glob(os.path.join(folder, "*.toml")):
            if os.path.basename(path) == "template.toml":
                continue
            by_id[os.path.basename(path)[:-5]] = path
    # print(handbooks)
    return [by_id[k] for k in sorted(by_id)]


def assemble_handbook_description(handbook_files):
    descriptions = []
    data_source_dict = {}
    for book in handbook_files:
        try:
            with open(book, "rb") as f:
                handbook = tomli.load(f)
            data_source_name = handbook['data_source_name'].strip()
            brief_description = handbook['brief_description'].strip()
        except Exception as e:
            # A broken (e.g. hand-edited) handbook must not stop every request.
            print(f"Skipping handbook {os.path.basename(book)}: {e}")
            continue
        data_source_ID = os.path.basename(book)[:-5]  # data_source_ID is the name of .toml file
        description = f"{len(descriptions) + 1}. {data_source_name}. {brief_description}"
        # print(description)
        descriptions.append(description)
        data_source_dict[data_source_name] = {"ID": data_source_ID}
    data_source_dict['Unknown'] = {"ID": "Unknown"}
    descriptions_str = "\n".join(descriptions)
    return descriptions_str, data_source_dict


def collect_key_for_a_datasource(source_dir='Handbooks'):
    return "tested ok."


class Handbook():
    """
    class for the handbook. Carefully maintain it.

    by Huan Ning, 2024-08-31
    """

    def __init__(self,
                 handbook_file,
                 verbose=True,
                 ):
        self.handbook_file = handbook_file

        self.verbose = verbose

    def get_LLM_reply(self,
                      prompt,
                      verbose=True,
                      temperature=1,
                      stream=True,
                      retry_cnt=3,
                      sleep_sec=10,
                      system_role=None,
                      model=None,
                      ):

        if system_role is None:
            system_role = self.role

        if model is None:
            model = self.model

        # Query ChatGPT with the prompt
        # if verbose:
        #     print("Geting LLM reply... \n")
        count = 0
        isSucceed = False
        self.chat_history.append({'role': 'user', 'content': prompt})
        while (not isSucceed) and (count < retry_cnt):
            try:
                count += 1
                response = client.chat.completions.create(model=model,
                                                          # messages=self.chat_history,  # Too many tokens to run.
                                                          messages=[
                                                              {"role": "system", "content": system_role},
                                                              {"role": "user", "content": prompt},
                                                          ],
                                                          temperature=temperature,
                                                          stream=stream)
            except Exception as e:
                # logging.error(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n", e)
                print(f"Error in get_LLM_reply(), will sleep {sleep_sec} seconds, then retry {count}/{retry_cnt}: \n",
                      e)
                time.sleep(sleep_sec)

        response_chucks = []
        if stream:
            for chunk in response:
                response_chucks.append(chunk)
                content = chunk.choices[0].delta.content
                if content is not None:
                    if verbose:
                        print(content, end='')
        else:
            content = response.choices[0].message.content
            # print(content)
        print('\n\n')
        # print("Got LLM reply.")

        response = response_chucks  # good for saving

        content = helper.extract_content_from_LLM_reply(response)

        self.chat_history.append({'role': 'assistant', 'content': content})

        return response
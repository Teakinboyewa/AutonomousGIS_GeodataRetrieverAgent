"""
AI handbook generation for new data sources.

Ported from the GIS-co-scientist handbook generator and adapted to this
plugin: OpenAI keys (sk-...) get the full pipeline with live web search;
GIBD keys (gibd-services...) cannot use the web-search tool, so the model
works from its own knowledge plus documentation pages fetched from the URLs
the user provides.

Pipeline: find the source -> read its docs and pin down the access method ->
draft the handbook -> (optional) run its code_example in a separate Python
process and revise it until the sample download saves real data.

Handbooks follow this plugin's conventions (the file name is the source ID,
and the handbook text ends by pulling in {code_example}) and the GIS
Co-Scientist key convention: `key_name` lists the credential names (the
provider's own, e.g. FIRMS_MAP_KEY), the code reads them with
os.environ["NAME"], and the handbook text may reference them as {NAME}.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import requests

DEFAULT_MODEL = "gpt-5.2"
GIBD_SERVICE_NAME = "Spatial Data Retrieval Agent"
GIBD_BASE_URL = "https://www.gibd.online/api"

FIELDS = (
    "data_source_name", "brief_description", "handbook", "code_example",
    "website", "requires_key", "key_name", "key_signup_url", "caveats",
)

# Documentation-fetch budgets.
_DOC_TEXT_BUDGET = 14000
_DOC_TEXT_PER_URL = 8000
_FETCH_TIMEOUT = 15  # seconds per URL
_URL_RE = re.compile(r"https?://[^\s)>\]\"'{}]+", re.IGNORECASE)

_VERIFY_TIMEOUT = 300       # seconds per sample-download run
_SAME_ERROR_LIMIT = 3       # stop revising after N identical errors in a row
_MAX_VERIFY_ATTEMPTS = 6    # hard cap, so a model cycling through superficially
                            # different broken variants cannot loop forever

_TEXT_SAMPLE_EXTS = {
    ".csv", ".tsv", ".txt", ".json", ".geojson", ".xml", ".kml", ".gml",
    ".html", ".md", ".log", ".wkt", ".yaml", ".yml", ".toml",
}

# The fixed reply-format lines every handbook ends with (same as the built-in
# handbooks), preceded by the line that pulls in the code example.
HANDBOOK_TAIL = (
    "This is a program for your reference, note that you can improve it: {code_example}\n"
    "Put your reply into a Python code block. Explanation or conversation can be Python comments "
    "at the beginning of the code block (enclosed by ```python and ```).\n"
    "The download code is only in a function named 'download_data()'. The last line is to execute "
    "this function; do not use `if __name__ == '__main__':`.\n"
    "Throw an error if the program fails to download the data; no need to handle the exceptions."
)


class Cancelled(Exception):
    """Raised when the user stops a running generation."""


# ── Small helpers ────────────────────────────────────────────────────────────

def make_source_id(name):
    """A file-name-safe source ID from a human-readable name, e.g.
    'OpenAQ API (Global Air Quality)' -> 'OpenAQ_API_Global_Air_Quality'."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(name or "")).strip("_")
    if len(cleaned) > 32:  # cut at a word boundary, never mid-word
        words, kept = cleaned.split("_"), []
        for word in words:
            if kept and len("_".join(kept + [word])) > 32:
                break
            kept.append(word)
        cleaned = "_".join(kept)[:32]
    cleaned = cleaned.rstrip("_")
    if cleaned and cleaned[0].isdigit():
        cleaned = "DS_" + cleaned
    return cleaned or "New_Data_Source"


def split_key_names(key_name):
    """'A_KEY, B_KEY' -> ['A_KEY', 'B_KEY'] (comma or newline separated)."""
    return [n.strip() for n in re.split(r"[,\n]", str(key_name or "")) if n.strip()]


_ENV_NAME_RE = re.compile(
    r"""os\.(?:environ\s*\[\s*|environ\.get\s*\(\s*|getenv\s*\(\s*)["']([A-Za-z_][A-Za-z0-9_]*)["']""")


def env_names_in_code(code):
    """Environment-variable names the code reads via os.environ / os.getenv."""
    return list(dict.fromkeys(_ENV_NAME_RE.findall(code or "")))


def substitute_placeholders(text, keys):
    """Replace {NAME} credential placeholders (case-insensitive) with values."""
    if not keys or not text:
        return text
    keys_ci = {str(k).lower(): str(v) for k, v in keys.items()}
    return re.sub(r"\{([A-Za-z0-9_]+)\}", lambda m: keys_ci.get(m.group(1).lower(), m.group(0)), text)


def normalize_source(data, fallback_name="", website=""):
    """Coerce a model reply into the canonical handbook fields: stripped
    strings, ``requires_key`` forced to "true"/"false", ``key_name`` a clean
    comma-separated list (empty when no key is needed)."""
    data = data if isinstance(data, dict) else {}
    out = {k: str(data.get(k, "") or "").strip() for k in FIELDS}
    out["data_source_name"] = out["data_source_name"] or (fallback_name or "").strip()
    out["website"] = out["website"] or (website or "").strip()
    out["requires_key"] = "true" if out["requires_key"].lower() in ("true", "1", "yes") else "false"
    out["key_name"] = ",".join(dict.fromkeys(split_key_names(out["key_name"])))
    if out["requires_key"] != "true":
        out["key_name"] = ""
        out["key_signup_url"] = ""
    return out


def parse_json_object(reply, expected_keys=()):
    """Parse a model reply into a dict, tolerating code fences, prose around
    the object, and {placeholders} in that prose (which must not be mistaken
    for the start of the object). Falls back to TOML, which models sometimes
    answer with. Raises ValueError when no object can be found."""
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("empty reply from the model")
    text = reply.strip()
    candidates = [m.group(1).strip() for m in re.finditer(r"```[a-zA-Z]*\s*\n?(.*?)```", text, re.S)]
    candidates.append(re.sub(r"\s*```$", "", re.sub(r"^```[a-zA-Z]*\s*", "", text)).strip())

    decoder = json.JSONDecoder(strict=False)  # models often leave raw newlines inside code strings
    found = []
    for candidate in candidates:
        try:
            data = decoder.decode(candidate)
            if isinstance(data, dict):
                found.append(data)
                continue
        except ValueError:
            pass
        # Try every '{' as the start of the object (skips {placeholders} in prose).
        for match in list(re.finditer(r"\{", candidate))[:300]:
            try:
                data, _ = decoder.raw_decode(candidate, match.start())
            except ValueError:
                continue
            if isinstance(data, dict) and data:
                found.append(data)
                break
    if expected_keys:
        for data in found:
            if any(k in data for k in expected_keys):
                return data
    if found:
        return max(found, key=len)

    for candidate in candidates:  # TOML answer
        try:
            try:
                import tomllib as _toml
            except ImportError:
                import tomli as _toml
            data = _toml.loads(candidate)
            if isinstance(data, dict) and data:
                return data
        except Exception:
            pass
    preview = " ".join(text[:160].split())
    raise ValueError(f"the AI reply was not a valid JSON object (it started with: {preview!r})")


def extract_urls(text):
    return [u.rstrip('.,;\'"') for u in _URL_RE.findall(text)] if text else []


# ── LLM backend ──────────────────────────────────────────────────────────────

class LLMBackend:
    """One place for every model call. ``sk-`` keys go straight to OpenAI
    (Responses API, with the hosted web-search tool for research); GIBD keys
    go through the GIBD proxy (chat completions, no web search)."""

    def __init__(self, api_key, model=None, reasoning_effort=None, log=print):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise ValueError("Generating a handbook needs an OpenAI API key (sk-...) or a GIBD API key. "
                             "Enter one in the Settings tab.")
        self.is_gibd = "gibd-services" in self.api_key
        model = (model or "").strip()
        # Local (Ollama) models cannot do this job well; use the default.
        self.model = model if model.lower().startswith(("gpt", "o1", "o3", "o4")) else DEFAULT_MODEL
        self.reasoning_effort = reasoning_effort if self._is_reasoning_model() else None
        self.log = log
        self._client = None
        self._question_id = None

    @property
    def has_web_search(self):
        return not self.is_gibd

    def _is_reasoning_model(self):
        return self.model.lower().startswith(("gpt-5", "o1", "o3", "o4"))

    def _openai(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def _gibd_question_id(self):
        if self._question_id is None:
            resp = requests.post(f"{GIBD_BASE_URL}/request-question-id",
                                 json={"service_name": GIBD_SERVICE_NAME, "user_api_key": self.api_key},
                                 timeout=60)
            if resp.status_code != 201:
                raise RuntimeError(f"GIBD service error {resp.status_code}: {resp.text[:300]}")
            self._question_id = resp.json()["question_id"]
        return self._question_id

    def chat(self, messages, json_mode=False):
        """A plain completion (no tools). Returns the reply text. With
        ``json_mode`` the service is asked to return a JSON object only
        (silently retried without it if the service rejects the option)."""
        if self.is_gibd:
            payload = {
                "service_name": GIBD_SERVICE_NAME,
                "question_id": self._gibd_question_id(),
                "model": self.model,
                "messages": messages,
                "stream": False,
                "temperature": 1,
            }
            if self.reasoning_effort:
                payload["reasoning_effort"] = self.reasoning_effort
            url = f"{GIBD_BASE_URL}/openai/{self.api_key}"
            resp = None
            if json_mode:
                resp = requests.post(url, json={**payload, "response_format": {"type": "json_object"}}, timeout=600)
            if resp is None or resp.status_code != 200:
                resp = requests.post(url, json=payload, timeout=600)
            if resp.status_code != 200:
                raise RuntimeError(f"GIBD service error {resp.status_code}: {resp.text[:300]}")
            return resp.json()["choices"][0]["message"]["content"]

        kwargs = {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort else {}
        system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
        turns = [{"role": m["role"], "content": m["content"]}
                 for m in messages if m.get("role") in ("user", "assistant")]
        if system:
            kwargs["instructions"] = system
        if json_mode:
            try:
                resp = self._openai().responses.create(model=self.model, input=turns,
                                                       text={"format": {"type": "json_object"}}, **kwargs)
                return resp.output_text
            except Exception as e:  # e.g. a model without JSON mode: fall back to a plain reply
                if "json" not in str(e).lower() and "format" not in str(e).lower():
                    raise
        resp = self._openai().responses.create(model=self.model, input=turns, **kwargs)
        return resp.output_text

    def chat_json(self, messages, expected_keys=(), log=print):
        """chat() for replies that must be a JSON object: JSON mode, tolerant
        parsing, and one retry asking for the bare object if parsing fails."""
        reply = self.chat(messages, json_mode=True)
        try:
            return parse_json_object(reply, expected_keys)
        except ValueError as e:
            log(f"The AI reply could not be read ({e}); asking again for JSON only...")
        retry = messages + [
            {"role": "assistant", "content": reply or ""},
            {"role": "user", "content": "Your reply was not a valid JSON object. Reply again with ONLY the "
                                        "complete JSON object - starting with { and ending with } - and no "
                                        "other text, code fences or comments."}]
        return parse_json_object(self.chat(retry, json_mode=True), expected_keys)

    def research(self, prompt, log=print):
        """A JSON-returning research call: with live web search when the key
        allows it, otherwise from the model's own knowledge."""
        if self.has_web_search:
            kwargs = {"tools": [{"type": "web_search"}]}
            if self.reasoning_effort:
                kwargs["reasoning"] = {"effort": self.reasoning_effort}
            resp = self._openai().responses.create(model=self.model, input=prompt, **kwargs)
            try:
                return parse_json_object(resp.output_text)
            except ValueError as e:
                log(f"The AI reply could not be read ({e}); asking again for JSON only...")
            resp = self._openai().responses.create(
                model=self.model, input=prompt + "\n\nReply with ONLY the JSON object and no other text.", **kwargs)
            return parse_json_object(resp.output_text)
        note = ("\n\n(Web search is not available. Use your own well-established knowledge of this source "
                "and the documentation text included above, if any. Do not invent URLs or parameters you "
                "are not confident about; say so in the notes instead.)")
        return self.chat_json([{"role": "user", "content": prompt + note}], log=log)


# ── Documentation fetching ───────────────────────────────────────────────────

_DOC_HEADERS = {
    "User-Agent": "AGGRA-HandbookGenerator/1.0",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
# Some agencies (e.g. cdc.gov) reject the identifying UA; retry once as a browser.
_DOC_HEADERS_BROWSER = {
    **_DOC_HEADERS,
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
}

_SOCRATA_FOUNDRY_RE = re.compile(
    r"^https?://dev\.socrata\.com/foundry/([^/]+)/([a-z0-9]{4}-[a-z0-9]{4})", re.I)
_SOCRATA_META_COLUMNS = 250
_SOCRATA_META_BUDGET = 24000


def _html_to_text(html):
    """HTML -> readable text; crude tag strip if bs4 is unavailable."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "form"]):
            tag.decompose()
        text = soup.get_text("\n")
    except Exception:
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        text = re.sub(r"<[^>]+>", " ", text)
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


def _socrata_dataset_ref(url):
    """(domain, dataset_id) when ``url`` points at a Socrata dataset, else None."""
    m = _SOCRATA_FOUNDRY_RE.match(url)
    if m:
        return m.group(1).lower(), m.group(2).lower()
    m = re.match(r"^https?://([^/]+)(/.*)?$", url)
    if not m:
        return None
    domain, path = m.group(1).lower(), m.group(2) or ""
    m = re.search(r"/(?:resource|api/views|api/id)/([a-z0-9]{4}-[a-z0-9]{4})(?:\.\w+)?(?:[/?#]|$)", path, re.I)
    if not m:
        m = re.search(r"/([a-z0-9]{4}-[a-z0-9]{4})/?(?:[?#]|$)", path, re.I)
    return (domain, m.group(1).lower()) if m else None


def _socrata_metadata_text(domain, dataset_id):
    """The dataset's real column list from Socrata's views endpoint: the one
    place the true field names live, so the writer does not guess them."""
    resp = requests.get(f"https://{domain}/api/views/{dataset_id}.json",
                        timeout=_FETCH_TIMEOUT, headers=_DOC_HEADERS)
    resp.raise_for_status()
    meta = resp.json()
    lines = [f"Dataset: {meta.get('name', '')} (id {dataset_id})",
             f"SODA endpoint: https://{domain}/resource/{dataset_id}.json"]
    desc = " ".join(str(meta.get("description") or "").split())
    if desc:
        lines.append(f"Description: {desc[:1200]}")
    columns = meta.get("columns") or []
    lines.append(f"Columns ({len(columns)}; use these exact field names in $select/$where):")
    for col in columns[:_SOCRATA_META_COLUMNS]:
        field = col.get("fieldName") or ""
        if not field or field.startswith(":"):
            continue
        entry = f"  {field} ({col.get('dataTypeName', '')})"
        cdesc = " ".join(str(col.get("description") or col.get("name") or "").split())
        if cdesc and cdesc.lower() != field.lower():
            entry += f": {cdesc[:90]}"
        lines.append(entry)
    return "\n".join(lines)


def _fetch_doc_page(url):
    resp = requests.get(url, timeout=_FETCH_TIMEOUT, headers=_DOC_HEADERS)
    if resp.status_code in (403, 406):
        resp = requests.get(url, timeout=_FETCH_TIMEOUT, headers=_DOC_HEADERS_BROWSER)
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "")
    if not any(t in ctype for t in ("html", "text", "json", "xml")):
        return ""
    return _html_to_text(resp.text) if "html" in ctype else resp.text


def fetch_doc_text(urls, log=print):
    """Fetch documentation pages within the text budgets; failures are logged
    and skipped. Returns "" when nothing could be fetched."""
    seen, socrata_seen, chunks, used = set(), set(), [], 0
    for url in urls:
        if not url or not url.lower().startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        if used >= _DOC_TEXT_BUDGET:
            break
        ref = _socrata_dataset_ref(url)
        if ref and ref not in socrata_seen:
            socrata_seen.add(ref)
            try:
                meta = _socrata_metadata_text(*ref)[:_SOCRATA_META_BUDGET]
                chunks.append(f"----- Dataset schema for {ref[1]} on {ref[0]} -----\n{meta}")
                log(f"Read the column list of Socrata dataset {ref[1]}.")
            except Exception as e:
                log(f"Could not read Socrata metadata for {ref[1]} ({e}).")
        try:
            text = _fetch_doc_page(url)
        except Exception as e:
            log(f"Could not fetch {url} ({e}).")
            continue
        if not text.strip():
            continue
        snippet = text[:min(_DOC_TEXT_PER_URL, _DOC_TEXT_BUDGET - used)]
        used += len(snippet)
        log(f"Read {len(snippet):,} characters of documentation from {url}.")
        chunks.append(f"----- Documentation from {url} -----\n{snippet}")
    return "\n\n".join(chunks)


# ── Prompts ──────────────────────────────────────────────────────────────────

_EXAMPLE_HANDBOOK = {
    "data_source_name": "OpenAQ API (Global Air Quality Observations)",
    "brief_description": (
        "OpenAQ provides globally aggregated, station-level air quality observations (PM2.5, PM10, O3, NO2, "
        "SO2, CO and other pollutants) from government and research monitoring networks worldwide. Coverage "
        "and historical depth vary by country and station; some stations go back a decade or more."),
    "handbook": (
        "OpenAQ data is accessed via the REST API at https://api.openaq.org/v3/.\n"
        "IMPORTANT: v3 requires an API key on every request, sent as the header 'X-API-Key: {OPENAQ_API_KEY}'. "
        "Requests without this header return 401/403.\n"
        "Monitoring stations are called \"locations\". Use GET /v3/locations to discover stations; each has an id, name, "
        "coordinates, and the list of sensors (parameter + sensor id) it reports.\n"
        "Spatial filtering on /v3/locations supports either 'coordinates=LAT,LON' with 'radius' (meters, max 25000), or "
        "'bbox=MIN_LON,MIN_LAT,MAX_LON,MAX_LAT'. Only one of the two may be used per request.\n"
        "To get measurements for a station, read its sensor ids from the location's 'sensors' list, then call "
        "GET /v3/sensors/{sensor_id}/measurements.\n"
        "Temporal filtering uses 'date_from' and 'date_to' as ISO 8601 timestamps (e.g. 2024-01-01T00:00:00Z).\n"
        "Pagination uses 'limit' (max 1000) and 'page' (1-indexed); keep incrementing 'page' until 'results' is empty.\n"
        "The free tier allows roughly 60 requests/minute; on a 429 response, back off and retry.\n"
        "If the requested area is provided as a place name, get its bounding box from OpenStreetMap "
        "(e.g. `ox.geocode_to_gdf(place_name)`); do not guess coordinates.\n"
        + HANDBOOK_TAIL),
    "code_example": (
        "import os\n"
        "import requests\n"
        "import pandas as pd\n\n"
        "def download_data():\n"
        "    API_KEY = os.environ[\"OPENAQ_API_KEY\"]\n"
        "    BASE_URL = \"https://api.openaq.org/v3\"\n"
        "    HEADERS = {\"X-API-Key\": API_KEY}\n\n"
        "    # Illustrative values: substitute the task's own area, pollutant and dates.\n"
        "    resp = requests.get(f\"{BASE_URL}/locations\", headers=HEADERS,\n"
        "                        params={\"coordinates\": \"40.4406,-79.9959\", \"radius\": 25000, \"limit\": 100}, timeout=30)\n"
        "    resp.raise_for_status()\n"
        "    sensor_ids = [s[\"id\"] for loc in resp.json()[\"results\"] for s in loc.get(\"sensors\", [])\n"
        "                  if s.get(\"parameter\", {}).get(\"name\") == \"pm25\"]\n\n"
        "    rows = []\n"
        "    for sensor_id in sensor_ids:\n"
        "        page = 1\n"
        "        while True:\n"
        "            try:\n"
        "                r = requests.get(f\"{BASE_URL}/sensors/{sensor_id}/measurements\", headers=HEADERS,\n"
        "                                 params={\"date_from\": \"2024-01-01T00:00:00Z\", \"date_to\": \"2024-01-07T23:59:59Z\",\n"
        "                                         \"limit\": 1000, \"page\": page}, timeout=30)\n"
        "                r.raise_for_status()\n"
        "                results = r.json()[\"results\"]\n"
        "            except Exception as e:\n"
        "                print(f\"Skipping sensor {sensor_id} page {page}: {e}\")\n"
        "                break\n"
        "            if not results:\n"
        "                break\n"
        "            rows += [{\"sensor_id\": sensor_id, \"value\": m.get(\"value\"),\n"
        "                      \"datetime\": m.get(\"period\", {}).get(\"datetimeFrom\", {}).get(\"utc\")} for m in results]\n"
        "            page += 1\n\n"
        "    df = pd.DataFrame(rows)\n"
        "    df.to_csv(\"openaq_measurements.csv\", index=False)\n"
        "    print(f\"Saved {len(df)} rows to openaq_measurements.csv\")\n\n"
        "download_data()\n"),
    "website": "https://openaq.org",
    "requires_key": "true",
    "key_name": "OPENAQ_API_KEY",
    "key_signup_url": "https://explore.openaq.org",
    "caveats": "Free tier is rate limited (about 60 requests/minute).",
}


def _writer_rules(source_id=None):
    return (
        "Handbook rules:\n"
        "- handbook: one requirement per line (base URL, endpoints, parameters, spatial filtering, response "
        "structure, pagination, rate limits, save format, pitfalls). Do not number the lines.\n"
        "- Credentials: requires_key is 'true' or 'false'. key_name: comma-separated UPPER_SNAKE environment-"
        "variable names, one per credential the source needs (e.g. 'EOG_CLIENT_ID,EOG_CLIENT_SECRET'), '' if "
        "none - and code_example must read exactly these names via os.environ[\"NAME\"] (which raises KeyError "
        "when unset). If the source needs only ONE credential (the common case - a single API key), key_name "
        "must list exactly ONE name; never list alias spellings of the same credential (e.g. never "
        "'FIRMS_MAP_KEY,NASA_FIRMS_MAP_KEY,MAP_KEY'), because each entry becomes its own field the user must "
        "fill in. Pick the ONE name the source's own documentation uses. If the handbook prose shows a "
        "credential inside an endpoint, header or URL pattern, write it as the exact key_name in curly braces "
        "(e.g. {EOG_CLIENT_ID}); the real value is substituted into exactly that token. Never invent or hard-"
        "code a credential value, and never silently continue, fall back to a keyless endpoint or return "
        "placeholder data when a credential is missing.\n"
        "- The handbook text must end with exactly these lines:\n"
        f"{HANDBOOK_TAIL}\n"
        "- Reusability: the handbook documents the SOURCE's general capabilities and must work for any future "
        "task against it. Never bake one task's place names, coordinates, dates or tag values into the handbook "
        "as permanent facts; label any worked query as illustrative.\n"
        "- Keep downloads fast and bounded: document result-count/size estimation if the source offers it, "
        "server-side filters (fields, bbox, date windows) and server-side limits/timeouts.\n"
        "- If areas are given as place names, tell the agent to look up the bounding box from OpenStreetMap "
        "(e.g. ox.geocode_to_gdf) rather than guessing coordinates.\n"
        "- code_example: one complete runnable Python script with a download_data() function called on the last "
        "line. It must download a SMALL sample (small area, short period) and save it to a file in the current "
        "directory using a relative file name, then print the row/feature count and file name. Do NOT wrap the "
        "initial request in try/except; let real bugs fail loudly. When looping over many pages/batches/items, "
        "wrap EACH iteration in its own narrow try/except that logs and skips that item. Call raise_for_status() "
        "after each request. Prefer requests, pandas, geopandas, osmnx, rasterio (already installed).\n"
        "- brief_description: 1-3 sentences telling an AI when to use this source; include extent, period and "
        "the kinds of data offered.\n"
        "- key_signup_url: the exact page where a user registers for the credentials ('' if no key needed).\n"
        "- caveats: short user-facing warnings, one per line (cost/paid tiers, registration, rate limits, "
        "licence, coverage gaps), '' if none.\n"
        "- Use only facts from the research provided or that you are confident are current; never fabricate "
        "endpoints or parameters.\n"
    )


def _reply_shape():
    return ("Reply with ONLY a JSON object with these string keys: "
            + ", ".join(FIELDS) + ". Start the reply with { and end it with } - no introduction, no "
            "code fences, no comments. Inside the strings, write line breaks as \\n and escape double quotes.")


def _writer_prompt(source_id, context):
    example = json.dumps(_EXAMPLE_HANDBOOK, ensure_ascii=False, indent=2)
    return (
        f"Draft a data-retrieval handbook for the data source below. The source ID is '{source_id}'.\n\n"
        f"{_writer_rules(source_id)}\n{_reply_shape()}\n\n"
        f"EXAMPLE:\n{example}\n\n{context}")


_SYSTEM_PROMPT = (
    "You are a professional GIScience data engineer with 20+ years of experience collecting geospatial data "
    "and writing the technical 'handbooks' that let an automated agent download it. You know the real APIs, "
    "endpoints, parameters, authentication schemes and practical pitfalls of OpenStreetMap, the US Census "
    "Bureau, NASA Earthdata, USGS, Copernicus, EPA, OpenTopography and hundreds of other providers. Be precise "
    "and factual; if you are unsure of an exact endpoint or parameter, describe the documented behaviour rather "
    "than inventing a URL.")


# ── Verification (run code_example in a separate process) ───────────────────

def _file_has_data(path):
    """Whether one output file carries at least one record. A run that exits 0
    but writes a header-only CSV, [] or an empty FeatureCollection has NOT
    shown a working query."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if size == 0:
        return False
    ext = os.path.splitext(path)[1].lower()
    if ext not in _TEXT_SAMPLE_EXTS:
        return True
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(10000)
    except OSError:
        return False
    if ext in (".json", ".geojson"):
        if len(text) >= 9999:
            return True  # large file: real content
        try:
            doc = json.loads(text)
        except ValueError:
            return bool(text.strip())
        if isinstance(doc, dict) and "features" in doc:
            return bool(doc.get("features"))
        return bool(doc)
    if ext in (".csv", ".tsv"):
        return len([ln for ln in text.splitlines() if ln.strip()]) >= 2
    return bool(text.strip())


def _empty_output_error(run_dir, files):
    if not files:
        return ("EmptyOutputError: the sample download exited without error but wrote NO files. "
                "It must save at least one file containing real records.")
    sizes = []
    for name in files:
        path = os.path.join(run_dir, name)
        if os.path.isfile(path) and _file_has_data(path):
            return ""
        try:
            sizes.append(f"{name} ({os.path.getsize(path)} bytes)")
        except OSError:
            sizes.append(name)
    return ("EmptyOutputError: the sample download exited without error but every file it wrote is empty "
            f"or holds no records: {', '.join(sizes)}. The query/filters matched nothing; probe the source for "
            "its real field names and values and fix the filters.")


def _error_signature(err):
    """A stable 'same failure as before?' signature that ignores volatile
    details like the exact URL, so superficially different retries of the
    same broken approach still count against the same-error limit."""
    last_line = err.strip().splitlines()[-1] if err.strip() else ""
    last_line = re.split(r"\s+for url:", last_line, maxsplit=1)[0]
    # Any "ExceptionType: message" line (requests' ConnectTimeout etc. do not end in Error).
    match = re.match(r"^([A-Za-z_][\w.]*):\s*(.*)$", last_line)
    if not match:
        return last_line
    exc_type, detail = match.groups()
    status = re.match(r"^(\d{3})\b", detail)
    return f"{exc_type}:{status.group(1)}" if status else exc_type


def run_code_example(code, python_exe, keys=None, should_stop=None):
    """Run ``code`` in a fresh temp folder with ``python_exe``; ``keys``
    ({NAME: value}) are exported as environment variables and also fill
    {NAME} placeholders. Returns (error_text, files, stdout) -- error_text is
    "" on success."""
    keys = {k: v for k, v in (keys or {}).items() if v}
    code = substitute_placeholders(code, keys)
    env = {**os.environ, **keys}
    work_dir = tempfile.mkdtemp(prefix="aggra_handbook_test_")
    script = os.path.join(work_dir, "_handbook_test.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(code)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        proc = subprocess.Popen([python_exe, script], cwd=work_dir, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                errors="replace", creationflags=flags, env=env)
        started = time.time()
        while True:
            try:
                out, err = proc.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                if should_stop and should_stop():
                    proc.kill()
                    proc.communicate()
                    raise Cancelled()
                if time.time() - started > _VERIFY_TIMEOUT:
                    proc.kill()
                    proc.communicate()
                    return (f"TimeoutError: timed out after {_VERIFY_TIMEOUT}s - likely downloading too much; "
                            "shrink the example's area/time window.", [], "")
        if proc.returncode != 0:
            return (err or out or f"Exited with code {proc.returncode}")[-3000:], [], out or ""
        files = sorted(f for f in os.listdir(work_dir)
                       if f != "_handbook_test.py" and os.path.isfile(os.path.join(work_dir, f)))
        empty = _empty_output_error(work_dir, files)
        if empty and (out or "").strip():
            empty = f"RUN STDOUT (tail):\n{out[-1500:]}\n\n{empty}"
        return empty, files, out or ""
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _revise_prompt(source_id, context, source, err, sig, streak, docs_text):
    repeat_note = ""
    if streak > 1:
        repeat_note = (f"\n\nThis is the SAME underlying failure ({sig}) as your last {streak - 1} attempt(s); "
                       "your previous fix did not address the root cause. Do not repeat a change you already "
                       "tried; check the documentation below instead of guessing another endpoint.")
    docs_block = (f"\n\nRELEVANT DOCUMENTATION (ground your fix in this):\n\n{docs_text}" if docs_text else "")
    return (
        f"{_writer_prompt(source_id, context)}\n\n"
        "Your previous handbook's code_example FAILED when executed. Diagnose the root cause from the error "
        "below, then return an IMPROVED handbook (same JSON keys). Typical fixes: correct a wrong endpoint or "
        "parameter; add a required parameter; switch the saved file format; handle pagination or rate limits; "
        "fix the authentication. Change ONLY what the error requires."
        f"{repeat_note}\n\nPREVIOUS HANDBOOK:\n{json.dumps(source, ensure_ascii=False, indent=2)}"
        f"\n\nERROR:\n{err}{docs_block}")


def missing_credentials(source, keys=None):
    """Credential names the code example needs (its os.environ reads plus the
    declared key_name) that have no value in ``keys`` or the environment."""
    have = {k.lower() for k, v in (keys or {}).items() if v}
    names = env_names_in_code(source.get("code_example", ""))
    if source.get("requires_key") == "true":
        names += [n for n in split_key_names(source.get("key_name", "")) if n not in names]
    return [n for n in names if n.lower() not in have and not os.environ.get(n)]


def verify_source(source, source_id, python_exe, backend=None, keys=None, context="",
                  log=print, should_stop=None):
    """Run the handbook's code_example; when ``backend`` is given, feed
    failures back to the model and retry. ``keys`` ({NAME: value}) are the
    data-source credentials. Returns (source, report) where report =
    {status: verified|failed|skipped_needs_key, attempts, error, files, missing}."""
    def check_stop():
        if should_stop and should_stop():
            raise Cancelled()

    attempts, last_sig, streak, docs_text = 0, None, 0, None
    while True:
        check_stop()
        code = source.get("code_example", "")
        if not code.strip():
            return source, {"status": "failed", "attempts": attempts, "files": [],
                            "error": "The handbook has no code example to test."}
        missing = missing_credentials(source, keys)
        if missing:
            log(f"Test skipped: enter a value for {', '.join(missing)}, then press 'Test code' to run it.")
            return source, {"status": "skipped_needs_key", "attempts": attempts, "error": "", "files": [],
                            "missing": missing}

        attempts += 1
        log(f"Test run {attempts}: running the sample download in a separate Python process...")
        err, files, _stdout = run_code_example(code, python_exe, keys, should_stop)
        if not err:
            log(f"Test passed: the sample download saved {', '.join(files)}.")
            return source, {"status": "verified", "attempts": attempts, "error": "", "files": files}

        sig = _error_signature(err)
        streak = streak + 1 if sig == last_sig else 1
        last_sig = sig
        log(f"Test run {attempts} failed: {sig}")
        if backend is None or streak >= _SAME_ERROR_LIMIT or attempts >= _MAX_VERIFY_ATTEMPTS:
            reason = ("no AI available to fix it" if backend is None
                      else "the same error repeated" if streak >= _SAME_ERROR_LIMIT
                      else "reached the attempt limit")
            log(f"Stopping the test ({reason}). Review the handbook before saving.")
            return source, {"status": "failed", "attempts": attempts, "error": err, "files": []}

        check_stop()
        if docs_text is None:
            docs_text = fetch_doc_text(extract_urls(context) + [source.get("website", "")], log=log)
        log("Asking the AI to fix the handbook...")
        try:
            data = backend.chat_json([{"role": "system", "content": _SYSTEM_PROMPT},
                                      {"role": "user", "content": _revise_prompt(
                                          source_id, context, source, err, sig, streak, docs_text)}],
                                     expected_keys=("handbook", "code_example"), log=log)
            source = normalize_source(data, source.get("data_source_name", ""), source.get("website", ""))
        except ValueError as e:
            log(f"The AI reply could not be read ({e}); keeping the previous version.")
            return source, {"status": "failed", "attempts": attempts, "error": err, "files": []}


# ── Generation ───────────────────────────────────────────────────────────────

def generate_handbook(query, backend, website="", source_id="", verify=True, python_exe=None,
                      keys=None, log=print, should_stop=None):
    """Draft a complete handbook: find source -> analyse access -> draft ->
    (optionally) verify. Returns (source_id, source, report_or_None)."""
    def check_stop():
        if should_stop and should_stop():
            raise Cancelled()

    query = (query or "").strip()
    if not query:
        raise ValueError("Describe the data source (or paste its API link) to generate a handbook.")
    user_urls = extract_urls(website) + extract_urls(query)

    mode = "with live web search" if backend.has_web_search else "without web search (GIBD key)"
    log(f"Using {backend.model} {mode}.")

    user_docs = ""
    if not backend.has_web_search and user_urls:
        log("Reading the documentation links you provided...")
        user_docs = fetch_doc_text(user_urls, log=log)
    check_stop()

    log("Step 1/4: finding the best official source for your request...")
    hint = f"\nUser-provided website/docs: {website}" if website else ""
    docs_block = f"\n\nDOCUMENTATION:\n{user_docs}" if user_docs else ""
    src = backend.research(
        "Given a data need, source name, or API link, pick the single best public data source. Confirm it "
        "exists and find the official website and documentation URL. Reply with ONLY a JSON object: "
        '{"name": str, "short_name": str (a short ID such as NASA_FIRMS or USGS_Water: letters, digits '
        'and underscores, at most 24 characters), "provider": str, "website": str, "docs_url": str, "why": str}'
        f"\n\nData need: {query}{hint}{docs_block}", log=log)
    log(f"Selected: {src.get('name') or 'the data source'} ({src.get('provider') or 'official provider'}).")
    check_stop()

    log("Step 2/4: reading the documentation and working out the access method...")
    docs = fetch_doc_text([src.get("docs_url", ""), src.get("website", "")] + user_urls, log=log)
    check_stop()
    access = backend.research(
        "Determine exactly how to retrieve this data programmatically with Python. The documentation below "
        "may be thin or empty. Start from your own well-established knowledge of this source's real API, then "
        "verify or fill in anything you are unsure of, anything likely to have changed (API versions, "
        "deprecated endpoints, auth schemes) or anything the documentation does not cover. Record real "
        "endpoints, parameters, auth, formats, pagination and rate limits in notes - only facts you are "
        "confident are current; never fabricate a URL or parameter. Reply with ONLY a JSON object: "
        '{"method": str, "base_url": str, "requires_key": bool, '
        '"key_name": str (comma-separated UPPER_SNAKE env-var names, "" if none), '
        '"key_signup_url": str, "notes": str}'
        f"\n\nData need: {query}\nSource: {json.dumps(src)}\n\nDOCUMENTATION:\n{docs}", log=log)
    auth = "an API key is required" if access.get("requires_key") else "no API key is required"
    log(f"Access: {access.get('method') or 'programmatic'} at {access.get('base_url') or 'the documented endpoint'}; {auth}.")
    check_stop()

    source_id = make_source_id(source_id or src.get("short_name") or src.get("name") or query)
    context = f"Data need: {query}\nSource: {json.dumps(src)}\nAccess: {json.dumps(access)}"
    log(f"Step 3/4: writing the handbook and a runnable example (source ID: {source_id})...")
    data = backend.chat_json([{"role": "system", "content": _SYSTEM_PROMPT},
                              {"role": "user", "content": _writer_prompt(source_id, context)}],
                             expected_keys=("handbook", "code_example"), log=log)
    source = normalize_source(data, src.get("name") or query, src.get("website") or website)
    if not source["key_signup_url"] and source["requires_key"] == "true":
        source["key_signup_url"] = str(access.get("key_signup_url") or "")
    log("Draft ready.")

    report = None
    if verify and python_exe:
        check_stop()
        log("Step 4/4: testing the code example...")
        source, report = verify_source(source, source_id, python_exe, backend=backend,
                                       keys=keys, context=context,
                                       log=log, should_stop=should_stop)
    else:
        log("Step 4/4: test skipped.")
    log("Done. Review and edit the handbook, then press Save.")
    return source_id, source, report


# ── Refinement (conversational edits) ───────────────────────────────────────

_REFINE_INSTRUCTIONS = """\
You are REFINING an existing handbook based on the user's message - most often an error they hit when \
running the code, or a request to change behaviour (output format, an endpoint, a parameter). You are given \
the CURRENT handbook as JSON plus the user's message.

Return an IMPROVED handbook. Change ONLY what the message requires; keep everything that already works and \
preserve the user's manual edits where they don't conflict. Do not bake one task's specific values \
(coordinates, dates, place names) into the handbook as permanent facts; fix gaps generically.

Return ONLY a single JSON object with the SAME handbook keys as before PLUS one extra key:
- "assistant_message": 1-3 plain-text sentences (no code) explaining what you changed and why."""


def refine_handbook(current, message, backend, source_id, history=None, log=print):
    """Apply a conversational change request to the current draft. Returns
    (source, assistant_message)."""
    if not (message or "").strip():
        raise ValueError("Type what you want the AI to change.")
    current = current if isinstance(current, dict) else {}
    docs = ""
    urls = extract_urls(message)
    if urls:
        docs = fetch_doc_text(urls, log=log)

    draft = {k: str(current.get(k, "") or "") for k in FIELDS}
    prompt = (f"{_REFINE_INSTRUCTIONS}\n\n{_writer_rules(source_id)}\n"
              f"CURRENT HANDBOOK (JSON):\n{json.dumps(draft, ensure_ascii=False, indent=2)}\n\n"
              f"USER MESSAGE:\n{message.strip()}")
    if docs:
        prompt += f"\n\nDocumentation fetched from links in the message:\n\n{docs}"

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for turn in (history or [])[-10:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": str(turn["content"])})
    messages.append({"role": "user", "content": prompt})

    data = backend.chat_json(messages, expected_keys=("handbook", "code_example", "assistant_message"), log=log)
    source = normalize_source(data, current.get("data_source_name", ""), current.get("website", ""))
    return source, (str(data.get("assistant_message") or "").strip() or "Updated the handbook.")


# ── Saving ───────────────────────────────────────────────────────────────────

def _toml_string(value):
    """A TOML string for ``value``: a readable multi-line literal string when
    possible, otherwise a JSON-quoted basic string (also valid TOML)."""
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    has_control = any(ord(c) < 32 and c not in "\n\t" for c in value)
    if "'''" not in value and not has_control and not value.endswith("'"):
        return "'''\n" + value.strip("\n") + "\n'''"
    return json.dumps(value, ensure_ascii=False)


def to_toml(source):
    """Serialise handbook fields to TOML text in the plugin's house layout."""
    s = {k: str(source.get(k, "") or "") for k in FIELDS}
    parts = [
        "# Handbook created with the Handbook Studio of the AutonomousGIS GeoData Retriever Agent.",
        "# The ID of the data source is the name of this file.",
        "",
        f"data_source_name = {json.dumps(s['data_source_name'], ensure_ascii=False)}",
        "",
        "# Brief description: tells the AI when to use this data source.",
        f"brief_description = {_toml_string(s['brief_description'])}",
        "",
        "# Technical requirements, one per line. {code_example} is replaced by the code below,",
        "# and {KEY_NAME} by the value of that credential stored in <ID>.keys.",
        f"handbook = {_toml_string(s['handbook'])}",
        "",
        "# The code reads credentials with os.environ[\"KEY_NAME\"].",
        f"code_example = {_toml_string(s['code_example'])}",
        "",
        f"website = {json.dumps(s['website'], ensure_ascii=False)}",
        "# Credentials (comma-separated names); their values are stored in <ID>.keys, never here.",
        f"requires_key = {json.dumps(s['requires_key'])}",
        f"key_name = {json.dumps(s['key_name'], ensure_ascii=False)}",
        f"key_signup_url = {json.dumps(s['key_signup_url'], ensure_ascii=False)}",
        f"caveats = {_toml_string(s['caveats'])}",
        "",
    ]
    return "\n".join(parts)


def load_toml_source(path):
    """Read a handbook file into the editable fields (unknown keys ignored)."""
    try:
        import tomllib as _toml
    except ImportError:
        import tomli as _toml
    with open(path, "rb") as fh:
        data = _toml.load(fh)
    # Old template.toml spelled the field 'hand_book'.
    if "handbook" not in data and "hand_book" in data:
        data["handbook"] = data["hand_book"]
    # Older handbooks have no requires_key/key_name; they reference their key as
    # a {<ID>_key} placeholder, which then becomes the credential name.
    if not data.get("key_name"):
        legacy = re.findall(r"\{(\w+_key)\}", f"{data.get('handbook', '')}\n{data.get('code_example', '')}")
        if legacy:
            data["key_name"] = ",".join(dict.fromkeys(legacy))
            data.setdefault("requires_key", "true")
    data.setdefault("requires_key", "false")
    return normalize_source(data)

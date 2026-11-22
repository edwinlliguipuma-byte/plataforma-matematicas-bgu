git checkout 096aa7c -- cursos/modulo_ia.py
@'
import py_compile

p = "cursos/modulo_ia.py"
txt = open(p, encoding="utf-8").read()

helper = """import urllib.error

def _llamar_gemini(api_key, payload):
    modelos = [
        "models/gemini-2.5-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-001",
        "models/gemini-1.5-flash",
        "models/gemini-pro-latest",
    ]
    try:
        u_list = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        with urllib.request.urlopen(u_list, timeout=15) as r:
            items = json.loads(r.read().decode("utf-8")).get("models", [])
        validos = [
            m["name"]
            for m in items
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and "gemini" in m.get("name", "").lower()
            and not any(k in m.get("name", "").lower() for k in ("embedding", "tts", "image", "veo", "aqa"))
        ]
        if validos:
            modelos = [m for m in modelos if m in validos] + [m for m in validos if m not in modelos]
    except Exception:
        pass

    ultimo_err = "No hay modelos Gemini disponibles."
    data_bytes = json.dumps(payload).encode("utf-8")
    for mod in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/{mod}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="ignore")
            ultimo_err = f"HTTP {e.code} en {mod}: {msg[:200]}"
            if e.code in (400, 404):
                continue
            raise Exception(ultimo_err)
    raise Exception(ultimo_err)


@staff_member_required
def crear_modulo_ia(request):"""

old_block = """            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]"""

new_block = """            try:
                data = _llamar_gemini(api_key, payload)
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.split(chr(10), 1)[-1].rsplit("```", 1)[0].strip()"""

assert "@staff_member_required\ndef crear_modulo_ia(request):" in txt
assert old_block in txt
txt = txt.replace("@staff_member_required\ndef crear_modulo_ia(request):", helper, 1).replace(old_block, new_block, 1)
open(p, "w", encoding="utf-8").write(txt)
py_compile.compile(p, doraise=True)
print("OK: Archivo actualizado y verificado sin errores de sintaxis")
'@ | Set-Content -Encoding UTF8 fix_gemini.py
python fix_gemini.py
Remove-Item fix_gemini.py
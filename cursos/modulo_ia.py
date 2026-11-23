@'
import re, py_compile

p = "cursos/modulo_ia.py"
txt = open(p, encoding="utf-8").read()

print("--- LINEAS ACTUALES CON GEMINI ---")
for i, l in enumerate(txt.splitlines(), 1):
    if any(w in l for w in ("generativelanguage", "_gemini_url", "except Exception")):
        print(f"L{i}: {l.strip()}")

new_helper = '''def _gemini_url(k):
    import json, urllib.request
    k = (k or "").strip()
    preferidos = [
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
        "models/gemini-2.0-flash-001",
        "models/gemini-flash-latest",
        "models/gemini-2.5-pro",
    ]
    try:
        req_list = urllib.request.urlopen(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={k}", timeout=12
        )
        data = json.loads(req_list.read().decode("utf-8"))
        validos = [
            m["name"] for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and not any(x in m.get("name", "") for x in ("tts", "image", "audio", "embedding", "exp", "preview", "1.5"))
        ]
        for mod in preferidos:
            if mod in validos:
                return f"https://generativelanguage.googleapis.com/v1beta/{mod}:generateContent?key={k}"
        flash = [m for m in validos if "flash" in m]
        if flash:
            return f"https://generativelanguage.googleapis.com/v1beta/{flash[0]}:generateContent?key={k}"
    except Exception:
        pass
    return f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={k}"

'''

if "def _gemini_url(" in txt:
    txt = re.sub(r"def _gemini_url\(.*?\n(?=@staff_member_required|def )", new_helper, txt, count=1, flags=re.S)
else:
    txt = re.sub(r"(?m)^(@staff_member_required\s*\r?\ndef )", new_helper + r"\1", txt, count=1)

txt, n1 = re.subn(
    r"url\s*=\s*f?['\"]https://generativelanguage\.googleapis\.com/[^\r\n]+",
    "url = _gemini_url(api_key)",
    txt
)

txt, n2 = re.subn(
    r"f?['\"]https://generativelanguage\.googleapis\.com/v1beta/models/[^'\"]+:generateContent\?key=\{[^}]+\}['\"]",
    "_gemini_url(api_key)",
    txt
)

def _wrap_exc(m):
    ind = m.group(1)
    inner = ind + "    "
    return (
        f"{ind}except Exception as e:\n"
        f"{inner}_det = e.read().decode('utf-8', errors='ignore')[:240] if hasattr(e, 'read') else ''\n"
        f"{inner}if _det:\n"
        f"{inner}    e = Exception(f'{{e}} | {{locals().get(\"url\", \"\").split(\"?\")[0].split(\"/\")[-1]}} -> {{_det}}')\n"
    )

if "_det = e.read()" not in txt:
    txt = re.sub(r"(?m)^([ \t]*)except Exception as e:\s*\r?\n", _wrap_exc, txt)

open(p, "w", encoding="utf-8").write(txt)
py_compile.compile(p, doraise=True)
print(f"OK_REPARADO | Rutas actualizadas: {n1 + n2}")
'@ | Set-Content -Encoding UTF8 reparar_ia.py; python reparar_ia.py; Remove-Item reparar_ia.py
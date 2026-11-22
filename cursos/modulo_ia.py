python -c '
p = "cursos/modulo_ia.py"
txt = open(p, encoding="utf-8").read()

helper = """import urllib.error

def _invocar_gemini_auto(api_key, payload):
    candidatos = [
        "models/gemini-2.5-flash",
        "models/gemini-flash-latest",
        "models/gemini-3-flash-preview",
        "models/gemini-2.0-flash",
        "models/gemini-pro-latest",
    ]
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        with urllib.request.urlopen(list_url, timeout=15) as r:
            modelos_data = json.loads(r.read().decode("utf-8")).get("models", [])
        disponibles = [
            m["name"]
            for m in modelos_data
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and "gemini" in m.get("name", "").lower()
            and not any(x in m.get("name", "").lower() for x in ["embedding", "tts", "image", "aqa", "vision"])
        ]
        flash_disp = [m for m in disponibles if "flash" in m.lower()]
        otros_disp = [m for m in disponibles if "flash" not in m.lower()]
        ordenados = []
        for m in candidatos + flash_disp + otros_disp:
            if m not in ordenados and (not disponibles or m in disponibles):
                ordenados.append(m)
        if ordenados:
            candidatos = ordenados
    except Exception:
        pass

    ultimo_error = "No se encontro un modelo Gemini disponible."
    body_bytes = json.dumps(payload).encode("utf-8")
    for modelo in candidatos:
        url = f"https://generativelanguage.googleapis.com/v1beta/{modelo}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            detalle = he.read().decode("utf-8", errors="ignore")
            ultimo_error = f"HTTP {he.code} ({modelo}): {detalle[:220]}"
            if he.code == 404:
                continue
            raise Exception(ultimo_error)
    raise Exception(ultimo_error)


@staff_member_required
def crear_modulo_ia(request):"""

old_call = """            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
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

new_call = """            try:
                data = _invocar_gemini_auto(api_key, payload)
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("\\n", 1)[-1].rsplit("```", 1)[0].strip()"""

assert "@staff_member_required\ndef crear_modulo_ia(request):" in txt, "No se encontro crear_modulo_ia"
assert old_call in txt, "No se encontro el bloque antiguo"
txt = txt.replace("@staff_member_required\ndef crear_modulo_ia(request):", helper, 1).replace(old_call, new_call, 1)
open(p, "w", encoding="utf-8").write(txt)
print("LISTO: Modelo Gemini auto-detectable actualizado")
'
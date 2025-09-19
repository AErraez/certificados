from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

from flask import send_from_directory


app = Flask(__name__)
CORS(app)

@app.route('/')
def serve_home():
    return send_from_directory('static', 'index.html')

BASE_URL = "https://portal.trabajo.gob.ec"

# === Helpers ===

def get_view_state(html):
    soup = BeautifulSoup(html, "html.parser")
    view_state_input = soup.find("input", {"name": "javax.faces.ViewState"})
    return view_state_input["value"] if view_state_input else None

def extract_table(html):
    soup = BeautifulSoup(html, 'html.parser')
    table_wrapper = soup.find('div', class_='ui-datatable-tablewrapper')
    if not table_wrapper:
        return None

    table = table_wrapper.find('table')
    
    # === Remove "Ver Certificado" column ===

    # Step 1: Identify the index of the "Ver Certificado" column from the <thead>
    thead = table.find('thead')
    ver_cert_index = -1
    headers = thead.find_all('th')
    for i, th in enumerate(headers):
        if th.get_text(strip=True) == "Ver Certificado":
            ver_cert_index = i
            th.decompose()  # Remove the <th> itself
            break

    # Step 2: Remove the corresponding <td> in each row
    if ver_cert_index != -1:
        tbody = table.find('tbody')
        for row in tbody.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > ver_cert_index:
                cells[ver_cert_index].decompose()

    # === Clean up "Nombres" and "Perfil" columns ===
    for th in headers:
        title = th.find("span", class_="ui-column-title")
        if title and title.get_text(strip=True) in ["Nombres", "Perfil"]:
            # Remove label and input elements
            label = th.find("label")
            input_tag = th.find("input")
            if label:
                label.decompose()
            if input_tag:
                input_tag.decompose()

    return str(table_wrapper)


# === Main Route ===

from flask import Response

@app.route('/api/proxy', methods=['POST'])
def proxy_request():
    cedula = request.get_json().get("cedula", "").strip()
    if not cedula:
        return jsonify({"error": "Cédula no proporcionada"}), 400

    # --- SESSION 1: Legitimidad Certificación ---
    session1 = requests.Session()
    path1 = "/setec-portal-web/pages/legitimidadCertificacion.jsf"
    url1 = BASE_URL + path1
    headers1 = {
        "User-Agent": "Mozilla/5.0",
        "Referer": url1,
        "Origin": BASE_URL
    }

    res1_get = session1.get(url1, headers=headers1)
    view_state1 = get_view_state(res1_get.text)
    jsessionid1 = session1.cookies.get("JSESSIONID")
    if not view_state1 or not jsessionid1:
        return jsonify({"error": "Error obteniendo ViewState o sesión (página 1)"}), 500

    payload1 = {
        "j_idt24:frmPersonasCert": "",
        "j_idt24:frmPersonasCert:cmbCriterioPersona:cmbCriterioPersona_focus": "",
        "j_idt24:frmPersonasCert:cmbCriterioPersona:cmbCriterioPersona_input": "1",
        "j_idt24:frmPersonasCert:txtDescripcionPersona": cedula,
        "j_idt24:frmPersonasCert:j_idt37": "",
        "javax.faces.ViewState": view_state1
    }

    post_url1 = f"{url1};jsessionid={jsessionid1}"
    res1_post = session1.post(post_url1, headers=headers1, data=payload1)
    table1 = extract_table(res1_post.text)

    if not table1:
        return Response("No se encontró la tabla", status=404, mimetype='text/plain')

    return Response(table1, mimetype='text/html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

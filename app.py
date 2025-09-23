from flask import (
    Flask, request, jsonify, send_from_directory,
    render_template, redirect, url_for, session, Response
)
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

app.secret_key = 'your-secret-key'  # Needed for session handling

# === Static index.html (existing route) ===
@app.route('/')
def serve_home():
    return send_from_directory('static', 'index.html')

# === Mock Login System ===
mock_users = {'admin': 'admin123'}
mock_ids = ['0912345678', '0999999999', '0911111111']

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in mock_users and mock_users[username] == password:
            session['username'] = username
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Credenciales inválidas')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', ids=mock_ids)

@app.route('/form/<id>', methods=['GET', 'POST'])
def form(id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        form_data = request.form  # You can log or print this
        print(f"Formulario recibido para ID {id}:", form_data)
        return redirect(url_for('dashboard'))
    return render_template('form.html', id=id)

# === Proxy API for existing JS frontend ===

BASE_URL = "https://portal.trabajo.gob.ec"

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

    # Remove "Ver Certificado" column
    thead = table.find('thead')
    ver_cert_index = -1
    headers = thead.find_all('th')
    for i, th in enumerate(headers):
        if th.get_text(strip=True) == "Ver Certificado":
            ver_cert_index = i
            th.decompose()
            break

    if ver_cert_index != -1:
        tbody = table.find('tbody')
        for row in tbody.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > ver_cert_index:
                cells[ver_cert_index].decompose()

    for th in headers:
        title = th.find("span", class_="ui-column-title")
        if title and title.get_text(strip=True) in ["Nombres", "Perfil"]:
            if (label := th.find("label")): label.decompose()
            if (input_tag := th.find("input")): input_tag.decompose()

    return str(table_wrapper)

@app.route('/api/proxy', methods=['POST'])
def proxy_request():
    cedula = request.get_json().get("cedula", "").strip()
    if not cedula:
        return jsonify({"error": "Cédula no proporcionada"}), 400

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

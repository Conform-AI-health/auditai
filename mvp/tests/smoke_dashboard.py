import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import app, storage, auth
import urllib.parse
from wsgiref.util import setup_testing_defaults
import io

print('Iniciando smoke test autenticado com dados sinteticos...')
def request(environ, path='/', method='GET', cookie=None, form_data=None):
    env = {}
    setup_testing_defaults(env)
    env['HTTP_HOST'] = '127.0.0.1:5000'
    env['REQUEST_METHOD'] = method
    env['PATH_INFO'] = path
    if cookie:
        env['HTTP_COOKIE'] = cookie
    if form_data:
        body = urllib.parse.urlencode(form_data).encode()
        env['CONTENT_LENGTH'] = str(len(body))
        env['wsgi.input'] = io.BytesIO(body)
    status_box = []
    headers_box = []
    def start_response(s, h):
        status_box.append(s)
        headers_box.append(dict(h))
    res = b''.join(app.app(env, start_response)).decode('utf-8', errors='replace')
    return status_box[0], headers_box[0], res

with storage.connection() as conn:
    storage.initialize()
    user = conn.execute("SELECT * FROM users WHERE username='auditor-aurora'").fetchone()
    print('Usuario encontrado no banco:', user['username'] if user else 'Nao encontrado!')
    session_data = {
        'user': 'auditor-aurora',
        'tenant': 'aurora',
        'tenant_name': 'Aurora Saúde',
        'role': 'auditor',
        'csrf': 'csrf-token-test',
        'termo': 'CFM-2454-2026-v1'
    }
    session_cookie = auth.issue(session_data)
    cookie_str = f'auditia={session_cookie}'

status, headers, body = request({}, '/', 'GET', cookie=cookie_str)
print('Status HTTP Dashboard:', status)
print('Headers:', headers)
if not status.startswith('200'):
    print('Erro no corpo:', body)
assert status.startswith('200'), f'Status inesperado: {status}'
assert 'Solicitações' in body, 'Card Solicitações ausente'
assert 'Aguardando análise' in body, 'Card Aguardando ausente'
assert 'Em análise' in body, 'Card Em análise ausente'
assert 'Pendências de codificação' in body, 'Card Pendências de codificação ausente'
assert 'Pendências documentais' in body, 'Card Pendências documentais ausente'
assert 'Concluídas' in body, 'Card Concluídas ausente'
assert 'glass-panel' in body, 'Warm Glass ausente'
assert 'Situação SLA ↕' in body, 'Link SLA ausente'
print('SMOKE TEST DO DASHBOARD APROVADO COM SUCESSO!')

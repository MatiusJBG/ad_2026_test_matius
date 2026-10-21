import pytds
import certifi
from flask import Flask, jsonify, request
import os
import threading
import time
import requests

app = Flask(__name__)

def getConection():
    return pytds.connect(
        server = os.environ["DB_SERVER"],
        database = os.environ["DB_DATABASE"],
        user = os.environ["DB_USER"],
        password = os.environ["DB_PASS"],
        port = 1433,
        cafile = certifi.where(),
        validate_host = True
    )

def enviar_correo_brevo(destinatario, asunto, contenido_html):
    api_key = os.environ.get("BREVO_API_KEY")
    sender_email = os.environ.get("BREVO_SENDER_EMAIL")

    if not api_key or not sender_email:
        print("[BREVO ERROR]: Faltan las variables BREVO_API_KEY o BREVO_SENDER_EMAIL.")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": api_key
    }
    payload = {
        "sender": {
            "name": "Servidor Cloud",
            "email": sender_email
        },
        "to": [{"email": destinatario}],
        "subject": asunto,
        "htmlContent": contenido_html
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=8)
        return response.status_code in [200, 201, 202]
    except Exception as e:
        print(f"[BREVO ERROR]: {e}")
        return False

@app.route('/api/enviar-correo', methods=['POST'])
def enviar_correo_manual():
    data = request.get_json() or {}
    destinatario = data.get("email", os.environ.get("BREVO_SENDER_EMAIL"))
    asunto = data.get("asunto", "Notificación del Sistema")
    mensaje = data.get("mensaje", "<p>Correo generado tras presionar el botón <b>Enviar Correo</b>.</p>")

    if not destinatario:
        return jsonify({"error": "No se especificó un correo de destino"}), 400

    enviado = enviar_correo_brevo(
        destinatario=destinatario,
        asunto=asunto,
        contenido_html=mensaje
    )

    if enviado:
        return jsonify({"mensaje": f"Correo enviado exitosamente a {destinatario}"}), 200
    
    return jsonify({"error": "No se pudo despachar el correo a través de Brevo"}), 500

@app.route('/test-db', methods=['GET'])
def test_db():
    try:
        conn = getConection()
        cursor = conn.cursor()

        cursor.execute("SELECT DB_NAME()")
        database = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        return jsonify({
            "mensaje": "Conexion Exitosa",
            "base_datos": database
        }), 200

    except Exception as e:
        return jsonify({
            "mensaje": "Error",
            "error": str(e)
        }), 500

### USAR VIEW PR
@app.route('/api/products', methods=['GET'])
def getproducts():
    try:
        conn = getConection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, names, price, stock, version FROM dbo.products_vw"
        )
        products = []

        for row in cursor.fetchall():
            products.append({
                "id": row[0],
                "names": row[1],
                "price": float(row[2]) if row[2] is not None else 0.0,
                "stock": row[3],
                "version": row[4]
            })

        cursor.close()
        conn.close()
        return jsonify(products), 200

    except Exception as e:
        return jsonify({
            "mensaje": "Error al consultar los productos",
            "error": str(e)
        }), 500

@app.route("/api/products/<int:id>", methods=['GET'])
def get_product(id):
    try:
        conn = getConection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, names, price, stock, version FROM dbo.products_vw WHERE id = ?",
            id
        )
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if row:
            return jsonify({
                "id": row[0],
                "names": row[1],
                "price": float(row[2]) if row[2] is not None else 0.0,
                "stock": row[3],
                "version": row[4]
            }), 200

        return jsonify({
            "mensaje": "Producto inexistente"
        }), 404

    except Exception as e:
        return jsonify({
            "mensaje": "error",
            "error": str(e)
        }), 500

@app.route('/api/products', methods=['POST'])
def create_product():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"mensaje": "No existen datos validos"}), 400

        names = data.get("names")
        price = data.get("price")
        stock = data.get("stock")

        if not names or price is None or stock is None:
            return jsonify({"mensaje": "Faltan campos obligatorios: names, price o stock"}), 400

        conn = getConection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO dbo.products (names, price, stock) VALUES (?, ?, ?)",
            names, price, stock
        )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"mensaje": "Producto creado correctamente"}), 201

    except Exception as e:
        return jsonify({
            "mensaje": "Error al crear el producto",
            "error": str(e)
        }), 500

## UPDATE SIN CONTROLES
@app.route("/api/products", methods=['PUT'])
def update_products():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Sin data"}), 400

        conn = getConection()
        cursor = conn.cursor()

        time.sleep(5)

        cursor.execute(
            "UPDATE dbo.products SET names=?, price=?, stock=?, version=version + 1 WHERE id=?",
            data.get('names'), data.get('price'), data.get('stock'), data.get('id')
        )

        if cursor.rowcount == 0:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({"msg": "registro no encontrado"}), 404

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"msg": "Actualizacion hecha exitosamente"}), 200

    except Exception as e:
        return jsonify({
            'error': 'Error al actualizar',
            'msg': str(e)
        }), 500

product_lock = threading.Lock()

## UPDATE CON PESSIMISTIC LOCK (LOCK EN MEMORIA)
@app.route("/api/products/lock", methods=['PUT'])
def update_lock():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"msg": "Falta informacion"}), 400

        with product_lock:
            conn = getConection()
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE dbo.products SET names=?, price=?, stock=?, version=version + 1 WHERE id=?",
                data.get("names"), data.get("price"), data.get("stock"), data.get("id")
            )

            if cursor.rowcount == 0:
                conn.rollback()
                cursor.close()
                conn.close()
                return jsonify({"msg": "Registro no encontrado"}), 404

            conn.commit()
            cursor.close()
            conn.close()

        return jsonify({"msg": "Actualizacion realizada correctamente"}), 200

    except Exception as e:
        return jsonify({
            "msg": "Error al actualizar",
            "error": str(e)
        }), 500

## UPDATE CON OPTIMISTIC LOCKING (VERSION CONTROL)
@app.route("/api/products/version", methods=['PUT'])
def update_version():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"msg": "Datos incompletos"}), 400

        if data.get("version") is None or data.get("id") is None:
            return jsonify({"msg": "Falta parametro (version o id)"}), 400

        conn = getConection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE dbo.products SET names=?, price=?, stock=?, version=version + 1 "
            "WHERE id=? AND version=?",
            data.get('names'), data.get('price'), data.get('stock'), data.get('id'), data.get('version')
        )

        if cursor.rowcount == 0:
            conn.rollback()
            cursor.close()
            conn.close()
            # Conflicto de versión o no existe
            return jsonify({"msg": "Conflicto de concurrencia: el producto fue modificado por otra transaccion o no existe"}), 409

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"msg": "Producto actualizado con exito"}), 200

    except Exception as e:
        return jsonify({"msg": "Error al actualizar", "error": str(e)}), 500

if __name__ == '__main__':
    # Para levantar la segunda instancia solo cambias port=5001
    app.run(host='0.0.0.0', port=5000, debug=True)
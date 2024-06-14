"""
This module takes care of starting the API Server, Loading the DB and Adding the endpoints
"""
from api.RecuperarContraseña import enviar_correo
from api.EmailBienvenida import enviar_correo_bienvenida
import os
from flask import Flask, request, jsonify, url_for, send_from_directory, render_template, flash, redirect
from flask_migrate import Migrate
from flask_swagger import swagger
from api.utils import APIException, generate_sitemap
from api.routes import api
from api.admin import setup_admin
from api.commands import setup_commands
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token, JWTManager
import jwt
import uuid
from flask_mail import Mail, Message
from datetime import datetime, timedelta
import bcrypt
from dotenv import load_dotenv
load_dotenv()

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer
from api.models import db, User, Asignacion_entrenador


ENV = "development" if os.getenv("FLASK_DEBUG") == "1" else "production"
static_file_dir = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), '../public/')
app = Flask(__name__)
app.url_map.strict_slashes = False

# Configuración de la aplicación
app.config['SECRET_KEY'] = 'fit_titans_ajr'  # Cambia esto por una clave secreta segura
app.config['SECURITY_PASSWORD_SALT'] = 'fit_titans_ajr'  # Cambia esto por un salt seguro



# database condiguration
db_url = os.getenv("DATABASE_URL")
if db_url is not None:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace(
        "postgres://", "postgresql://")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:////tmp/test.db"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
MIGRATE = Migrate(app, db, compare_type=True)
db.init_app(app)

# Allow CORS requests to this API
CORS(app)

# add the admin
setup_admin(app)

# add the admin
setup_commands(app)

# Add all endpoints form the API with a "api" prefix
app.register_blueprint(api, url_prefix='/api')

# Handle/serialize errors like a JSON object


@app.errorhandler(APIException)
def handle_invalid_usage(error):
    return jsonify(error.to_dict()), error.status_code

# generate sitemap with all your endpoints

@app.route('/')
def sitemap():
    if ENV == "development":
        return generate_sitemap(app)
    return send_from_directory(static_file_dir, 'index.html')

# any other endpoint will try to serve it like a static file

@app.route('/<path:path>', methods=['GET'])
def serve_any_other_file(path):
    if not os.path.isfile(os.path.join(static_file_dir, path)):
        path = 'index.html'
    response = send_from_directory(static_file_dir, path)
    response.cache_control.max_age = 0  # avoid cache memory
    return response

# Setup the Flask-JWT-Extended extension
app.config["JWT_SECRET_KEY"] = "adios-coroto"  # Change this "super secret" with something else!
jwt = JWTManager(app)

 # contraseña hash

def hash_password(plain_password):
    salt = bcrypt.gensalt()
    print(salt)
    hashed_password = bcrypt.hashpw(plain_password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def check_password(plain_password, hashed_password):
    print(plain_password, hashed_password)
    hashed_password_bytes = hashed_password.encode('utf-8')
    print(plain_password, hashed_password)
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password_bytes)

@app.route('/registro', methods=['POST'])
def registro():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    rol = data.get('rol', False)
    nombre = data.get('nombre')
    telefono = data.get('telefono')

    if not email or not password:
        return jsonify({'message': 'Username and password are required'}), 400

    hashed_password = hash_password(password)
    # Convertir el valor de rol a un booleano si es true sera entrenador, si es false usuario
    rol_booleano = True if rol else False
    user_uuid = str(uuid.uuid4())
    enviar_correo_bienvenida(email)
    new_user = User(email=email, password=hashed_password, rol=rol_booleano, nombre=nombre, telefono=telefono, user_uuid = user_uuid)
    db.session.add(new_user)
    db.session.commit()
    
    # Obtengo el id del usuario recien creado
    user_id = new_user.id
    
    # Devuelvo el ID del usuario como parte de la respuesta
    return jsonify({'message': 'User registered successfully', 'userId': user_id}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'message': 'Username and password are required'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    if not user:
        return jsonify({'message': 'usuario no encontrado'}), 401
    if not check_password(password, user.password) : 
        return jsonify({'message': 'contrasegna incorrecta'}), 402
        
    token = create_access_token(identity= user.id)
    return jsonify({'message': 'Login successful', "token": token, "user_rol" : user.rol, "id" : user.id}), 200
    
# GETTING ALL THE USERS
@app.route("/users", methods=["GET"])
@jwt_required()
def get_all_users():
    all_users = User.query.all()
    mapped_users = list(map(lambda index: index.serialize(), all_users))

    response_body = jsonify(mapped_users)
    return response_body, 200


@app.route("/Usuarios/<int:user_id>", methods=["GET"])
def get_user_by_id(user_id):
    user = User.query.get(user_id)
    usuarios = User.query.filter_by(rol=False).all()
    if user is None and usuarios is True:
        return jsonify({"message": "User not found"}), 404
    return jsonify(user.serialize()), 200 


@app.route('/Usuarios', methods=['GET'])
def obtener_usuarios():
    try:
        usuarios = User.query.filter_by(rol=False).all()
        usuarios_data = [usuarios.serialize() for usuarios in usuarios]
        return jsonify(usuarios_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/Usuarios/<int:id>', methods=['PUT'])
def actualizar_user(id):
    user = User.query.get(id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    data = request.get_json()
    print("Datos recibidos:", data)
    user.email = data.get('email', user.email)
    user.nombre = data.get('nombre', user.nombre)
    user.telefono = data.get('telefono', user.telefono)
    user.rol = data.get('rol', user.rol)
    
    db.session.commit()

    return jsonify(user.serialize()), 200




#PARA ENTRENADORES 
# para mostrar la lista de entrenadores
@app.route('/listaentrenadores', methods=['GET'])
def get_entrenadores_usuarios():
    users = User.query.all()
    entrenadores = [user.serialize() for user in users if user.rol] # filtra solo los usuarios que tienen el campo rol igual a True, lo que probablemente indica que son entrenadores.
    return jsonify({
        "entrenadores": entrenadores,
    }), 200

#para mostrar en el perfil del entrenador detallado
@app.route("/listaentrenadores/<int:entrenador_id>", methods=["GET"])
def get_entrenador_by_id(entrenador_id):
    user = User.query.get(entrenador_id)
    usuarios = User.query.filter_by(rol="true").all()
    if user is None and usuarios is "false":
        return jsonify({"message": "User not found"}), 404
    return jsonify(user.serialize()), 200 

#para editar el perfil del usuario entrenador
@app.route('/listaentrenadores/<int:id>', methods=['PUT'])
def update_user(id):
    user = User.query.get(id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    data = request.get_json()
    print("Datos recibidos:", data)
    user.email = data.get('email', user.email)
    user.nombre = data.get('nombre', user.nombre)
    user.telefono = data.get('telefono', user.telefono)
    user.rol = data.get('rol', user.rol)
    user.edad = data.get('edad', user.edad)
    user.genero = data.get('genero', user.genero)
    user.altura = data.get('altura', user.altura)
    user.tipo_entrenamiento = data.get('tipo_entrenamiento', user.tipo_entrenamiento)
    user.foto = data.get('foto', user.foto)
    db.session.commit()

    return jsonify(user.serialize()), 200

  
#  para el entrenador obtener sus clientes :
@app.route("/listaentrenadores/<int:entrenador_id>/clientes", methods=["GET"])
def get_clientes_by_entrenador_id(entrenador_id):
    # Obtener los clientes asignados a un entrenador dado
    asignaciones = db.session.query(Asignacion_entrenador).filter_by(entrenador_id=entrenador_id).all()
    clientes = [User.query.get(asignacion.usuario_id).serialize() for asignacion in asignaciones]

    return jsonify(clientes), 200

#para obtener los planes del cliente rutina, dieta etc
@app.route("/clientes/<int:cliente_id>", methods=["GET"])
def get_cliente_detalle(cliente_id):
    cliente = User.query.get(cliente_id)
    if cliente is None:
        return jsonify({"message": "Cliente no encontrado"}), 404
    
    asignacion = Asignacion_entrenador.query.filter_by(usuario_id=cliente_id).first()
    if asignacion is None:
        return jsonify({"message": "Asignación no encontrada"}), 404
    
    cliente_detalle = cliente.serialize()
    cliente_detalle.update({
        "dieta": asignacion.dieta,
        "rutina": asignacion.rutina,
        "plan_entrenamiento": asignacion.plan_entrenamiento
    })

    return jsonify(cliente_detalle), 200


# para contratar a un entrenador
@app.route('/contratar', methods=['POST'])
@jwt_required()
def contratar_entrenador():
    data = request.get_json()
    entrenador_id = data.get('entrenador_id')
    usuario_id = data.get('usuario_id')
    plan_entrenamiento= data.get ('plan_entrenamiento')
    print(data)

    if not entrenador_id or not usuario_id:
        return jsonify({"error": "Faltan datos"}), 400

    entrenador = User.query.get(entrenador_id)
    usuario = User.query.get(usuario_id)

    if not entrenador or not usuario:
        return jsonify({"error": "Usuario o entrenador no encontrado"}), 404

    if not entrenador.rol or usuario.rol:
        return jsonify({"error": "Roles incorrectos"}), 400
    
    # Verificar si ya existe una asignación
    asignacion_existente = Asignacion_entrenador.query.filter_by(entrenador_id=entrenador_id, usuario_id=usuario_id).first()
    if asignacion_existente:
        return jsonify({"error": "El usuario ya ha contratado a este entrenador"}), 400
    
    asignacion = Asignacion_entrenador(
        entrenador_id=entrenador_id,
        usuario_id=usuario_id,
        plan_entrenamiento=plan_entrenamiento,
    )

    db.session.add(asignacion)
    db.session.commit()

    return jsonify({"message": "Entrenador contratado exitosamente"}), 200



#para editar borrar o modificar rutinas
@app.route("/clientes/<int:cliente_id>/rutinas", methods=["GET"])
def get_rutinas_cliente(cliente_id):
    asignacion = Asignacion_entrenador.query.filter_by(usuario_id=cliente_id).first()
    if asignacion is None:
        return jsonify({"message": "Asignación no encontrada"}), 404

    return jsonify({"rutinas": asignacion.rutina.split(';') if asignacion.rutina else []}), 200

@app.route("/clientes/<int:cliente_id>/rutinas", methods=["POST"])
def add_rutina_cliente(cliente_id):
    data = request.get_json()
    nueva_rutina = data.get('rutina', '')
    if not nueva_rutina:
        return jsonify({"message": "Rutina no proporcionada"}), 400

    asignacion = Asignacion_entrenador.query.filter_by(usuario_id=cliente_id).first()
    if asignacion is None:
        return jsonify({"message": "Asignación no encontrada"}), 404

    rutinas = asignacion.rutina.split(';') if asignacion.rutina else []
    rutinas.append(nueva_rutina)
    asignacion.rutina = ';'.join(rutinas)
    db.session.commit()

    return jsonify({"message": "Rutina añadida exitosamente"}), 201

@app.route("/clientes/<int:cliente_id>/rutinas/<int:rutina_index>", methods=["PUT"])
def update_rutina_cliente(cliente_id, rutina_index):
    data = request.get_json()
    nuevo_nombre_rutina = data.get('rutina', '')
    if not nuevo_nombre_rutina:
        return jsonify({"message": "Nombre de rutina no proporcionado"}), 400

    asignacion = Asignacion_entrenador.query.filter_by(usuario_id=cliente_id).first()
    if asignacion is None:
        return jsonify({"message": "Asignación no encontrada"}), 404

    rutinas = asignacion.rutina.split(';') if asignacion.rutina else []
    if rutina_index < 0 or rutina_index >= len(rutinas):
        return jsonify({"message": "Índice de rutina inválido"}), 400

    rutinas[rutina_index] = nuevo_nombre_rutina
    asignacion.rutina = ';'.join(rutinas)
    db.session.commit()

    return jsonify({"message": "Nombre de rutina actualizado exitosamente"}), 200

@app.route("/clientes/<int:cliente_id>/rutinas/<int:rutina_index>", methods=["DELETE"])
def delete_rutina_cliente(cliente_id, rutina_index):
    asignacion = Asignacion_entrenador.query.filter_by(usuario_id=cliente_id).first()
    if asignacion is None:
        return jsonify({"message": "Asignación no encontrada"}), 404

    rutinas = asignacion.rutina.split(';') if asignacion.rutina else []
    if rutina_index < 0 or rutina_index >= len(rutinas):
        return jsonify({"message": "Índice de rutina inválido"}), 400

    del rutinas[rutina_index]
    asignacion.rutina = ';'.join(rutinas)
    db.session.commit()

    return jsonify({"message": "Rutina eliminada exitosamente"}), 200







# Configurar Flask-Mail para usar Mailtrap
def configure_mail(app):
    app.config['MAIL_SERVER']='sandbox.smtp.mailtrap.io'
    app.config['MAIL_PORT'] = 2525
    app.config['MAIL_USERNAME'] = '41f4804efd3283'
    app.config['MAIL_PASSWORD'] = '4bd4cccf66d78e'
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False

configure_mail(app)
mail = Mail(app)

# Función para generar un token de restablecimiento de contraseña
def generate_reset_token(email):
    payload = {
        'sub': email,
        'exp': datetime.utcnow() + timedelta(minutes=10)
    }
    secret_key = 'short_secret'
    return jwt.encode(payload, secret_key, algorithm='HS256')

# Función para decodificar el token de restablecimiento de contraseña
def decode_reset_token(token):
    try:
        payload = jwt.decode(token, 'short_secret', algorithms=['HS256'])
        return payload['sub']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Ruta para solicitar la recuperación de contraseña
@app.route('/solicitud', methods=['POST'])
def forgot_password():
    email = request.json.get('email')
    user = User.query.filter_by(email=email).first()

    if user:
        user_uuid = user.user_uuid
        reset_link = f"https://glowing-spork-jj94vv5pq7p2ppw7-3000.app.github.dev/reset-password/{user_uuid}"
       # msg = Message("Password Reset Request",
        #              sender="ajrfittitans@gmail.com",  # Cambiar por tu correo
         #             recipients=[email])
        #msg.body = f"To reset your password, visit the following link: {reset_link}"
        #mail.send(msg)
        enviar_correo(email, reset_link)

        return jsonify({"msg": "Password reset link sent"}, reset_link), 200

    return jsonify({"msg": "Email not found"}), 404

@app.route('/reset-password', methods=['PUT'])
def recovery_password():
    data = request.get_json(force=True)
    try:
        user_uuid = data.get('user_uuid')
        new_password = data.get('password')
        user = User.query.filter_by(user_uuid=user_uuid).first()
        hashed_password = hash_password(new_password)
        if user:
            user.password = hashed_password
            db.session.commit()
            return jsonify({"message": "Usuario confirmado exitosamente"}), 200
        else:
            return jsonify({"error": "Usuario no encontrado"}), 404
    except Exception as e:
        return jsonify({"error": f"Error al confirmar el usuario: {str(e)}"}), 500
#}
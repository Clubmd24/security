from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import os
import pymysql
import requests
from math import radians, cos, sin, sqrt, atan2
from urllib.parse import urlparse, quote

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Parse new connection string
jawsdb_url = "mysql://roqj6vrs3u9lbrbg:s0176e7q4crbscml@bqmayq5x95g1sgr9.cbetxkdyhwsb.us-east-1.rds.amazonaws.com:3306/tsp07coyqwcok0uk"
parsed_url = urlparse(jawsdb_url)
DB_HOST = parsed_url.hostname
DB_USER = parsed_url.username
DB_PASSWORD = parsed_url.password
DB_NAME = parsed_url.path[1:]  # Remove leading slash

# Geolocation configuration
PINNED_LOCATION = (53.483959, -2.244644)  # Latitude, Longitude of the pinned building
ALLOWED_RADIUS = 50  # in meters
GEO_API_URL = "https://ipapi.co/{ip}/json/"

def init_db():
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except pymysql.MySQLError as e:
        print(f"Database connection failed: {e}")
        raise

        # Users table
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                          id INT AUTO_INCREMENT PRIMARY KEY,
                          username VARCHAR(255) UNIQUE NOT NULL,
                          password VARCHAR(255) NOT NULL,
                          role VARCHAR(50) NOT NULL)''')

        # Images table
        cursor.execute('''CREATE TABLE IF NOT EXISTS images (
                          id INT AUTO_INCREMENT PRIMARY KEY,
                          full_name VARCHAR(255) NOT NULL,
                          date_barred DATE NOT NULL,
                          date_bar_expires DATE NOT NULL,
                          reason TEXT NOT NULL,
                          image_filename VARCHAR(255))''')

        # Check for existing admin user
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin', 'administrator')")

        # Check for the main super user
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'Kieran Jenkinson'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO users (username, password, role) VALUES ('Kieran Jenkinson', '230885', 'administrator')")

        conn.commit()
    except pymysql.MySQLError as e:
        print(f"Error initializing database: {e}")
    finally:
        conn.close()

init_db()

# Helper functions
def get_db_connection():
    conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    return conn

def get_user_location(ip):
    """Fetch user location based on IP address."""
    try:
        response = requests.get(GEO_API_URL.format(ip=ip))
        if response.status_code == 200:
            data = response.json()
            return float(data.get('latitude')), float(data.get('longitude'))
    except Exception as e:
        print(f"Geolocation API error: {e}")
    return None

def calculate_distance(coord1, coord2):
    """Calculate distance between two geographic coordinates."""
    R = 6371e3  # Earth radius in meters
    lat1, lon1 = radians(coord1[0]), radians(coord1[1])
    lat2, lon2 = radians(coord2[0]), radians(coord2[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

# Routes

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))

    search_query = request.args.get('search', '').strip()
    sort_option = request.args.get('sort', '')

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    query = 'SELECT * FROM images'
    params = []

    if search_query:
        query += ' WHERE full_name LIKE %s'
        params.append(f"%{search_query}%")

    sort_options = {
        'date_barred_asc': 'date_barred ASC',
        'date_barred_desc': 'date_barred DESC',
        'date_bar_expires_asc': 'date_bar_expires ASC',
        'date_bar_expires_desc': 'date_bar_expires DESC',
        'full_name_az': 'full_name ASC'
    }

    if sort_option in sort_options:
        query += f" ORDER BY {sort_options[sort_option]}"

    cursor.execute(query, params)
    records = cursor.fetchall()
    conn.close()

    return render_template('index.html', records=records, search_query=search_query, sort_option=sort_option)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s AND role = %s', (username, password, role))
        user = cursor.fetchone()
        conn.close()

    if user:
        session['username'] = user['username']
        session['role'] = user['role']

        if user['role'] == 'administrator':
            return redirect(url_for('admin'))
        elif user['role'] == 'standard':
            return redirect(url_for('index'))  # Explicit for standard users
        else:
            flash('Role not recognized')
            return render_template('login.html')
    else:
        flash('Invalid username, password, or role')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'role' not in session or session['role'] != 'administrator':
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    if request.method == 'POST':
        if 'add_user' in request.form:
            username = request.form['username']
            password = request.form['password']
            role = request.form['role']
            try:
                cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (username, password, role))
                conn.commit()
                flash('User added successfully')
            except pymysql.IntegrityError:
                flash('Username already exists')

        elif 'add_entry' in request.form:
            full_name = request.form['full_name']
            date_barred = request.form['date_barred']
            date_bar_expires = request.form['date_bar_expires']
            reason = request.form['reason']
            image = request.files['image']

            if not full_name.strip():
                flash('Full Name is required')
            elif not date_barred.strip():
                flash('Date Barred is required')
            elif not date_bar_expires.strip():
                flash('Date Bar Expires is required')
            elif not reason.strip():
                flash('Reason is required')
            elif not image or image.filename == '':
                flash('Image is required')
            else:
                filename = secure_filename(image.filename)
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(image_path)

                cursor.execute(
                    'INSERT INTO images (full_name, date_barred, date_bar_expires, reason, image_filename) VALUES (%s, %s, %s, %s, %s)',
                    (full_name, date_barred, date_bar_expires, reason, filename)
                )
                conn.commit()
                flash('Record added successfully')

    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    conn.close()

    return render_template('admin.html', users=users)

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if 'role' not in session or session['role'] != 'administrator':
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully')
    return redirect(url_for('admin'))

@app.route('/add_user', methods=['POST'])
def add_user():
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (username, password, role))
        conn.commit()
        flash('User added successfully!')
    except pymysql.IntegrityError:
        flash('Failed to add user: username already exists.')

    conn.close()
    return redirect(url_for('admin'))

@app.route('/add_entry', methods=['POST'])
def add_entry():
    full_name = request.form['full_name']
    date_barred = request.form['date_barred']
    date_bar_expires = request.form['date_bar_expires']
    reason = request.form['reason']
    image = request.files['image']

    if not image or image.filename == '':
        flash('Image is required')
        return redirect(url_for('admin'))

    filename = secure_filename(image.filename)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        # Save the image
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        image.save(image_path)

        # Insert entry into the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO images (full_name, date_barred, date_bar_expires, reason, image_filename) VALUES (%s, %s, %s, %s, %s)', 
            (full_name, date_barred, date_bar_expires, reason, filename)
        )
        conn.commit()
        flash('Entry added successfully!')
    except pymysql.MySQLError as e:
        print(f"Error adding entry: {e}")
        flash("Failed to add entry. Please try again.")
    finally:
        conn.close()

    return redirect(url_for('admin'))
